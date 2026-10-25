"""`python -m masdar migrate | seed | serve | sweep`.

The first three run in that order on a fresh machine and again after every deploy; each
is safe to repeat. Migrations are forward-only and skip what is applied; seeding upserts
reference data and never deletes; serving is the API, which also sweeps abandoned
uploads every half hour. `sweep` does that once, by hand.
"""

from __future__ import annotations

import argparse
import shutil
import sys

import psycopg

from masdar.db.migrate import migrate
from masdar.db.seed import load_scholars, load_topics, seed_reference
from masdar.db.sql import PsycopgExecutor
from masdar.db.submissions import PgSubmissions
from masdar.server import Settings, build_app, sweep_staging
from masdar.staging import LocalUploadStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="masdar")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="apply pending database migrations")
    commands.add_parser("seed", help="load reference/ scholars and topics")
    commands.add_parser("sweep", help="remove uploads nobody decided on within a day")
    serve = commands.add_parser("serve", help="run the API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    settings = Settings()  # type: ignore[call-arg]  # database_url comes from the environment

    if args.command == "serve":
        import uvicorn

        if shutil.which(settings.fpcalc_path) is None:
            # Refuse to start rather than tell every contributor their video is broken.
            message = f"fpcalc not found ({settings.fpcalc_path}); install chromaprint"
            print(message, file=sys.stderr)
            return 1
        uvicorn.run(build_app(settings), host=args.host, port=args.port)
        return 0

    with psycopg.connect(settings.database_url, autocommit=True) as connection:
        executor = PsycopgExecutor(connection)
        if args.command == "migrate":
            applied = migrate(executor, settings.migrations_dir)
            print(f"applied: {', '.join(applied) or 'nothing, already up to date'}")
        elif args.command == "sweep":
            store = LocalUploadStore(settings.staging_dir, max_bytes=settings.max_upload_bytes)
            print(f"swept {sweep_staging(PgSubmissions(executor), store)} abandoned upload(s)")
        else:
            scholars = load_scholars(settings.reference_dir / "scholars.csv")
            topics = load_topics(settings.reference_dir / "topics.yml")
            seed_reference(executor, scholars, topics)
            print(f"seeded {len(scholars)} scholars and {len(topics)} topics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
