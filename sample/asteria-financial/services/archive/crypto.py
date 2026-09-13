import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def archive(data: bytes, key: bytes):
    checksum = hashlib.sha1(data).digest()  # intentionally legacy showcase
    return AESGCM(key).encrypt(b"2"*12, data + checksum, None)
