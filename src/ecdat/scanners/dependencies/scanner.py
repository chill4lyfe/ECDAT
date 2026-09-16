from __future__ import annotations

import json
import re
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ecdat.confidence.model import confidence_from_score
from ecdat.domain.enums import AssetType, TargetKind
from ecdat.domain.models import CryptoAsset, Evidence, Finding, ScanRequest, SourceLocation
from ecdat.evidence.fingerprint import evidence_fingerprint
from ecdat.scanners.base import ScannerCapabilities
from ecdat.scanners.fs import iter_files, relative_path, resolve_target_root

_MANIFEST_NAMES = frozenset(
    {
        "requirements.txt",
        "pyproject.toml",
        "Pipfile",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "go.mod",
        "Cargo.toml",
        "Cargo.lock",
        "packages.lock.json",
        "CMakeLists.txt",
        "meson.build",
        "conanfile.txt",
        "vcpkg.json",
        "Makefile",
    }
)


@dataclass(frozen=True, slots=True)
class CryptoPackage:
    canonical: str
    ecosystem: str
    capability: str


_REGISTRY: dict[str, CryptoPackage] = {
    "cryptography": CryptoPackage("cryptography", "python", "general-purpose cryptography"),
    "pycryptodome": CryptoPackage("PyCryptodome", "python", "general-purpose cryptography"),
    "pycrypto": CryptoPackage("PyCrypto", "python", "legacy general-purpose cryptography"),
    "pyjwt": CryptoPackage("PyJWT", "python", "JWT signing/verification"),
    "python-jose": CryptoPackage("python-jose", "python", "JOSE/JWT"),
    "pynacl": CryptoPackage("PyNaCl", "python", "libsodium bindings"),
    "bcrypt": CryptoPackage("bcrypt", "python", "password hashing"),
    "argon2-cffi": CryptoPackage("argon2-cffi", "python", "password hashing"),
    "jsonwebtoken": CryptoPackage("jsonwebtoken", "npm", "JWT signing/verification"),
    "jose": CryptoPackage("jose", "npm", "JOSE/JWT"),
    "node-forge": CryptoPackage("node-forge", "npm", "general-purpose cryptography/PKI"),
    "libsodium-wrappers": CryptoPackage("libsodium-wrappers", "npm", "libsodium bindings"),
    "bcryptjs": CryptoPackage("bcryptjs", "npm", "password hashing"),
    "org.bouncycastle:bcprov-jdk18on": CryptoPackage("Bouncy Castle", "maven", "JCA cryptography provider"),
    "org.bouncycastle:bcpkix-jdk18on": CryptoPackage("Bouncy Castle PKIX", "maven", "PKI/CMS"),
    "com.nimbusds:nimbus-jose-jwt": CryptoPackage("Nimbus JOSE + JWT", "maven", "JOSE/JWT"),
    "golang.org/x/crypto": CryptoPackage("golang.org/x/crypto", "go", "extended Go cryptography"),
    "github.com/golang-jwt/jwt": CryptoPackage("golang-jwt/jwt", "go", "JWT signing/verification"),
    "openssl": CryptoPackage("openssl", "rust", "OpenSSL bindings"),
    "ring": CryptoPackage("ring", "rust", "cryptographic primitives"),
    "rustls": CryptoPackage("rustls", "rust", "TLS"),
    "jsonwebtoken-rust": CryptoPackage("jsonwebtoken", "rust", "JWT signing/verification"),
    "system.security.cryptography": CryptoPackage("System.Security.Cryptography", "dotnet", ".NET cryptography"),
    "bouncycastle.cryptography": CryptoPackage("BouncyCastle.Cryptography", "dotnet", "cryptography provider"),
    "openssl-native": CryptoPackage("OpenSSL", "native", "native cryptography/TLS"),
    "libsodium-native": CryptoPackage("libsodium", "native", "native cryptographic primitives"),
}


def _registry_match(name: str, ecosystem: str) -> CryptoPackage | None:
    key = name.strip().lower()
    direct = _REGISTRY.get(key)
    if direct and (direct.ecosystem == ecosystem or direct.ecosystem in {"python", "npm", "rust"}):
        return direct
    if ecosystem == "maven":
        return _REGISTRY.get(key)
    if ecosystem == "go":
        for registry_key, package in _REGISTRY.items():
            if package.ecosystem == "go" and key.startswith(registry_key):
                return package
    if ecosystem == "dotnet" and key.startswith("system.security.cryptography"):
        return _REGISTRY["system.security.cryptography"]
    if ecosystem == "native" and key in {"openssl-native", "libsodium-native"}:
        return _REGISTRY[key]
    return None


class DependencyScanner:
    scanner_id = "dependencies.manifest"
    version = "0.2.0"
    capabilities = ScannerCapabilities(
        target_kinds=frozenset({TargetKind.DIRECTORY, TargetKind.REPOSITORY}),
        deterministic=True,
    )

    async def scan(self, request: ScanRequest) -> tuple[Finding, ...]:
        root = resolve_target_root(request.target.locator)
        findings: list[Finding] = []
        manifests_scanned = 0
        parse_failures = 0
        for path in iter_files(root, names=_MANIFEST_NAMES, max_file_bytes=5_000_000):
            try:
                dependencies = tuple(self._parse_manifest(path))
            except (OSError, ValueError, ET.ParseError, json.JSONDecodeError, tomllib.TOMLDecodeError):
                parse_failures += 1
                continue
            manifests_scanned += 1
            for name, version, ecosystem, line in dependencies:
                package = _registry_match(name, ecosystem)
                if not package:
                    continue
                findings.append(self._finding(request, root, path, package, name, version, line))
        self.last_metrics = {
            "manifests_scanned": manifests_scanned,
            "parse_failures": parse_failures,
            "raw_findings": len(findings),
        }
        return tuple(findings)

    def _parse_manifest(self, path: Path) -> Iterable[tuple[str, str | None, str, int | None]]:
        name = path.name
        if name == "requirements.txt":
            for line_no, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                match = re.match(r"([A-Za-z0-9_.-]+)\s*(?:==|>=|<=|~=|>|<)?\s*([^;\s]+)?", line)
                if match:
                    yield match.group(1), match.group(2), "python", line_no
            return

        if name == "pyproject.toml":
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            project = data.get("project", {})
            for dep in project.get("dependencies", []) or []:
                match = re.match(r"([A-Za-z0-9_.-]+)\s*([^;]+)?", str(dep))
                if match:
                    yield match.group(1), (match.group(2) or "").strip() or None, "python", None
            poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            for dep_name, value in poetry.items():
                if dep_name.lower() == "python":
                    continue
                yield dep_name, str(value) if isinstance(value, str) else None, "python", None
            return

        if name in {"package.json", "package-lock.json"}:
            data = json.loads(path.read_text(encoding="utf-8"))
            for section in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
                values = data.get(section, {}) or {}
                if isinstance(values, dict):
                    for dep_name, version in values.items():
                        yield dep_name, str(version), "npm", None
            if name == "package-lock.json":
                for package_path, meta in (data.get("packages", {}) or {}).items():
                    if not package_path.startswith("node_modules/") or not isinstance(meta, dict):
                        continue
                    dep_name = package_path.removeprefix("node_modules/")
                    yield dep_name, str(meta.get("version")) if meta.get("version") else None, "npm", None
            return

        if name == "pom.xml":
            tree = ET.parse(path)
            root = tree.getroot()
            ns = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0] + "}"
            for dep in root.findall(f".//{ns}dependency"):
                group = dep.findtext(f"{ns}groupId") or ""
                artifact = dep.findtext(f"{ns}artifactId") or ""
                version = dep.findtext(f"{ns}version")
                if group and artifact:
                    yield f"{group}:{artifact}", version, "maven", None
            return

        if name in {"build.gradle", "build.gradle.kts"}:
            for line_no, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                match = re.search(r"[\"']([^:\"']+):([^:\"']+):([^\"']+)[\"']", raw)
                if match:
                    yield f"{match.group(1)}:{match.group(2)}", match.group(3), "maven", line_no
            return

        if name == "go.mod":
            for line_no, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                line = raw.strip()
                if not line or line.startswith("module ") or line in {"require (", ")"}:
                    continue
                match = re.match(r"([^\s]+)\s+(v[^\s]+)", line)
                if match:
                    yield match.group(1), match.group(2), "go", line_no
            return

        if name in {"Cargo.toml", "Cargo.lock"}:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            if name == "Cargo.toml":
                for section in ("dependencies", "dev-dependencies", "build-dependencies"):
                    for dep_name, value in (data.get(section, {}) or {}).items():
                        if isinstance(value, str):
                            version = value
                        elif isinstance(value, dict):
                            version = str(value.get("version")) if value.get("version") else None
                        else:
                            version = None
                        registry_name = "jsonwebtoken-rust" if dep_name == "jsonwebtoken" else dep_name
                        yield registry_name, version, "rust", None
            else:
                for package in data.get("package", []) or []:
                    dep_name = str(package.get("name", ""))
                    if dep_name:
                        registry_name = "jsonwebtoken-rust" if dep_name == "jsonwebtoken" else dep_name
                        yield registry_name, str(package.get("version")) if package.get("version") else None, "rust", None
            return

        if name == "packages.lock.json":
            data = json.loads(path.read_text(encoding="utf-8"))
            for framework in (data.get("dependencies", {}) or {}).values():
                if not isinstance(framework, dict):
                    continue
                for dep_name, meta in framework.items():
                    version = meta.get("resolved") if isinstance(meta, dict) else None
                    yield dep_name, str(version) if version else None, "dotnet", None
            return

        if name in {"CMakeLists.txt", "meson.build", "conanfile.txt", "Makefile"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_no, raw in enumerate(text.splitlines(), 1):
                lower = raw.lower()
                if (
                    "find_package(openssl" in lower
                    or "openssl::crypto" in lower
                    or "openssl::ssl" in lower
                    or "dependency('openssl" in lower
                    or 'dependency("openssl' in lower
                    or "openssl/" in lower
                    or "-lcrypto" in lower
                    or "-lssl" in lower
                ):
                    yield "openssl-native", None, "native", line_no
                if "libsodium" in lower or "-lsodium" in lower:
                    yield "libsodium-native", None, "native", line_no
            return

        if name == "vcpkg.json":
            data = json.loads(path.read_text(encoding="utf-8"))
            for dep in data.get("dependencies", []) or []:
                dep_name = dep if isinstance(dep, str) else dep.get("name") if isinstance(dep, dict) else None
                if str(dep_name).lower() == "openssl":
                    yield "openssl-native", None, "native", None
                elif str(dep_name).lower() == "libsodium":
                    yield "libsodium-native", None, "native", None
            return

        # Lightweight lockfile fallback for pnpm/yarn without pretending full semantic parsing.
        if name in {"pnpm-lock.yaml", "yarn.lock"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_no, raw in enumerate(text.splitlines(), 1):
                for registry_name, package in _REGISTRY.items():
                    if package.ecosystem != "npm":
                        continue
                    if re.search(rf"(^|[/@'\"\s]){re.escape(registry_name)}([@:'\"/\s]|$)", raw, re.I):
                        yield registry_name, None, "npm", line_no

    def _finding(
        self,
        request: ScanRequest,
        root: Path,
        path: Path,
        package: CryptoPackage,
        declared_name: str,
        version: str | None,
        line: int | None,
    ) -> Finding:
        rel = relative_path(root, path)
        attrs = {
            "ecosystem": package.ecosystem,
            "declared_name": declared_name,
            "declared_version": version,
            "capability": package.capability,
        }
        evidence = Evidence(
            detector=self.scanner_id,
            detector_version=self.version,
            method=f"{package.ecosystem}-manifest-parser",
            location=SourceLocation(uri=request.target.locator, path=rel, line_start=line),
            fingerprint=evidence_fingerprint(
                detector=self.scanner_id,
                locator=request.target.locator,
                payload={"path": rel, **attrs},
            ),
            summary=f"Crypto-capable dependency {package.canonical} declared in {rel}.",
            attributes=attrs,
        )
        return Finding(
            scanner_id=self.scanner_id,
            title=f"Cryptographic dependency: {package.canonical}",
            asset=CryptoAsset(
                asset_type=AssetType.LIBRARY,
                canonical_name=package.canonical,
                version=version,
                algorithm_family=None,
                properties=attrs,
            ),
            evidence=(evidence,),
            confidence=confidence_from_score(0.95, "Parsed from a structured dependency manifest"),
            tags=("dependency", package.ecosystem),
        )
