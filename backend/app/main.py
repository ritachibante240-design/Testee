import logging
import os
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator
from uuid import uuid4
from urllib.parse import unquote, urlsplit

import imageio_ffmpeg
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import update
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import Video
from .schemas import VideoCreate, VideoResponse


IS_VERCEL = os.getenv("VERCEL") == "1"
STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage"
STORAGE_DIR = Path(
    os.getenv("VIDEOHUB_STORAGE_DIR", str(STORAGE_DIR))
).expanduser()
VIDEO_DIR = STORAGE_DIR / "videos"
THUMBNAIL_DIR = STORAGE_DIR / "thumbnails"
API_BASE_URL = (
    os.getenv("API_BASE_URL") or os.getenv("PUBLIC_BASE_URL", "")
).strip().rstrip("/")
FRONTEND_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv("FRONTEND_ORIGINS", "").split(",")
    if origin.strip()
]

MAX_VIDEO_SIZE = 500 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024
SUPPORTED_VIDEO_EXTENSIONS = {
    ".3g2",
    ".3gp",
    ".asf",
    ".avi",
    ".f4v",
    ".flv",
    ".m2ts",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpe",
    ".mpeg",
    ".mpg",
    ".mpv",
    ".mts",
    ".mxf",
    ".ogv",
    ".ts",
    ".vob",
    ".webm",
    ".wmv",
}
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    if not IS_VERCEL:
        VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)

    Base.metadata.create_all(bind=engine)
    if IS_VERCEL:
        validate_vercel_media_urls()
    else:
        generate_missing_thumbnails()
    yield


def validate_vercel_media_urls() -> None:
    db = SessionLocal()
    try:
        for video in db.query(Video).all():
            media_urls = (video.video_url, video.thumbnail_url)
            if any(
                url and urlsplit(url).path.startswith("/storage/")
                for url in media_urls
            ):
                raise RuntimeError(
                    "Há vídeos ou miniaturas ainda apontando para /storage/. "
                    "Migre os arquivos para Vercel Blob antes de usar a API na Vercel."
                )
    finally:
        db.close()


app = FastAPI(
    title="VideoHub API",
    description="API para gerenciamento de vídeos",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "http://localhost:19006",
        "http://127.0.0.1:19006",
        *FRONTEND_ORIGINS,
    ],
    allow_origin_regex=(
        r"^(?:https?://(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
        r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?::\d+)?|"
        r"https://[a-z0-9-]+\.vercel\.app)$"
    ),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
if not IS_VERCEL:
    app.mount(
        "/storage",
        StaticFiles(directory=STORAGE_DIR, check_dir=False),
        name="storage",
    )


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def video_response(video: Video, request: Request) -> VideoResponse:
    response = VideoResponse.model_validate(video)
    base_url = API_BASE_URL or str(request.base_url).rstrip("/")
    configured_host = urlsplit(API_BASE_URL).hostname if API_BASE_URL else None
    request_host = request.url.hostname
    if configured_host in {"localhost", "127.0.0.1"} and request_host not in {
        "localhost",
        "127.0.0.1",
    }:
        base_url = str(request.base_url).rstrip("/")

    if response.video_url.startswith("/storage/"):
        response.video_url = f"{base_url}{response.video_url}"
    if response.thumbnail_url and response.thumbnail_url.startswith("/storage/"):
        response.thumbnail_url = f"{base_url}{response.thumbnail_url}"

    return response


@app.get("/")
def root():
    return {
        "message": "VideoHub API funcionando"
    }


@app.get("/api/videos", response_model=list[VideoResponse])
def get_videos(
    request: Request,
    db: Session = Depends(get_db),
):
    return [video_response(video, request) for video in db.query(Video).all()]


@app.get("/api/videos/{video_id}", response_model=VideoResponse)
def get_video(
    video_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    video = db.query(Video).filter(Video.id == video_id).first()

    if not video:
        raise HTTPException(
            status_code=404,
            detail="Vídeo não encontrado",
        )

    return video_response(video, request)


def require_public_uploads_enabled() -> None:
    if IS_VERCEL:
        raise HTTPException(
            status_code=501,
            detail=(
                "Envios de vídeo pelo backend não estão disponíveis na Vercel. "
                "Use o fluxo de envio direto para Vercel Blob."
            ),
        )

    enabled = os.getenv("VIDEOHUB_ALLOW_PUBLIC_UPLOADS", "true").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        raise HTTPException(
            status_code=403,
            detail="O envio público de vídeos está desativado.",
        )


@app.post("/api/videos/{video_id}/view", response_model=VideoResponse)
def record_video_view(
    video_id: int,
    request: Request,
    duration: int | None = Query(default=None, ge=0),
    db: Session = Depends(get_db),
):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(
            status_code=404,
            detail="Vídeo não encontrado",
        )

    values = {"views": Video.views + 1}
    if duration is not None and duration > 0 and video.duration == 0:
        values["duration"] = duration

    db.execute(update(Video).where(Video.id == video_id).values(**values))
    db.commit()
    db.refresh(video)

    return video_response(video, request)


@app.post(
    "/api/videos",
    response_model=VideoResponse,
    dependencies=[Depends(require_public_uploads_enabled)],
)
def create_video(
    video_data: VideoCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    video = Video(
        title=video_data.title,
        description=video_data.description,
        category=video_data.category,
        views=video_data.views,
        duration=video_data.duration,
        video_url=video_data.video_url,
        thumbnail_url=video_data.thumbnail_url,
    )

    db.add(video)
    db.commit()
    db.refresh(video)

    return video_response(video, request)


def save_video_upload(upload: UploadFile) -> Path:
    extension = Path(upload.filename or "").suffix.lower()

    if extension not in SUPPORTED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=(
                "Formato de vídeo não suportado. Envie MP4, MOV, MKV, WebM, "
                "AVI, WMV, FLV, MPEG, 3GP ou outro formato de vídeo comum."
            ),
        )

    file_path = VIDEO_DIR / f"{uuid4().hex}{extension}"
    saved = False

    try:
        with file_path.open("wb") as destination:
            header = upload.file.read(12)
            if extension == ".mp4" and (
                len(header) < 8 or header[4:8] != b"ftyp"
            ):
                raise HTTPException(
                    status_code=400,
                    detail="O conteúdo do arquivo não corresponde ao formato MP4",
                )

            size = len(header)
            if size > MAX_VIDEO_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail="Arquivo excede o tamanho máximo permitido",
                )
            destination.write(header)

            while chunk := upload.file.read(UPLOAD_CHUNK_SIZE):
                size += len(chunk)
                if size > MAX_VIDEO_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="Arquivo excede o tamanho máximo permitido",
                    )
                destination.write(chunk)

        saved = True
        return file_path
    finally:
        if not saved:
            file_path.unlink(missing_ok=True)


def generate_video_thumbnail(video_path: Path) -> Path:
    thumbnail_path = THUMBNAIL_DIR / f"{uuid4().hex}.jpg"
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    last_error = "O FFmpeg não conseguiu extrair um quadro do vídeo."

    try:
        for timestamp in ("1", "0"):
            try:
                result = subprocess.run(
                    [
                        ffmpeg_path,
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-ss",
                        timestamp,
                        "-i",
                        str(video_path),
                        "-frames:v",
                        "1",
                        "-vf",
                        "scale='min(640,iw)':-2",
                        "-q:v",
                        "3",
                        "-y",
                        str(thumbnail_path),
                    ],
                    capture_output=True,
                    check=False,
                    text=True,
                    timeout=60,
                )
            except subprocess.TimeoutExpired:
                last_error = "A extração da miniatura excedeu o tempo limite."
            else:
                if (
                    result.returncode == 0
                    and thumbnail_path.is_file()
                    and thumbnail_path.stat().st_size > 0
                ):
                    return thumbnail_path
                last_error = result.stderr.strip() or last_error

            thumbnail_path.unlink(missing_ok=True)

        raise RuntimeError(last_error)
    except Exception:
        thumbnail_path.unlink(missing_ok=True)
        raise


def generate_missing_thumbnails() -> None:
    db = SessionLocal()
    changed = False

    try:
        videos = db.query(Video).filter(Video.thumbnail_url.is_(None)).all()
        for video in videos:
            video_url_path = unquote(urlsplit(video.video_url).path)
            if not video_url_path.startswith("/storage/videos/"):
                logger.warning(
                    "Miniatura não gerada para o vídeo %s: a origem não é um arquivo local.",
                    video.id,
                )
                continue

            video_filename = Path(video_url_path).name
            video_path = (VIDEO_DIR / video_filename).resolve()
            if (
                not video_filename
                or video_path.parent != VIDEO_DIR.resolve()
                or not video_path.is_file()
            ):
                logger.warning(
                    "Miniatura não gerada para o vídeo %s: arquivo local ausente.",
                    video.id,
                )
                continue

            try:
                thumbnail_path = generate_video_thumbnail(video_path)
            except (OSError, RuntimeError) as error:
                logger.warning(
                    "Miniatura não gerada para o vídeo %s: %s",
                    video.id,
                    error,
                )
                continue

            video.thumbnail_url = (
                f"/storage/thumbnails/{thumbnail_path.name}"
            )
            changed = True

        if changed:
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.post(
    "/api/videos/upload",
    response_model=VideoResponse,
    status_code=201,
    dependencies=[Depends(require_public_uploads_enabled)],
)
def upload_video(
    request: Request,
    title: str = Form(..., min_length=1, max_length=255),
    category: str = Form(..., min_length=1, max_length=100),
    description: str | None = Form(None),
    duration: int = Form(0, ge=0),
    video: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    video_path = None
    thumbnail_path = None
    commit_succeeded = False

    try:
        video_path = save_video_upload(video)
        try:
            thumbnail_path = generate_video_thumbnail(video_path)
        except (OSError, RuntimeError) as error:
            logger.exception("Não foi possível gerar a miniatura do vídeo enviado.")
            raise HTTPException(
                status_code=422,
                detail=(
                    "Não foi possível ler este vídeo. Verifique se o arquivo "
                    "está íntegro e usa um formato compatível."
                ),
            ) from error

        record = Video(
            title=title,
            description=description,
            category=category,
            duration=duration,
            video_url=f"/storage/videos/{video_path.name}",
            thumbnail_url=f"/storage/thumbnails/{thumbnail_path.name}",
        )
        db.add(record)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        commit_succeeded = True
        db.refresh(record)
        return video_response(record, request)
    finally:
        if not commit_succeeded:
            if video_path is not None:
                video_path.unlink(missing_ok=True)
            if thumbnail_path is not None:
                thumbnail_path.unlink(missing_ok=True)