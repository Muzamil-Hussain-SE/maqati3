"""Google sign-in: the authorization-code flow, and the check of the id_token it returns.

An id_token is only worth what its checks are. Each of these is a way a forged or stolen
token would otherwise get in, and each has a test that must refuse it:

* signature, with Google's key and *only* RS256 -- accepting whatever algorithm the token
  names lets an attacker sign with the public key as an HMAC secret, or send none at all;
* issuer and audience -- a token Google issued to someone else's application is not ours;
* expiry -- required, not optional;
* nonce -- ties the token to the login this browser started, so one cannot be replayed
  into another;
* `email_verified` -- anyone can open a Google account under an address they do not own.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from maqati3.auth.identity import Identity, IdentityError

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"

#: Google documents both spellings.
ISSUERS = ("https://accounts.google.com", "accounts.google.com")

KeyResolver = Callable[[str], Any]


def google_key_resolver(jwks_uri: str = JWKS_URI) -> KeyResolver:
    """Look the signing key up in Google's published key set, by the token's `kid`.

    PyJWT's client caches the key set, so this is one request per key rotation and not
    one per login.
    """
    client = jwt.PyJWKClient(jwks_uri, cache_keys=True)

    def resolve(raw_token: str) -> Any:
        return client.get_signing_key_from_jwt(raw_token).key

    return resolve


def verify_id_token(
    raw_token: str, *, client_id: str, nonce: str, key_resolver: KeyResolver
) -> Identity:
    """The identity in ``raw_token``, or `IdentityError`."""
    try:
        key = key_resolver(raw_token)
        claims = jwt.decode(
            raw_token,
            key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=list(ISSUERS),
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except Exception as exc:  # jwt's own errors, a failed key lookup, anything else
        raise IdentityError(f"id_token refused: {exc}") from exc

    if claims.get("nonce") != nonce:
        raise IdentityError("id_token refused: it belongs to a different login")
    email = claims.get("email")
    if not isinstance(email, str) or not email.strip():
        raise IdentityError("id_token refused: no email address")
    if claims.get("email_verified") is not True:
        raise IdentityError("id_token refused: the email address is not verified")
    name = claims.get("name")
    return Identity(
        email=email.strip().lower(),
        email_verified=True,
        name=name if isinstance(name, str) else None,
    )


class GoogleIdentityProvider:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        http: httpx.Client | None = None,
        key_resolver: KeyResolver | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http or httpx.Client(timeout=10.0)
        self._key_resolver = key_resolver or google_key_resolver()

    def authorization_url(self, *, redirect_uri: str, state: str, nonce: str) -> str:
        query = urlencode(
            {
                "client_id": self._client_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "scope": "openid email profile",
                "state": state,
                "nonce": nonce,
                # Always offer the account chooser: an admin on a shared computer must not
                # be signed in as whoever Google last remembered.
                "prompt": "select_account",
            }
        )
        return f"{AUTHORIZATION_ENDPOINT}?{query}"

    def identify(self, *, code: str, redirect_uri: str, nonce: str) -> Identity:
        try:
            response = self._http.post(
                TOKEN_ENDPOINT,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
        except httpx.HTTPError as exc:
            raise IdentityError(f"could not reach Google's token endpoint: {exc}") from exc
        if response.status_code != 200:
            raise IdentityError(f"Google refused the code (HTTP {response.status_code})")
        raw_token = response.json().get("id_token")
        if not isinstance(raw_token, str):
            raise IdentityError("Google's answer carried no id_token")
        return verify_id_token(
            raw_token, client_id=self._client_id, nonce=nonce, key_resolver=self._key_resolver
        )


__all__ = [
    "GoogleIdentityProvider",
    "KeyResolver",
    "google_key_resolver",
    "verify_id_token",
]
