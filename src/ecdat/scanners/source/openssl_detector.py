from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class OpenSSLSignal:
    canonical_name: str
    family: str | None
    method: str
    confidence: float
    purpose: str | None = None
    mode: str | None = None
    key_size_bits: int | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


_FETCH_CALL = re.compile(
    r"\b(EVP_(?:CIPHER|MD|MAC|KDF|KEM|SIGNATURE|KEYMGMT)_fetch)\s*\([^\n;]*?[\"']([^\"']+)[\"']",
    re.I,
)
_PKEY_NAME_CALL = re.compile(
    r"\b(EVP_PKEY_CTX_new_from_name)\s*\([^\n;]*?[\"']([^\"']+)[\"']",
    re.I,
)
_ACCESSOR = re.compile(
    r"\bEVP_(aes_(?:128|192|256)_(?:gcm|ccm|cbc|ctr|xts|ocb)|chacha20_poly1305|chacha20|"
    r"sha(?:1|224|256|384|512)|sha3_(?:224|256|384|512)|shake(?:128|256))\s*\(",
    re.I,
)
_LEGACY_API = re.compile(r"\b(RSA|DSA|DH|ECDSA|ECDH|AES|HMAC|CMAC|SHA1|SHA224|SHA256|SHA384|SHA512)_[A-Za-z0-9_]+\s*\(")
_CURVE_TOKEN = re.compile(r"\b(X25519|X448|ED25519|ED448)\b", re.I)
_PQC_TOKEN = re.compile(r"\b(ML[-_]?KEM(?:[-_]?512|[-_]?768|[-_]?1024)?|ML[-_]?DSA(?:[-_]?44|[-_]?65|[-_]?87)?|SLH[-_]?DSA)\b", re.I)
_NAMED_ALGORITHM = re.compile(
    r"[\"'](AES[-_](?:128|192|256)[-_](?:GCM|CCM|CBC|CTR|XTS|OCB)|CHACHA20[-_]POLY1305|"
    r"SHA3[-_](?:224|256|384|512)|SHA[-_]?(?:1|224|256|384|512)|HKDF|PBKDF2|SCRYPT|HMAC|CMAC|"
    r"RSA[-_]?PSS|ECDSA|ECDH|X25519|X448|ED25519|ED448|DES|DES[-_]?EDE3|RC4)[\"']",
    re.I,
)


def _sha_name(token: str) -> tuple[str, str] | None:
    compact = token.upper().replace("_", "-")
    compact = compact.replace("SHA-", "SHA")
    if compact == "SHA1":
        return "SHA-1", "SHA"
    if compact in {"SHA224", "SHA256", "SHA384", "SHA512"}:
        return f"SHA-{compact.removeprefix('SHA')}", "SHA-2"
    match = re.fullmatch(r"SHA3-?(224|256|384|512)", token.upper().replace("_", "-"))
    if match:
        return f"SHA3-{match.group(1)}", "SHA-3"
    return None


def _from_algorithm_name(name: str, *, method: str, purpose: str | None, confidence: float, api_call: str | None = None) -> OpenSSLSignal | None:
    raw = name.strip()
    upper = raw.upper().replace("_", "-")
    attrs: dict[str, Any] = {"openssl_algorithm_name": raw}
    if api_call:
        attrs["api_call"] = api_call

    aes = re.search(r"\bAES-(128|192|256)-(GCM|CCM|CBC|CTR|XTS|OCB)\b", upper)
    if aes:
        return OpenSSLSignal(
            "AES",
            "AES",
            method,
            confidence,
            purpose or "encryption",
            aes.group(2),
            int(aes.group(1)),
            attrs,
        )
    if "CHACHA20-POLY1305" in upper:
        return OpenSSLSignal("ChaCha20-Poly1305", "ChaCha20", method, confidence, purpose or "encryption", attributes=attrs)
    if upper == "CHACHA20":
        return OpenSSLSignal("ChaCha20", "ChaCha20", method, confidence, purpose or "encryption", attributes=attrs)

    sha = _sha_name(upper)
    if sha:
        return OpenSSLSignal(sha[0], sha[1], method, confidence, purpose or "hashing", attributes=attrs)

    exact: dict[str, tuple[str, str, str | None]] = {
        "HMAC": ("HMAC", "HMAC", "message-authentication"),
        "CMAC": ("CMAC", "CMAC", "message-authentication"),
        "HKDF": ("HKDF", "HKDF", "key-derivation"),
        "PBKDF2": ("PBKDF2", "PBKDF2", "key-derivation"),
        "SCRYPT": ("scrypt", "scrypt", "key-derivation"),
        "RSA": ("RSA", "RSA", None),
        "RSA-PSS": ("RSA-PSS", "RSA", "signature"),
        "DSA": ("DSA", "DSA", "signature"),
        "DH": ("DH", "DH", "key-establishment"),
        "ECDSA": ("ECDSA", "ECDSA", "signature"),
        "ECDH": ("ECDH", "ECDH", "key-establishment"),
        "EC": ("ECC", "ECC", None),
        "X25519": ("X25519", "X25519", "key-establishment"),
        "X448": ("X448", "X448", "key-establishment"),
        "ED25519": ("Ed25519", "EdDSA", "signature"),
        "ED448": ("Ed448", "EdDSA", "signature"),
        "DES": ("DES", "DES", "encryption"),
        "DES-EDE3": ("3DES", "3DES", "encryption"),
        "RC4": ("RC4", "RC4", "encryption"),
    }
    if upper in exact:
        canonical, family, default_purpose = exact[upper]
        return OpenSSLSignal(canonical, family, method, confidence, purpose or default_purpose, attributes=attrs)

    pq = upper.replace("_", "-")
    if pq.startswith("ML-KEM"):
        return OpenSSLSignal(pq, "ML-KEM", method, confidence, purpose or "key-establishment", attributes=attrs)
    if pq.startswith("ML-DSA"):
        return OpenSSLSignal(pq, "ML-DSA", method, confidence, purpose or "signature", attributes=attrs)
    if pq.startswith("SLH-DSA"):
        return OpenSSLSignal(pq, "SLH-DSA", method, confidence, purpose or "signature", attributes=attrs)
    return None


def detect_openssl_line(line: str) -> tuple[OpenSSLSignal, ...]:
    """Return deterministic OpenSSL/C semantic signals from one source line.

    This is deliberately additive to the legacy generic EVP detector.  It resolves
    concrete primitives where the API/constant carries enough information, while
    leaving unresolved EVP usage visible as contextual evidence elsewhere.
    """

    found: list[OpenSSLSignal] = []

    for match in _FETCH_CALL.finditer(line):
        api = match.group(1)
        api_upper = api.upper()
        purpose = (
            "encryption" if "CIPHER" in api_upper else
            "hashing" if "_MD_" in api_upper else
            "message-authentication" if "MAC" in api_upper else
            "key-derivation" if "KDF" in api_upper else
            "key-establishment" if "KEM" in api_upper else
            "signature" if "SIGNATURE" in api_upper else
            "key-management"
        )
        signal = _from_algorithm_name(match.group(2), method="openssl-evp-fetch", purpose=purpose, confidence=0.99, api_call=api)
        if signal:
            found.append(signal)

    for match in _PKEY_NAME_CALL.finditer(line):
        signal = _from_algorithm_name(match.group(2), method="openssl-evp-pkey-name", purpose=None, confidence=0.98, api_call=match.group(1))
        if signal:
            found.append(signal)

    for match in _ACCESSOR.finditer(line):
        token = match.group(1).replace("_", "-")
        signal = _from_algorithm_name(token, method="openssl-evp-accessor", purpose=None, confidence=0.98, api_call=f"EVP_{match.group(1)}")
        if signal:
            found.append(signal)

    for match in _LEGACY_API.finditer(line):
        token = match.group(1).upper()
        alias = {"SHA1": "SHA1", "SHA224": "SHA224", "SHA256": "SHA256", "SHA384": "SHA384", "SHA512": "SHA512"}.get(token, token)
        signal = _from_algorithm_name(alias, method="openssl-family-api", purpose=None, confidence=0.95, api_call=match.group(0).split("(", 1)[0].strip())
        if signal:
            found.append(signal)

    for match in _CURVE_TOKEN.finditer(line):
        signal = _from_algorithm_name(match.group(1), method="openssl-curve-token", purpose=None, confidence=0.9)
        if signal:
            found.append(signal)

    for match in _PQC_TOKEN.finditer(line):
        signal = _from_algorithm_name(match.group(1), method="openssl-pqc-token", purpose=None, confidence=0.93)
        if signal:
            found.append(signal)

    for match in _NAMED_ALGORITHM.finditer(line):
        signal = _from_algorithm_name(match.group(1), method="openssl-named-algorithm", purpose=None, confidence=0.94)
        if signal:
            found.append(signal)

    # Avoid duplicate semantic signals caused by the same line matching a specific
    # accessor plus its literal algorithm name. Location is added by the caller.
    unique: dict[tuple[object, ...], OpenSSLSignal] = {}
    for signal in found:
        key = (
            signal.canonical_name.lower(),
            (signal.family or "").lower(),
            signal.key_size_bits,
            (signal.mode or "").lower(),
            (signal.purpose or "").lower(),
        )
        unique.setdefault(key, signal)
    return tuple(unique.values())
