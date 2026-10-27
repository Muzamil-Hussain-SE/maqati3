"""`python -m maqati3 admin add | remove | list`.

Putting an address on the admin list is how someone gets into the dashboard, so it is a
command on the server rather than a button nobody could press before there is an admin.
The logic sits here, away from the database connection, so it can be tested without one.
"""

from __future__ import annotations

import re

from maqati3.api.desk import Admins

#: Deliberately plain: one @, something on both sides, no whitespace. Google verifies the
#: address itself at sign-in; this only catches typos before they become a dead entry.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+$")


def run_admin_command(
    admins: Admins, action: str, email: str | None, *, name: str | None = None
) -> list[str]:
    """Do one thing to the list and say what happened, one line per fact."""
    if action == "list":
        people = admins.all()
        if not people:
            return ["no admins yet -- nobody can sign in to the dashboard"]
        return [f"{p.email}  ({p.name})" if p.name else p.email for p in people]

    address = (email or "").strip().lower()
    if not _EMAIL.match(address):
        raise ValueError(f"not an email address: {email!r}")

    if action == "add":
        if admins.add(address, name=name, added_by="cli"):
            return [f"added {address}"]
        return [f"{address} is already an admin"]
    if action == "remove":
        if admins.remove(address):
            return [f"removed {address} -- locked out from their next request"]
        return [f"{address} was not an admin"]
    raise ValueError(f"unknown admin command: {action}")


__all__ = ["run_admin_command"]
