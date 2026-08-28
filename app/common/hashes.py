"""리프레시 토큰은 원문을 저장하지 않는다. 파일럿 Hashes.sha256Hex 와 같은 규격이다."""

import hashlib
import secrets


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def random_token() -> str:
    """32바이트 난수를 패딩 없는 base64url 로. 파일럿과 동일한 형식이다."""
    return secrets.token_urlsafe(32)[:43]
