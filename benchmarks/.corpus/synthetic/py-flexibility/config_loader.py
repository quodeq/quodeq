import os


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "sqlite:///local.db")
