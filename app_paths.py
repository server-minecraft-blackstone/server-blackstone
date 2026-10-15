import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent


def get_data_dir() -> Path:
    """Return the writable application-data directory.

    Set DATA_DIR to a persistent-disk mount (for example, /var/data on Render)
    to keep SQLite settings across redeployments.
    """
    configured = os.getenv("DATA_DIR")
    directory = Path(configured).expanduser() if configured else ROOT_DIR
    if not directory.is_absolute():
        directory = ROOT_DIR / directory
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def get_database_path() -> str:
    return str(get_data_dir() / "data.db")
