from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def new_archive_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=3072)

def protect_archive(key: bytes, nonce: bytes, payload: bytes) -> bytes:
    return AESGCM(key).encrypt(nonce, payload, b"regulatory-archive")
