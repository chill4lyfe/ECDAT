from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ecdat.confidence.model import confidence_from_score
from ecdat.domain.enums import AssetType, TargetKind
from ecdat.domain.models import CryptoAsset, Evidence, Finding, ScanRequest, SourceLocation
from ecdat.evidence.fingerprint import evidence_fingerprint
from ecdat.scanners.base import ScannerCapabilities
from ecdat.scanners.fs import iter_files, relative_path, resolve_target_root
from ecdat.scanners.source.openssl_detector import detect_openssl_line

_SOURCE_SUFFIXES = frozenset({".py", ".java", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".cs", ".c", ".cc", ".cpp", ".h", ".hpp"})


@dataclass(frozen=True, slots=True)
class Signal:
    canonical_name: str
    asset_type: AssetType = AssetType.ALGORITHM
    family: str | None = None
    mode: str | None = None
    key_size_bits: int | None = None
    purpose: str | None = None
    confidence: float = 0.9


_PY_CALL_SIGNALS: dict[str, Signal] = {
    "hashlib.md5": Signal("MD5", family="MD5", purpose="hashing", confidence=0.98),
    "hashlib.sha1": Signal("SHA-1", family="SHA", purpose="hashing", confidence=0.98),
    "hashlib.sha256": Signal("SHA-256", family="SHA-2", purpose="hashing", confidence=0.98),
    "hashlib.sha384": Signal("SHA-384", family="SHA-2", purpose="hashing", confidence=0.98),
    "hashlib.sha512": Signal("SHA-512", family="SHA-2", purpose="hashing", confidence=0.98),
    "hmac.new": Signal("HMAC", family="HMAC", purpose="message-authentication", confidence=0.96),
    "AESGCM": Signal("AES", family="AES", mode="GCM", purpose="encryption", confidence=0.98),
    "ChaCha20Poly1305": Signal("ChaCha20-Poly1305", family="ChaCha20", purpose="encryption", confidence=0.98),
    "rsa.generate_private_key": Signal("RSA", family="RSA", purpose="key-generation", confidence=0.99),
    "ec.generate_private_key": Signal("ECC", family="ECC", purpose="key-generation", confidence=0.97),
    "ed25519.Ed25519PrivateKey.generate": Signal("Ed25519", family="EdDSA", purpose="key-generation", confidence=0.99),
    "Fernet": Signal("Fernet", family="Fernet", purpose="authenticated-encryption", confidence=0.95),
}

_PY_IMPORT_LIBRARIES = {
    "cryptography": "cryptography",
    "Crypto": "PyCryptodome/PyCrypto",
    "OpenSSL": "pyOpenSSL",
    "jwt": "PyJWT",
    "nacl": "PyNaCl/libsodium",
    "bcrypt": "bcrypt",
    "argon2": "argon2",
}

_GENERIC_PATTERNS: tuple[tuple[re.Pattern[str], Signal, str], ...] = (
    (re.compile(r"\bCipher\.getInstance\(\s*[\"']AES(?:/GCM)?", re.I), Signal("AES", family="AES", mode="GCM", confidence=0.97), "java-jca-api"),
    (re.compile(r"\bSignature\.getInstance\(\s*[\"']SHA\d+withRSA", re.I), Signal("RSA", family="RSA", purpose="signature", confidence=0.97), "java-jca-api"),
    (re.compile(r"\bMessageDigest\.getInstance\(\s*[\"']SHA-?1", re.I), Signal("SHA-1", family="SHA", purpose="hashing", confidence=0.97), "java-jca-api"),
    (re.compile(r"\bcreateHash\(\s*[\"']md5[\"']", re.I), Signal("MD5", family="MD5", purpose="hashing", confidence=0.96), "node-crypto-api"),
    (re.compile(r"\bcreateHash\(\s*[\"']sha1[\"']", re.I), Signal("SHA-1", family="SHA", purpose="hashing", confidence=0.96), "node-crypto-api"),
    (re.compile(r"\bcreateCipheriv\(\s*[\"']aes-[0-9]+-gcm", re.I), Signal("AES", family="AES", mode="GCM", purpose="encryption", confidence=0.97), "node-crypto-api"),
    (re.compile(r"\brsa\.(?:GenerateKey|Encrypt|Decrypt|Sign|Verify)", re.I), Signal("RSA", family="RSA", confidence=0.94), "go-crypto-api"),
    (re.compile(r"\baes\.NewCipher\s*\(", re.I), Signal("AES", family="AES", purpose="encryption", confidence=0.94), "go-crypto-api"),
    (re.compile(r"\bsha1\.New\s*\(", re.I), Signal("SHA-1", family="SHA", purpose="hashing", confidence=0.94), "go-crypto-api"),
    (re.compile(r"\bAesGcm\s*\(", re.I), Signal("AES", family="AES", mode="GCM", purpose="encryption", confidence=0.96), "dotnet-crypto-api"),
    (re.compile(r"\bRSA\.Create\s*\(", re.I), Signal("RSA", family="RSA", confidence=0.96), "dotnet-crypto-api"),
    (re.compile(r"\bSHA1\.Create\s*\(", re.I), Signal("SHA-1", family="SHA", purpose="hashing", confidence=0.96), "dotnet-crypto-api"),
    (re.compile(r"\bEVP_(?:Encrypt|Decrypt|Digest|PKEY)", re.I), Signal("OpenSSL EVP usage", asset_type=AssetType.CRYPTO_USAGE, family="OpenSSL", confidence=0.9), "openssl-evp-api"),
    (re.compile(r"\bRSA_(?:new|generate_key_ex|public_encrypt|private_decrypt)", re.I), Signal("RSA", family="RSA", confidence=0.94), "openssl-rsa-api"),
)

_KEYLIKE_ASSIGNMENT = re.compile(
    r"(?i)\b(?:secret|private[_-]?key|encryption[_-]?key|aes[_-]?key)\b\s*=\s*[\"'][A-Za-z0-9+/=_-]{16,}[\"']"
)


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


class _PythonVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.signals: list[tuple[int, Signal, str, dict[str, Any]]] = []
        self.imports: list[tuple[int, str]] = []
        self.aliases: dict[str, str] = {}

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            self.imports.append((node.lineno, root))
            self.aliases[alias.asname or root] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        root = module.split(".")[0]
        if root:
            self.imports.append((node.lineno, root))
        for alias in node.names:
            self.aliases[alias.asname or alias.name] = f"{module}.{alias.name}".strip(".")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        dotted = _dotted_name(node.func)
        if dotted:
            resolved = self._resolve_alias(dotted)
            signal = self._match_call(resolved, dotted)
            if signal:
                attrs: dict[str, Any] = {"api_call": resolved}
                if signal.family == "RSA":
                    key_size = self._integer_argument(node, "key_size")
                    if key_size:
                        signal = Signal(
                            signal.canonical_name,
                            signal.asset_type,
                            signal.family,
                            signal.mode,
                            key_size,
                            signal.purpose,
                            signal.confidence,
                        )
                        attrs["key_size_bits"] = key_size
                self.signals.append((node.lineno, signal, "python-ast-call", attrs))

            if resolved.endswith("jwt.encode") or resolved == "jwt.encode":
                algorithm = self._string_keyword(node, "algorithm")
                if algorithm:
                    self.signals.append(
                        (
                            node.lineno,
                            Signal(algorithm, family=_jwt_family(algorithm), purpose="signature", confidence=0.99),
                            "python-ast-jwt-algorithm",
                            {"api_call": resolved, "jwt_algorithm": algorithm},
                        )
                    )
        self.generic_visit(node)

    def _resolve_alias(self, dotted: str) -> str:
        head, *tail = dotted.split(".")
        mapped = self.aliases.get(head, head)
        return ".".join([mapped, *tail]) if tail else mapped

    def _match_call(self, resolved: str, original: str) -> Signal | None:
        for key, signal in _PY_CALL_SIGNALS.items():
            if resolved == key or resolved.endswith(f".{key}") or original == key or original.endswith(f".{key}"):
                return signal
        return None

    @staticmethod
    def _integer_argument(node: ast.Call, keyword: str) -> int | None:
        for item in node.keywords:
            if item.arg == keyword and isinstance(item.value, ast.Constant) and isinstance(item.value.value, int):
                return item.value.value
        return None

    @staticmethod
    def _string_keyword(node: ast.Call, keyword: str) -> str | None:
        for item in node.keywords:
            if item.arg == keyword and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
                return item.value.value
        return None


def _jwt_family(algorithm: str) -> str:
    upper = algorithm.upper()
    if upper.startswith("RS") or upper.startswith("PS"):
        return "RSA"
    if upper.startswith("ES"):
        return "ECC"
    if upper.startswith("HS"):
        return "HMAC"
    if upper == "EDDSA":
        return "EdDSA"
    return "JWT"


class SourceCodeScanner:
    scanner_id = "source.static"
    version = "0.2.0"
    capabilities = ScannerCapabilities(
        target_kinds=frozenset({TargetKind.DIRECTORY, TargetKind.REPOSITORY}),
        deterministic=True,
        emits_raw_secret_material=False,
    )

    async def scan(self, request: ScanRequest) -> tuple[Finding, ...]:
        root = resolve_target_root(request.target.locator)
        findings: list[Finding] = []
        files_scanned = 0
        unreadable = 0
        for path in iter_files(root, suffixes=_SOURCE_SUFFIXES):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                unreadable += 1
                continue
            files_scanned += 1
            if path.suffix.lower() == ".py":
                findings.extend(self._scan_python(root, path, text, request))
            else:
                findings.extend(self._scan_generic(root, path, text, request))
            findings.extend(self._scan_keylike_assignment(root, path, text, request))
        self.last_metrics = {
            "files_scanned": files_scanned,
            "unreadable_files": unreadable,
            "raw_findings": len(findings),
        }
        return tuple(findings)

    def _scan_python(self, root: Path, path: Path, text: str, request: ScanRequest) -> list[Finding]:
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            return []
        visitor = _PythonVisitor()
        visitor.visit(tree)
        findings: list[Finding] = []

        seen_imports: set[str] = set()
        for line, imported in visitor.imports:
            library = _PY_IMPORT_LIBRARIES.get(imported)
            if not library or library in seen_imports:
                continue
            seen_imports.add(library)
            findings.append(
                self._finding(
                    request,
                    root,
                    path,
                    line,
                    Signal(library, asset_type=AssetType.LIBRARY, family=library, confidence=0.9),
                    "python-ast-import",
                    {"import_root": imported},
                    title=f"Cryptographic library import: {library}",
                )
            )

        for line, signal, method, attrs in visitor.signals:
            findings.append(self._finding(request, root, path, line, signal, method, attrs))
        return findings

    def _scan_generic(self, root: Path, path: Path, text: str, request: ScanRequest) -> list[Finding]:
        findings: list[Finding] = []
        c_family = path.suffix.lower() in {".c", ".cc", ".cpp", ".h", ".hpp"}
        for line_number, line in enumerate(text.splitlines(), start=1):
            semantic_signals = detect_openssl_line(line) if c_family else ()
            semantic_keys = {
                (item.canonical_name.lower(), (item.family or "").lower())
                for item in semantic_signals
            }
            for detected in semantic_signals:
                attrs = {"language_suffix": path.suffix.lower(), **detected.attributes}
                if detected.purpose:
                    attrs["operation"] = detected.purpose
                findings.append(
                    self._finding(
                        request,
                        root,
                        path,
                        line_number,
                        Signal(
                            detected.canonical_name,
                            family=detected.family,
                            mode=detected.mode,
                            key_size_bits=detected.key_size_bits,
                            purpose=detected.purpose,
                            confidence=detected.confidence,
                        ),
                        detected.method,
                        attrs,
                        tags=("source", "openssl", "semantic"),
                    )
                )
            for pattern, signal, method in _GENERIC_PATTERNS:
                if not pattern.search(line):
                    continue
                # Preserve the legacy signal surface, but do not count the same source
                # occurrence twice when Phase 9 already resolved it more precisely.
                if c_family and (signal.canonical_name.lower(), (signal.family or "").lower()) in semantic_keys:
                    continue
                findings.append(
                    self._finding(
                        request,
                        root,
                        path,
                        line_number,
                        signal,
                        method,
                        {"language_suffix": path.suffix.lower()},
                    )
                )
        return findings

    def _scan_keylike_assignment(self, root: Path, path: Path, text: str, request: ScanRequest) -> list[Finding]:
        findings: list[Finding] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not _KEYLIKE_ASSIGNMENT.search(line):
                continue
            findings.append(
                self._finding(
                    request,
                    root,
                    path,
                    line_number,
                    Signal(
                        "Hardcoded key-like material",
                        asset_type=AssetType.CRYPTO_USAGE,
                        family="key-material",
                        purpose="secret-management",
                        confidence=0.72,
                    ),
                    "redacted-keylike-assignment",
                    {"raw_value_stored": False},
                    title="Potential hardcoded cryptographic key material",
                    tags=("hardcoded-material", "redacted"),
                )
            )
        return findings

    def _finding(
        self,
        request: ScanRequest,
        root: Path,
        path: Path,
        line: int,
        signal: Signal,
        method: str,
        attrs: dict[str, Any],
        *,
        title: str | None = None,
        tags: tuple[str, ...] = ("source",),
    ) -> Finding:
        rel = relative_path(root, path)
        payload = {
            "path": rel,
            "line": line,
            "name": signal.canonical_name,
            "method": method,
            **attrs,
        }
        evidence = Evidence(
            detector=self.scanner_id,
            detector_version=self.version,
            method=method,
            location=SourceLocation(uri=request.target.locator, path=rel, line_start=line),
            fingerprint=evidence_fingerprint(
                detector=self.scanner_id,
                locator=request.target.locator,
                payload=payload,
            ),
            summary=f"{signal.canonical_name} usage identified by {method} at {rel}:{line}.",
            attributes=attrs,
        )
        asset = CryptoAsset(
            asset_type=signal.asset_type,
            canonical_name=signal.canonical_name,
            algorithm_family=signal.family,
            key_size_bits=signal.key_size_bits,
            mode=signal.mode,
            properties={"purpose": signal.purpose, "source_path": rel, **attrs},
        )
        return Finding(
            scanner_id=self.scanner_id,
            title=title or f"{signal.canonical_name} cryptographic usage",
            asset=asset,
            evidence=(evidence,),
            confidence=confidence_from_score(signal.confidence, f"Structured static signal: {method}"),
            tags=tags,
        )
