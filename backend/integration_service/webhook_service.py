import hashlib
import hmac


def verify_webhook_signature(
    payload: bytes,
    signature: str,
    secret: str,
) -> bool:
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(
        expected_signature,
        signature,
    )