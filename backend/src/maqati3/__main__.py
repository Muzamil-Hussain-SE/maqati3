"""`python -m maqati3 migrate | seed | serve | sweep | inbox`.

The first three run in that order on a fresh machine and again after every deploy; each
is safe to repeat. Migrations are forward-only and skip what is applied; seeding upserts
reference data and never deletes; serving is the API, which also sweeps abandoned
uploads every half hour. `sweep` does that once, by hand. `inbox` lists what
contributors sent in and an admin has not registered yet.
"""

from __future__ import annotations

import argparse
import shutil
import sys

import psycopg

from maqati3.db.migrate import migrate
from maqati3.db.seed import load_scholars, load_topics, seed_reference
from maqati3.db.sql import PsycopgExecutor
from maqati3.db.submissions import PgSubmissions
from maqati3.server import Settings, build_app, sweep_staging
from maqati3.staging import LocalUploadStore


def print_inbox(submissions: PgSubmissions) -> None:
    items = submissions.inbox()
    if not items:
        print("inbox is empty")
    for item in items:
        minutes, seconds = divmod(round(item.duration_ms / 1000), 60)
        print(f"{item.received_at:%Y-%m-%d %H:%M}  {item.original_name}  ({minutes}:{seconds:02d})")
        print(f"    from: {item.contributor or '-'}")
        if item.kept_despite:
            print(f"    KEPT DESPITE A MATCH with {', '.join(item.kept_despite)} -- listen to both")
        print(f"    file: {item.staged_path}   sha256: {item.sha256}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="maqati3")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="apply pending database migrations")
    commands.add_parser("seed", help="load reference/ scholars and topics")
    commands.add_parser("sweep", help="remove uploads nobody decided on within a day")
    commands.add_parser("inbox", help="list kept uploads waiting to be registered")
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
        elif args.command == "inbox":
            print_inbox(PgSubmissions(executor))
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
