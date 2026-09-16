from __future__ import annotations

from pathlib import Path

from ecdat.domain.enums import TargetKind
from ecdat.domain.models import Finding, ScanCoverage, ScanRequest, ScannerExecution
from ecdat.scanners.fs import DEFAULT_EXCLUDES

_SOURCE = {'.py', '.java', '.js', '.jsx', '.ts', '.tsx', '.go', '.rs', '.cs', '.c', '.cc', '.cpp', '.h', '.hpp'}
_CONFIG = {'.conf', '.cnf', '.cfg', '.ini', '.yaml', '.yml', '.toml', '.properties', '.env'}
_MANIFEST_NAMES = {
    'requirements.txt', 'pyproject.toml', 'poetry.lock', 'package.json', 'package-lock.json',
    'pnpm-lock.yaml', 'yarn.lock', 'pom.xml', 'build.gradle', 'build.gradle.kts', 'go.mod',
    'cargo.toml', 'cargo.lock', 'packages.lock.json', 'cmakelists.txt', 'meson.build',
    'conanfile.txt', 'vcpkg.json', 'makefile',
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
    execution_by_id = {item.scanner_id: item for item in executions}

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

    source_metrics = execution_by_id.get('source.static').metrics if execution_by_id.get('source.static') else {}
    if source_metrics.get('files_scanned'):
        observations.append(
            f"Source analysis examined {source_metrics.get('files_scanned')} eligible source files and emitted {source_metrics.get('raw_findings', 0)} raw signals before normalization."
        )
    binary_metrics = execution_by_id.get('binaries.heuristic').metrics if execution_by_id.get('binaries.heuristic') else {}
    if binary_metrics.get('binary_files_scanned'):
        observations.append(
            f"Binary analysis structurally inspected {binary_metrics.get('binary_files_scanned')} binary candidate(s); {binary_metrics.get('unresolved_binary_files', 0)} had no supported crypto signature."
        )
    cert_metrics = execution_by_id.get('certificates.x509').metrics if execution_by_id.get('certificates.x509') else {}
    if cert_metrics.get('limited_files'):
        observations.append(
            f"Certificate analysis retained partial results for {cert_metrics.get('limited_files')} file(s) with parser/algorithm limitations instead of aborting the adapter."
        )

    limitations = [
        'A zero-finding result means no supported deterministic evidence was observed; it does not prove cryptography is absent.',
        'Runtime-only cryptography, HSM activity, sidecars, dynamically loaded code and encrypted/packed artifacts may still require additional telemetry; TLS, cloud-KMS and PKI exports are consumed when supplied.',
    ]
    if request.target.kind in {TargetKind.DIRECTORY, TargetKind.REPOSITORY}:
        limitations.append('Static analysis reflects supplied artifacts and configuration, not every production runtime path.')
    if isinstance(supplied_sources, list) and supplied_sources and not (Path(request.target.locator) / "ecdat.context.json").is_file():
        limitations.append('No enterprise context manifest was supplied; business topology remains unknown and assessment-wide operator inputs are used only where explicitly supplied.')
    if binary_metrics.get('unresolved_binary_files'):
        limitations.append(
            f"{binary_metrics.get('unresolved_binary_files')} binary artifact(s) were inspected but remained unresolved by supported static symbol/library/string signatures."
        )

    observed_binary_files = sum(path.suffix.lower() in _BINARY for path in files)
    structurally_scanned_binaries = int(binary_metrics.get('binary_files_scanned') or 0)

    return ScanCoverage(
        files_observed=len(files),
        source_files=sum(path.suffix.lower() in _SOURCE for path in files),
        config_files=sum(path.suffix.lower() in _CONFIG for path in files),
        dependency_manifests=sum(path.name.lower() in _MANIFEST_NAMES for path in files),
        certificate_files=sum(path.suffix.lower() in _CERT for path in files),
        binary_files=max(observed_binary_files, structurally_scanned_binaries),
        container_definitions=sum(path.name.startswith('Dockerfile') for path in files),
        scanners_completed=completed,
        scanners_failed=failed,
        evidence_records=evidence_records,
        confidence_average=avg,
        observations=tuple(observations),
        limitations=tuple(limitations),
    )
