from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ecdat.confidence.model import confidence_from_score
from ecdat.domain.enums import AssetType, TargetKind
from ecdat.domain.models import CryptoAsset, Evidence, Finding, ScanRequest, SourceLocation
from ecdat.evidence.fingerprint import evidence_fingerprint
from ecdat.scanners.base import ScannerCapabilities
from ecdat.scanners.fs import iter_files, relative_path, resolve_target_root

_CONFIG_SUFFIXES = frozenset({".conf", ".cfg", ".ini", ".yaml", ".yml", ".toml", ".properties", ".env"})
_CONFIG_NAMES = frozenset({"nginx.conf", "httpd.conf", "sshd_config", "haproxy.cfg", "traefik.yml", "traefik.yaml"})


@dataclass(frozen=True, slots=True)
class ConfigSignal:
    pattern: re.Pattern[str]
    name: str
    asset_type: AssetType
    family: str | None
    method: str
    confidence: float
    tag: str


_SIGNALS = (
    ConfigSignal(re.compile(r"\bssl_protocols\s+([^;]+)", re.I), "TLS", AssetType.PROTOCOL, "TLS", "nginx-tls-protocols", 0.98, "tls"),
    ConfigSignal(re.compile(r"\bMinProtocol\s*=\s*([^\s#]+)", re.I), "TLS", AssetType.PROTOCOL, "TLS", "openssl-min-protocol", 0.97, "tls"),
    ConfigSignal(re.compile(r"\bSSLProtocol\s+(.+)$", re.I), "TLS", AssetType.PROTOCOL, "TLS", "apache-ssl-protocol", 0.97, "tls"),
    ConfigSignal(re.compile(r"\bssl_ciphers\s+([^;]+)", re.I), "TLS cipher suite policy", AssetType.CRYPTO_USAGE, "TLS", "nginx-cipher-policy", 0.94, "cipher-policy"),
    ConfigSignal(re.compile(r"\bSSLCipherSuite\s+(.+)$", re.I), "TLS cipher suite policy", AssetType.CRYPTO_USAGE, "TLS", "apache-cipher-policy", 0.94, "cipher-policy"),
    ConfigSignal(re.compile(r"\b(?:JWT_ALGORITHM|jwt_algorithm|algorithm)\s*[:=]\s*[\"']?(RS256|RS384|RS512|PS256|PS384|PS512|ES256|ES384|ES512|HS256|HS384|HS512|EdDSA)", re.I), "JWT signature algorithm", AssetType.ALGORITHM, "JWT", "config-jwt-algorithm", 0.92, "jwt"),
    ConfigSignal(re.compile(r"\b(?:Ciphers|MACs|HostKeyAlgorithms)\s+(.+)$", re.I), "SSH cryptographic policy", AssetType.PROTOCOL, "SSH", "ssh-crypto-policy", 0.92, "ssh"),
    ConfigSignal(re.compile(r"\b(?:key_exchange_algorithm|tls_key_exchange|key_exchange)\s*[:=]\s*[\"']?(RSA|DH|ECDH|X25519|X448|ML-KEM(?:-512|-768|-1024)?)", re.I), "Key-establishment algorithm", AssetType.ALGORITHM, None, "config-key-establishment", 0.95, "key-establishment"),
    ConfigSignal(re.compile(r"\b(?:signature_algorithm|signing_algorithm)\s*[:=]\s*[\"']?(RSA|ECDSA|ED25519|ED448|ML-DSA(?:-44|-65|-87)?|SLH-DSA)", re.I), "Signature algorithm", AssetType.ALGORITHM, None, "config-signature-algorithm", 0.95, "signature"),
    ConfigSignal(re.compile(r"\b(?:encryption_algorithm|data_encryption_algorithm)\s*[:=]\s*[\"']?(AES(?:-128|-192|-256)?|CHACHA20(?:-POLY1305)?|RSA)", re.I), "Encryption algorithm", AssetType.ALGORITHM, None, "config-encryption-algorithm", 0.94, "encryption"),
)


def _jwt_family(algorithm: str) -> str:
    upper = algorithm.upper()
    if upper.startswith(("RS", "PS")):
        return "RSA"
    if upper.startswith("ES"):
        return "ECC"
    if upper.startswith("HS"):
        return "HMAC"
    if upper == "EDDSA":
        return "EdDSA"
    return "JWT"


class ProtocolConfigScanner:
    scanner_id = "protocols.config"
    version = "0.1.0"
    capabilities = ScannerCapabilities(
        target_kinds=frozenset({TargetKind.DIRECTORY, TargetKind.REPOSITORY}),
        deterministic=True,
    )

    async def scan(self, request: ScanRequest) -> tuple[Finding, ...]:
        root = resolve_target_root(request.target.locator)
        findings: list[Finding] = []
        for path in iter_files(root, suffixes=_CONFIG_SUFFIXES, names=_CONFIG_NAMES):
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line_no, line in enumerate(lines, 1):
                stripped = line.strip()
                if not stripped or stripped.startswith(("#", ";")):
                    continue
                for signal in _SIGNALS:
                    match = signal.pattern.search(stripped)
                    if not match:
                        continue
                    value = (match.group(1) if match.groups() else stripped).strip().strip('"\'')
                    findings.append(self._finding(request, root, path, line_no, signal, value))
        return tuple(findings)

    def _finding(
        self,
        request: ScanRequest,
        root: Path,
        path: Path,
        line: int,
        signal: ConfigSignal,
        value: str,
    ) -> Finding:
        rel = relative_path(root, path)
        attrs = {"configured_value": value, "config_kind": signal.tag}
        canonical = signal.name
        family = signal.family
        if signal.tag == "jwt":
            canonical = value.upper()
            family = _jwt_family(canonical)
        elif signal.tag in {"key-establishment", "signature", "encryption"}:
            canonical = value.upper()
            upper = canonical.upper()
            if upper.startswith("ML-KEM"):
                family = "ML-KEM"
            elif upper.startswith("ML-DSA"):
                family = "ML-DSA"
            elif upper.startswith("SLH-DSA"):
                family = "SLH-DSA"
            elif upper.startswith("AES"):
                family = "AES"
            elif upper.startswith("CHACHA20"):
                family = "ChaCha20"
            else:
                family = upper
            attrs["purpose"] = signal.tag
        evidence = Evidence(
            detector=self.scanner_id,
            detector_version=self.version,
            method=signal.method,
            location=SourceLocation(uri=request.target.locator, path=rel, line_start=line),
            fingerprint=evidence_fingerprint(
                detector=self.scanner_id,
                locator=request.target.locator,
                payload={"path": rel, "line": line, "method": signal.method, "value": value},
            ),
            summary=f"{signal.name} configuration detected in {rel}:{line}.",
            attributes=attrs,
        )
        return Finding(
            scanner_id=self.scanner_id,
            title=f"Configured {signal.name}",
            asset=CryptoAsset(
                asset_type=signal.asset_type,
                canonical_name=canonical,
                algorithm_family=family,
                properties=attrs,
            ),
            evidence=(evidence,),
            confidence=confidence_from_score(signal.confidence, f"Parsed configuration directive: {signal.method}"),
            tags=("protocol", signal.tag),
        )
