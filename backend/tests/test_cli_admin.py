"""`python -m maqati3 admin add | remove | list`: who is on the admin list.

The list is how someone gets into the dashboard, so the command is the one place an
address is added. It is tested against a fake of the list -- the real one is covered
against Postgres in test_db_admin.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from maqati3.api.desk import AdminUser, LogRecord
from maqati3.cli_admin import run_admin_command


class FakeAdmins:
    def __init__(self, *emails: str) -> None:
        self.people = {e: AdminUser(e, None) for e in emails}
        self.added_by: list[str] = []

    def find(self, email: str) -> AdminUser | None:
        return self.people.get(email)

    def add(self, email: str, *, name: str | None, added_by: str) -> bool:
        email = email.strip().lower()
        if email in self.people:
            return False
        self.people[email] = AdminUser(email, name)
        self.added_by.append(added_by)
        return True

    def remove(self, email: str) -> bool:
        return self.people.pop(email.strip().lower(), None) is not None

    def all(self) -> list[AdminUser]:
        return list(self.people.values())

    def log(
        self, admin_email: str, action: str, subject: str | None, detail: dict[str, Any]
    ) -> None:
        pass

    def recent_log(self, *, limit: int) -> list[LogRecord]:
        return []


def test_adding_an_address_puts_it_on_the_list() -> None:
    admins = FakeAdmins()

    lines = run_admin_command(admins, "add", "Yusuf@Example.org", name="Yusuf")

    assert lines == ["added yusuf@example.org"]
    assert admins.find("yusuf@example.org") == AdminUser("yusuf@example.org", "Yusuf")
    assert admins.added_by == ["cli"]


def test_adding_an_address_twice_says_so() -> None:
    admins = FakeAdmins("yusuf@example.org")

    assert run_admin_command(admins, "add", "yusuf@example.org") == [
        "yusuf@example.org is already an admin"
    ]


@pytest.mark.parametrize("bad", ["", "   ", "no-at-sign", "two@@example.org", "a b@example.org"])
def test_something_that_is_not_an_email_address_is_refused(bad: str) -> None:
    admins = FakeAdmins()

    with pytest.raises(ValueError, match="email"):
        run_admin_command(admins, "add", bad)

    assert admins.all() == []


def test_removing_an_address_takes_it_off_the_list() -> None:
    admins = FakeAdmins("yusuf@example.org")

    assert run_admin_command(admins, "remove", "Yusuf@example.org") == [
        "removed yusuf@example.org -- locked out from their next request"
    ]
    assert admins.all() == []


def test_removing_an_address_that_is_not_on_the_list_says_so() -> None:
    assert run_admin_command(FakeAdmins(), "remove", "x@example.org") == [
        "x@example.org was not an admin"
    ]


def test_listing_shows_every_admin() -> None:
    admins = FakeAdmins("yusuf@example.org")
    admins.add("bilal@example.org", name="Bilal", added_by="cli")

    assert run_admin_command(admins, "list", None) == [
        "yusuf@example.org",
        "bilal@example.org  (Bilal)",
    ]


def test_an_empty_list_says_nobody_can_sign_in() -> None:
    assert run_admin_command(FakeAdmins(), "list", None) == [
        "no admins yet -- nobody can sign in to the dashboard"
    ]
