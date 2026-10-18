"""``python -m app.web [--config path] [--host H] [--port P]``: serve the local UI."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.config import load_config
from app.exceptions import MathGraderError

logger = logging.getLogger("app.web")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.web", description="Handwriting Math Grader — UI web lokal"
    )
    parser.add_argument("--config", type=Path, default=None, help="config.yaml lain")
    parser.add_argument("--host", default=None, help="default: web.host di config")
    parser.add_argument("--port", type=int, default=None, help="default: web.port di config")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        config = load_config(args.config)
    except MathGraderError as exc:
        logger.error("%s", exc)
        return 1

    import uvicorn

    from app.web.main import create_app

    host = args.host or config.web.host
    port = args.port or config.web.port
    logger.info("Math Grader berjalan di http://%s:%s", host, port)
    try:
        uvicorn.run(create_app(config), host=host, port=port)
    except OSError as exc:
        # Windows: WinError 10048 when another process still holds the port.
        logger.error(
            "Tidak bisa bind %s:%s (%s). Tutup server lama atau jalankan "
            "dengan --port lain (contoh: python -m app.web --port 8765).",
            host,
            port,
            exc,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
