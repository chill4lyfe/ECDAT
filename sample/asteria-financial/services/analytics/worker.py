import hashlib

def fingerprint(blob: bytes) -> bytes:
    return hashlib.sha512(blob).digest()
