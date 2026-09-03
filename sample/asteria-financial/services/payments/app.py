import hashlib
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Deliberately unsafe reference material. Scanner evidence must never copy the value.
encryption_key = "reference-only-encryption-key-4bcdfec2"


def legacy_customer_digest(customer_id: bytes) -> bytes:
    return hashlib.sha1(customer_id).digest()


def encrypt_record(key: bytes, nonce: bytes, payload: bytes) -> bytes:
    return AESGCM(key).encrypt(nonce, payload, None)


def issue_receipt(private_key: str, claims: dict) -> str:
    return jwt.encode(claims, private_key, algorithm="RS256")


def bootstrap_legacy_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)
