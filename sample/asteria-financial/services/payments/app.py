import hashlib
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def payment_token(payload: bytes) -> bytes:
    digest = hashlib.sha256(payload).digest()
    aes = AESGCM(b"0" * 32)
    return aes.encrypt(b"1" * 12, digest, None)


def rotate_legacy_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)
