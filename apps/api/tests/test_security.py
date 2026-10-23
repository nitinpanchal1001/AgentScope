from uuid import uuid4

import jwt

from agentscope_api.core.config import Settings
from agentscope_api.core.security import (
    create_access_token,
    decode_access_token,
    generate_api_key,
    hash_password,
    keyed_hash,
    verify_password,
)


def test_password_hash_is_argon2_and_verifies() -> None:
    encoded = hash_password("correct-horse-42")
    assert encoded.startswith("$argon2id$")
    assert "correct-horse-42" not in encoded
    assert verify_password("correct-horse-42", encoded)
    assert not verify_password("wrong", encoded)


def test_access_token_rejects_wrong_audience() -> None:
    settings = Settings(environment="test")
    user_id = uuid4()
    token, _ = create_access_token(user_id, settings)
    assert decode_access_token(token, settings) == user_id
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=["HS256"], options={"verify_aud": False}
    )
    payload["aud"] = "another-service"
    wrong = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    try:
        decode_access_token(wrong, settings)
    except jwt.InvalidAudienceError:
        pass
    else:
        raise AssertionError("wrong audience was accepted")


def test_api_key_format_and_hash() -> None:
    raw, prefix = generate_api_key("production")
    assert raw.startswith("as_live_")
    assert raw.startswith(prefix)
    digest = keyed_hash(raw, "x" * 32)
    assert len(digest) == 64
    assert raw not in digest
