import os
from collections.abc import Mapping

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()


def database_settings(
    environ: Mapping[str, str],
) -> tuple[str, dict[str, str | bool]]:
    turso_url = environ.get("TURSO_DATABASE_URL", "").strip()
    turso_token = environ.get("TURSO_AUTH_TOKEN", "").strip()
    is_vercel = environ.get("VERCEL") == "1"

    if turso_url or turso_token:
        if not turso_url or not turso_token:
            raise RuntimeError(
                "TURSO_DATABASE_URL e TURSO_AUTH_TOKEN devem ser configurados juntos."
            )
        if not turso_url.startswith("libsql://"):
            raise RuntimeError(
                "TURSO_DATABASE_URL deve usar o formato libsql://."
            )

        engine_url = f"sqlite+{turso_url}"
        separator = "&" if "?" in engine_url else "?"
        return (
            f"{engine_url}{separator}secure=true",
            {"auth_token": turso_token},
        )

    if is_vercel:
        raise RuntimeError(
            "Configure TURSO_DATABASE_URL e TURSO_AUTH_TOKEN na Vercel; "
            "o SQLite local não é persistente em Vercel Functions."
        )

    database_url = environ.get("DATABASE_URL", "sqlite:///./videos.db")
    connect_args: dict[str, str | bool] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return database_url, connect_args


DATABASE_URL, connect_args = database_settings(os.environ)
engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()