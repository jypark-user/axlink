"""인증정보 암호화. 파일럿 SecretCipher 와 같은 규격이다 — AES-256-GCM, IV(12B) 앞에 붙여 base64.

마스터 키는 base64 인코딩한 32바이트다(AXLINK_SECRET_KEY). 없으면 일회용 키를 만들어 쓰되,
재기동하면 기존 암호문을 복호화할 수 없다. 운영에서는 반드시 주입한다.
"""

import base64
import logging
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.common import errors
from app.config import settings

log = logging.getLogger(__name__)

_IV_BYTES = 12
_KEY_BYTES = 32


def _resolve_key() -> bytes:
    raw = settings.secret_key
    if not raw:
        log.warning(
            "AXLINK_SECRET_KEY 가 없어 일회용 키를 생성한다. 재기동하면 기존 암호문을 "
            "복호화할 수 없다. 운영에서는 AXLINK_SECRET_KEY(base64 32바이트)를 설정하라."
        )
        return os.urandom(_KEY_BYTES)
    key = base64.b64decode(raw)
    if len(key) != _KEY_BYTES:
        raise ValueError("AXLINK_SECRET_KEY 는 base64 로 인코딩한 32바이트여야 한다.")
    return key


_key = _resolve_key()
_aead = AESGCM(_key)


def encrypt(plain: str | None) -> str | None:
    if plain is None:
        return None
    try:
        iv = os.urandom(_IV_BYTES)
        sealed = _aead.encrypt(iv, plain.encode("utf-8"), None)
        return base64.b64encode(iv + sealed).decode("ascii")
    except Exception as exc:  # noqa: BLE001
        raise errors.ApiError(500, "INTERNAL", "자격증명 암호화에 실패했습니다.") from exc


def decrypt(encoded: str | None) -> str | None:
    if encoded is None:
        return None
    try:
        blob = base64.b64decode(encoded)
        return _aead.decrypt(blob[:_IV_BYTES], blob[_IV_BYTES:], None).decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise errors.ApiError(500, "INTERNAL", "자격증명 복호화에 실패했습니다.") from exc


def hint(plain: str | None) -> str:
    """마스킹 힌트. 뒤 4자만 남긴다 — 화면에 credentialMasked 로 나간다."""
    if not plain or not plain.strip():
        return "****"
    tail = plain if len(plain) <= 4 else plain[-4:]
    return "****" + tail
