from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path


_CONFIGURED = False


def configure_logging(
    log_dir: str | os.PathLike[str] | None = None,
    level: str | int = "INFO",
) -> Path:
    """
    Configure root logging once per process.

    Writes to `<log_dir>/hugorm.log` with 10 MB rotation, 3 backups.
    Honours `HUGORM_LOG_LEVEL` and `HUGORM_LOG_DIR` env vars.
    Also attaches the same handlers to uvicorn's loggers so request access
    lines end up in the same file as our application logs.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return Path(log_dir or os.environ.get("HUGORM_LOG_DIR", "./logs"))

    path = Path(log_dir or os.environ.get("HUGORM_LOG_DIR", "./logs"))
    path.mkdir(parents=True, exist_ok=True)
    log_file = path / "hugorm.log"

    level_val = logging.getLevelNamesMapping().get(
        str(os.environ.get("HUGORM_LOG_LEVEL", level)).upper(), logging.INFO
    )

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level_val)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level_val)

    root = logging.getLogger()
    root.setLevel(level_val)
    # Clear any handlers uvicorn or others may have installed so we control format.
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Route uvicorn's loggers through our handlers too.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        ul = logging.getLogger(name)
        ul.handlers.clear()
        ul.addHandler(file_handler)
        ul.addHandler(console_handler)
        ul.setLevel(level_val)
        ul.propagate = False

    # Quiet transitively-noisy libs.
    for name, lvl in {
        "httpx": logging.WARNING,
        "httpcore": logging.WARNING,
        "asyncpg": logging.WARNING,
        "watchfiles": logging.WARNING,
        "multipart": logging.WARNING,
    }.items():
        logging.getLogger(name).setLevel(lvl)

    logging.getLogger("hugorm.logging").info(
        "logging configured -> %s (level=%s)", log_file, logging.getLevelName(level_val)
    )
    _CONFIGURED = True
    return path
