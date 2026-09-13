from __future__ import annotations

from pathlib import Path

from ecdat.domain.enums import TargetKind
from ecdat.domain.models import Finding, ScanCoverage, ScanRequest, ScannerExecution
from ecdat.scanners.fs import DEFAULT_EXCLUDES

_SOURCE = {'.py', '.java', '.js', '.jsx', '.ts', '.tsx', '.go', '.rs', '.cs', '.c', '.cc', '.cpp', '.h', '.hpp'}
_CONFIG = {'.conf', '.cfg', '.ini', '.yaml', '.yml', '.toml', '.properties', '.env'}
_MANIFEST_NAMES = {
    'requirements.txt', 'pyproject.toml', 'poetry.lock', 'package.json', 'package-lock.json',
    'pnpm-lock.yaml', 'yarn.lock', 'pom.xml', 'build.gradle', 'build.gradle.kts', 'go.mod',
    'cargo.toml', 'cargo.lock', 'packages.lock.json',
}
_CERT = {'.crt', '.cer', '.pem', '.der', '.p12', '.pfx'}
_BINARY = {'.so', '.dll', '.dylib', '.exe', '.bin', '.elf', '.a'}


def _visible_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    candidates = [root] if root.is_file() else root.rglob('*')
    result: list[Path] = []
    for path in candidates:
        if not path.is_file() or any(part in DEFAULT_EXCLUDES for part in path.parts):
            continue
        result.append(path)
    return result


def build_coverage(request: ScanRequest, findings: tuple[Finding, ...], executions: tuple[ScannerExecution, ...]) -> ScanCoverage:
    root = Path(request.target.locator)
    files = _visible_files(root) if request.target.kind in {TargetKind.DIRECTORY, TargetKind.REPOSITORY, TargetKind.BOM, TargetKind.BINARY} else []
    evidence_records = sum(len(item.evidence) for item in findings)
    avg = (sum(item.confidence.score for item in findings) / len(findings)) if findings else None
    completed = sum(item.status == 'completed' for item in executions)
    failed = sum(item.status == 'failed' for item in executions)

    observations: list[str] = []
    if findings:
        observations.append(f'{len(findings)} normalized cryptographic assets were supported by {evidence_records} evidence records.')
    elif files:
        observations.append(f'No deterministic cryptographic evidence was found across {len(files)} observable files with {completed} scanner adapters completing.')
    else:
        observations.append('No filesystem artifacts were available to the selected scanner adapters for this target type.')
    supplied_sources = request.target.metadata.get("sources")
    if isinstance(supplied_sources, list) and supplied_sources:
        kinds = sorted({str(item.get("kind")) for item in supplied_sources if isinstance(item, dict) and item.get("kind")})
        observations.append(
            f"Combined assessment correlated {len(supplied_sources)} supplied source(s) across: {', '.join(kinds)}."
        )

    connector_findings = [item for item in findings if item.scanner_id == 'connectors.enterprise']
    if connector_findings:
        connector_types = sorted({tag for item in connector_findings for tag in item.tags if tag in {'tls', 'cloud_kms', 'pki'}})
        observations.append(f"Enterprise connector telemetry contributed {len(connector_findings)} finding(s) from: {', '.join(connector_types)}.")
    if failed:
        observations.append(f'{failed} scanner adapter(s) failed; absence of findings from those adapters must not be interpreted as absence of cryptography.')

    limitations = [
        'A zero-finding result means no supported deterministic evidence was observed; it does not prove cryptography is absent.',
        'Runtime-only cryptography, HSM activity, sidecars, dynamically loaded code and encrypted/packed artifacts may still require additional telemetry; TLS, cloud-KMS and PKI exports are consumed when supplied.',
    ]
    if request.target.kind in {TargetKind.DIRECTORY, TargetKind.REPOSITORY}:
        limitations.append('Static analysis reflects supplied artifacts and configuration, not every production runtime path.')
    if isinstance(supplied_sources, list) and supplied_sources and not (Path(request.target.locator) / "ecdat.context.json").is_file():
        limitations.append('No enterprise context manifest was supplied; business topology and service criticality use operator-wide planning assumptions rather than invented service relationships.')

    return ScanCoverage(
        files_observed=len(files),
        source_files=sum(path.suffix.lower() in _SOURCE for path in files),
        config_files=sum(path.suffix.lower() in _CONFIG for path in files),
        dependency_manifests=sum(path.name.lower() in _MANIFEST_NAMES for path in files),
        certificate_files=sum(path.suffix.lower() in _CERT for path in files),
        binary_files=sum(path.suffix.lower() in _BINARY for path in files),
        container_definitions=sum(path.name.startswith('Dockerfile') for path in files),
        scanners_completed=completed,
        scanners_failed=failed,
        evidence_records=evidence_records,
        confidence_average=avg,
        observations=tuple(observations),
        limitations=tuple(limitations),
    )
