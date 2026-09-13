import hmac, hashlib
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

def protect(data: bytes, key: bytes):
    mac = hmac.new(key, data, hashlib.sha384).digest()
    return ChaCha20Poly1305(key[:32]).encrypt(b"0"*12, data + mac, None)
