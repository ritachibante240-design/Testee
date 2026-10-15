import argparse
import asyncio
import os
from collections.abc import AsyncIterator
from importlib import import_module
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, engine as remote_engine
from app.models import Video

BACKEND_DIR = Path(__file__).resolve().parents[1]
STORAGE_DIR = Path(
    os.getenv("VIDEOHUB_STORAGE_DIR", BACKEND_DIR / "storage")
).expanduser()
CHUNK_SIZE = 8 * 1024 * 1024


def local_media_path(url: str | None, media_type: str) -> Path | None:
    if not url:
        return None

    media_path = unquote(urlsplit(url).path)
    prefix = f"/storage/{media_type}/"
    if not media_path.startswith(prefix):
        return None

    filename = Path(media_path).name
    media_directory = (STORAGE_DIR / media_type).resolve()
    path = (media_directory / filename).resolve()
    if path.parent != media_directory:
        raise ValueError(f"Caminho de mídia inválido: {url}")
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo local não encontrado: {path}")
    return path


async def file_chunks(path: Path) -> AsyncIterator[bytes]:
    with path.open("rb") as source:
        while chunk := await asyncio.to_thread(source.read, CHUNK_SIZE):
            yield chunk


async def upload_media(
    client: Any,
    video_id: int,
    media_type: str,
    path: Path,
) -> str:
    content_type = "video/mp4" if media_type == "videos" else "image/jpeg"
    blob = await client.put(
        f"videohub/{media_type}/{video_id}-{path.name}",
        file_chunks(path),
        access="public",
        content_type=content_type,
        overwrite=True,
    )
    return str(blob["url"])


def copy_local_records() -> list[dict[str, Any]]:
    local_database_url = os.getenv("LOCAL_DATABASE_URL", "sqlite:///./videos.db")
    connect_args = (
        {"check_same_thread": False}
        if local_database_url.startswith("sqlite")
        else {}
    )
    local_engine = create_engine(
        local_database_url,
        connect_args=connect_args,
    )

    try:
        with Session(local_engine) as source:
            videos = source.query(Video).order_by(Video.id).all()
            records = [
                {
                    "id": video.id,
                    "title": video.title,
                    "description": video.description,
                    "category": video.category,
                    "views": video.views,
                    "duration": video.duration,
                    "video_url": video.video_url,
                    "thumbnail_url": video.thumbnail_url,
                    "created_at": video.created_at,
                }
                for video in videos
            ]
    finally:
        local_engine.dispose()

    if not records:
        raise RuntimeError("O SQLite local não contém vídeos para migrar.")
    return records


async def migrate() -> None:
    if not remote_engine.url.drivername.endswith("+libsql"):
        raise RuntimeError(
            "Configure TURSO_DATABASE_URL e TURSO_AUTH_TOKEN para apontar "
            "o destino à base remota Turso."
        )

    if not (
        os.getenv("BLOB_READ_WRITE_TOKEN")
        or (
            os.getenv("VERCEL_OIDC_TOKEN")
            and os.getenv("BLOB_STORE_ID")
        )
    ):
        raise RuntimeError(
            "Configure BLOB_READ_WRITE_TOKEN ou as credenciais OIDC da Vercel "
            "antes de enviar arquivos."
        )

    records = copy_local_records()
    planned_media: list[tuple[dict[str, Any], str, Path]] = []
    for record in records:
        for field, media_type in (
            ("video_url", "videos"),
            ("thumbnail_url", "thumbnails"),
        ):
            path = local_media_path(record[field], media_type)
            if path is not None:
                planned_media.append((record, field, path))

    Base.metadata.create_all(bind=remote_engine)
    with Session(remote_engine) as destination:
        if destination.query(Video.id).first():
            raise RuntimeError(
                "A base Turso já contém vídeos. A migração foi interrompida "
                "para evitar sobrescrever registros."
            )

    try:
        blob_module = import_module("vercel.blob")
    except ImportError as error:
        raise RuntimeError(
            "Instale requirements-migration.txt antes de executar a migração."
        ) from error

    client = blob_module.AsyncBlobClient()
    for record, field, path in planned_media:
        media_type = "videos" if field == "video_url" else "thumbnails"
        record[field] = await upload_media(
            client,
            record["id"],
            media_type,
            path,
        )

    with Session(remote_engine) as destination:
        destination.add_all(Video(**record) for record in records)
        destination.commit()

    print(
        f"Migração concluída: {len(records)} registros e "
        f"{len(planned_media)} arquivos enviados."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Envia a mídia local para Vercel Blob e copia os registros "
            "do SQLite para uma base Turso vazia."
        )
    )
    parser.add_argument(
        "--confirm-public-upload",
        action="store_true",
        help="Confirma o envio dos vídeos para armazenamento público.",
    )
    args = parser.parse_args()
    if not args.confirm_public_upload:
        parser.error(
            "Adicione --confirm-public-upload somente depois de revisar "
            "os custos e confirmar a publicação pública dos arquivos."
        )

    asyncio.run(migrate())


if __name__ == "__main__":
    main()
