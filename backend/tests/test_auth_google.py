"""Who is signing in: verifying what Google says, without trusting anything it did not sign.

The id_token check is a security gate, so every way a token can be wrong has a test that
must refuse it. Google itself is the genuinely external system: its signing key and its
token endpoint are replaced by a locally generated key and an `httpx.MockTransport`,
while the verification logic under test is the real one.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from maqati3.auth.google import GoogleIdentityProvider, verify_id_token
from maqati3.auth.identity import Identity, IdentityError

CLIENT_ID = "1234-abc.apps.googleusercontent.com"
NONCE = "nonce-from-this-login"
ISSUER = "https://accounts.google.com"

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def claims(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    base: dict[str, Any] = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": "1098765",
        "email": "Yusuf@Example.org",
        "email_verified": True,
        "name": "Yusuf",
        "nonce": NONCE,
        "iat": now - 5,
        "exp": now + 600,
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


def token(payload: dict[str, Any], key: Any = KEY, algorithm: str = "RS256") -> str:
    return jwt.encode(payload, key, algorithm=algorithm, headers={"kid": "k1"})


def resolver(_: str) -> Any:
    return KEY.public_key()


def verify(
    raw: str, *, nonce: str = NONCE, key_resolver: Callable[[str], Any] = resolver
) -> Identity:
    return verify_id_token(raw, client_id=CLIENT_ID, nonce=nonce, key_resolver=key_resolver)


def test_a_valid_token_gives_the_verified_identity_with_a_normalised_email() -> None:
    identity = verify(token(claims()))

    assert identity == Identity(email="yusuf@example.org", email_verified=True, name="Yusuf")


def test_the_issuer_may_be_written_without_the_scheme() -> None:
    # Google documents both spellings of its issuer.
    assert verify(token(claims(iss="accounts.google.com"))).email == "yusuf@example.org"


@pytest.mark.parametrize(
    ("what", "payload"),
    [
        ("wrong audience", claims(aud="someone-elses-client.apps.googleusercontent.com")),
        ("wrong issuer", claims(iss="https://evil.example.com")),
        ("expired", claims(exp=int(time.time()) - 60)),
        ("no expiry at all", claims(exp=None)),
        ("wrong nonce", claims(nonce="a-different-login")),
        ("no nonce", claims(nonce=None)),
        ("no email", claims(email=None)),
    ],
)
def test_a_token_that_is_wrong_in_any_way_is_refused(what: str, payload: dict[str, Any]) -> None:
    with pytest.raises(IdentityError):
        verify(token(payload))


def test_an_unverified_email_is_refused() -> None:
    # Anyone can register a Google account under an address they do not control. Only
    # an address Google has verified may be matched against the admin list.
    with pytest.raises(IdentityError, match="verified"):
        verify(token(claims(email_verified=False)))


def test_a_token_signed_with_another_key_is_refused() -> None:
    with pytest.raises(IdentityError):
        verify(token(claims(), key=OTHER_KEY))


def test_a_token_with_no_signature_is_refused() -> None:
    unsigned = jwt.encode(claims(), key=None, algorithm="none")

    with pytest.raises(IdentityError):
        verify(unsigned)


def test_a_symmetric_algorithm_is_refused_even_with_a_matching_secret() -> None:
    # The classic confusion attack: sign with HS256 using the *public* key as the secret.
    forged = jwt.encode(claims(), "the-public-key-bytes", algorithm="HS256")

    with pytest.raises(IdentityError):
        verify(forged)


def test_garbage_is_refused_not_crashed_on() -> None:
    with pytest.raises(IdentityError):
        verify("not.a.jwt")


def test_a_failing_key_lookup_is_refused_not_crashed_on() -> None:
    def broken(_: str) -> Any:
        raise RuntimeError("could not reach Google's key endpoint")

    with pytest.raises(IdentityError):
        verify(token(claims()), key_resolver=broken)


# ------------------------------------------------------------------ the provider


def provider(handler: Callable[[httpx.Request], httpx.Response]) -> GoogleIdentityProvider:
    return GoogleIdentityProvider(
        client_id=CLIENT_ID,
        client_secret="s3cret",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        key_resolver=resolver,
    )


def test_the_authorization_url_carries_what_google_needs_and_what_we_check_later() -> None:
    url = provider(lambda r: httpx.Response(500)).authorization_url(
        redirect_uri="https://archiv.example.org/api/v1/admin/auth/callback",
        state="the-state",
        nonce="the-nonce",
    )

    parts = urlparse(url)
    query = parse_qs(parts.query)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == (
        "https://accounts.google.com/o/oauth2/v2/auth"
    )
    assert query["client_id"] == [CLIENT_ID]
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == ["https://archiv.example.org/api/v1/admin/auth/callback"]
    assert query["state"] == ["the-state"]
    assert query["nonce"] == ["the-nonce"]
    assert set(query["scope"][0].split()) == {"openid", "email", "profile"}


def test_the_code_is_exchanged_for_an_identity() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["form"] = parse_qs(request.content.decode())
        return httpx.Response(200, json={"id_token": token(claims())})

    identity = provider(handler).identify(
        code="auth-code",
        redirect_uri="https://archiv.example.org/api/v1/admin/auth/callback",
        nonce=NONCE,
    )

    assert identity.email == "yusuf@example.org"
    assert seen["url"] == "https://oauth2.googleapis.com/token"
    assert seen["form"]["code"] == ["auth-code"]
    assert seen["form"]["grant_type"] == ["authorization_code"]
    assert seen["form"]["client_secret"] == ["s3cret"]


def test_an_error_from_googles_token_endpoint_is_a_refusal() -> None:
    with pytest.raises(IdentityError):
        provider(lambda r: httpx.Response(400, json={"error": "invalid_grant"})).identify(
            code="used-twice", redirect_uri="https://x/cb", nonce=NONCE
        )


def test_a_reply_without_an_id_token_is_a_refusal() -> None:
    with pytest.raises(IdentityError):
        provider(lambda r: httpx.Response(200, json={"access_token": "only"})).identify(
            code="c", redirect_uri="https://x/cb", nonce=NONCE
        )


def test_an_unreachable_token_endpoint_is_a_refusal_not_a_crash() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    with pytest.raises(IdentityError):
        provider(down).identify(code="c", redirect_uri="https://x/cb", nonce=NONCE)
