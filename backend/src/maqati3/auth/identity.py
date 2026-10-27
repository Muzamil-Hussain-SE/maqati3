"""What the login provider told us about a person, and the boundary it sits behind.

The provider is the one external system of the login. Everything after it -- is this
address on the admin list, is the session still valid -- is ours and is tested without
it, against a fake of this Protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class IdentityError(Exception):
    """The provider's answer cannot be trusted, or there was none.

    Always a refusal to sign in, never a crash: whatever came back -- a forged token, an
    expired one, an unreachable endpoint -- ends with the person not logged in.
    """


@dataclass(frozen=True, slots=True)
class Identity:
    """A person as the provider vouches for them. ``email`` is lower-cased."""

    email: str
    email_verified: bool
    name: str | None


class IdentityProvider(Protocol):
    def authorization_url(self, *, redirect_uri: str, state: str, nonce: str) -> str:
        """Where to send the browser to sign in."""
        ...

    def identify(self, *, code: str, redirect_uri: str, nonce: str) -> Identity:
        """Exchange the code the browser came back with for a verified identity.

        Raises `IdentityError` for anything that is not a valid, verified sign-in.
        """
        ...


__all__ = ["Identity", "IdentityError", "IdentityProvider"]
