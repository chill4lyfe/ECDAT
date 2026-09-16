from __future__ import annotations

import json
import re
import shutil
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ecdat.api.routes.scans import BomScanPayload, bom_scan, run_directory_scan
from ecdat.auth.security import Principal, require_analyst
from ecdat.domain.enums import TargetKind
from ecdat.domain.models import RiskContext, ScanRequest, ScanSummary, ScanTarget
from ecdat.graph.context import EnterpriseContextManifest
from ecdat.orchestration.pipeline import ScanPipeline
from ecdat.risk.quantum import QuantumRiskEngine
from ecdat.scanners.containers.image_archive import ContainerImageArchiveScanner
from ecdat.api.catalog import catalog
from ecdat.settings import get_settings

router = APIRouter(prefix="/intake", tags=["intake"])


_SOURCE_KINDS = {"repository", "container_image", "bom", "connector", "context"}
_CONNECTOR_ARRAYS = {
    "ecdat.connector.tls.v1": ("tls-endpoints.json", "endpoints"),
    "ecdat.connector.cloud-kms.v1": ("cloud-kms.json", "keys"),
    "ecdat.connector.pki.v1": ("pki-inventory.json", "certificates"),
}


def _source_slug(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-._").lower()
    return (cleaned[:72] or fallback).replace("..", ".")


def _read_json_file(path: Path, *, label: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{label} is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail=f"{label} must contain a JSON object.")
    return payload


def _validate_connector_export(path: Path, original_name: str) -> None:
    payload = _read_json_file(path, label=original_name)
    schema = str(payload.get("schema") or "")
    target = _CONNECTOR_ARRAYS.get(schema)
    if target is None:
        raise HTTPException(status_code=400, detail=f"{original_name} is not a recognized ECDAT TLS, cloud-KMS or enterprise-PKI connector export.")
    _, array_key = target
    if not isinstance(payload.get(array_key), list):
        raise HTTPException(status_code=400, detail=f"{original_name} is missing the expected '{array_key}' record array.")
    return None


def _validate_cyclonedx(path: Path, original_name: str) -> None:
    payload = _read_json_file(path, label=original_name)
    if payload.get("bomFormat") != "CycloneDX":
        raise HTTPException(status_code=400, detail=f"{original_name} is JSON but not a CycloneDX BOM.")


def _validate_context_manifest(path: Path, original_name: str) -> None:
    payload = _read_json_file(path, label=original_name)
    try:
        manifest = EnterpriseContextManifest.model_validate(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{original_name} is not a valid ecdat.context.v1 manifest.") from exc
    if manifest.schema_name != "ecdat.context.v1":
        raise HTTPException(status_code=400, detail=f"{original_name} must use schema ecdat.context.v1.")


def _validate_container_tar(path: Path, original_name: str) -> None:
    try:
        with tarfile.open(path, mode="r:*") as bundle:
            names = {member.name for member in bundle.getmembers()[:5000]}
    except (OSError, tarfile.TarError) as exc:
        raise HTTPException(status_code=400, detail=f"{original_name} is not a readable container image TAR archive.") from exc
    if not ({"manifest.json", "index.json"} & names) and not any(name.startswith("blobs/sha256/") for name in names):
        raise HTTPException(status_code=400, detail=f"{original_name} does not look like a Docker/OCI image archive.")



def _safe_member_path(root: Path, member_name: str) -> Path:
    normalized = PurePosixPath(member_name.replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        raise HTTPException(status_code=400, detail=f"Unsafe archive path rejected: {member_name}")
    candidate = (root / Path(*normalized.parts)).resolve()
    if root.resolve() not in candidate.parents and candidate != root.resolve():
        raise HTTPException(status_code=400, detail=f"Archive member escapes intake root: {member_name}")
    return candidate


async def _store_upload(file: UploadFile, destination: Path) -> int:
    settings = get_settings()
    total = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as handle:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > settings.max_upload_bytes:
                handle.close()
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Upload exceeds configured size limit.")
            handle.write(chunk)
    await file.close()
    return total


def _extract_zip(
    archive: Path,
    root: Path,
    *,
    max_extracted_bytes: int | None = None,
    max_members: int | None = None,
) -> tuple[int, int]:
    settings = get_settings()
    byte_limit = min(settings.max_extracted_bytes, max_extracted_bytes) if max_extracted_bytes is not None else settings.max_extracted_bytes
    member_limit = min(settings.max_archive_members, max_members) if max_members is not None else settings.max_archive_members
    if byte_limit <= 0 or member_limit <= 0:
        raise HTTPException(status_code=413, detail="Combined assessment extraction budget has been exhausted.")
    extracted = 0
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > member_limit:
            raise HTTPException(status_code=413, detail="Archive contains too many members for the remaining assessment budget.")
        for member in members:
            mode = (member.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise HTTPException(status_code=400, detail="Symbolic links are not accepted in uploaded archives.")
            target = _safe_member_path(root, member.filename)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            extracted += member.file_size
            if extracted > byte_limit:
                raise HTTPException(status_code=413, detail="Expanded archive exceeds the configured assessment extraction limit.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
    return extracted, len(members)


def _extract_tar(
    archive: Path,
    root: Path,
    *,
    max_extracted_bytes: int | None = None,
    max_members: int | None = None,
) -> tuple[int, int]:
    settings = get_settings()
    byte_limit = min(settings.max_extracted_bytes, max_extracted_bytes) if max_extracted_bytes is not None else settings.max_extracted_bytes
    member_limit = min(settings.max_archive_members, max_members) if max_members is not None else settings.max_archive_members
    if byte_limit <= 0 or member_limit <= 0:
        raise HTTPException(status_code=413, detail="Combined assessment extraction budget has been exhausted.")
    extracted = 0
    with tarfile.open(archive, mode="r:*") as bundle:
        members = bundle.getmembers()
        if len(members) > member_limit:
            raise HTTPException(status_code=413, detail="Archive contains too many members for the remaining assessment budget.")
        for member in members:
            if member.issym() or member.islnk() or member.isdev():
                raise HTTPException(status_code=400, detail="Links and device nodes are not accepted in uploaded archives.")
            target = _safe_member_path(root, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            extracted += member.size
            if extracted > byte_limit:
                raise HTTPException(status_code=413, detail="Expanded archive exceeds the configured assessment extraction limit.")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                continue
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
    return extracted, len(members)


def _risk_context(
    data_lifetime_years: float | None,
    migration_time_years: float | None,
    quantum_horizon_years: float | None,
    data_sensitivity: str | None,
    business_criticality: str | None,
    public_exposure: bool | None,
    confidentiality_required: bool | None,
    context_profile: str | None = None,
    assumption_basis: str | None = None,
) -> RiskContext:
    return RiskContext(
        data_lifetime_years=data_lifetime_years,
        migration_time_years=migration_time_years,
        quantum_horizon_years=quantum_horizon_years,
        data_sensitivity=data_sensitivity,
        business_criticality=business_criticality,
        public_exposure=public_exposure,
        confidentiality_required=confidentiality_required,
        context_profile=context_profile,
        assumption_basis=assumption_basis,
    )



@router.post("/assessment", response_model=ScanSummary)
async def upload_multi_source_assessment(
    files: list[UploadFile] = File(...),
    source_kinds: str = Form(...),
    display_name: str = Form("Enterprise Assessment"),
    environment: str = Form("Production"),
    owner: str = Form("Security Architecture"),
    team: str = Form("Platform Cryptography"),
    data_lifetime_years: float | None = Form(None),
    migration_time_years: float | None = Form(None),
    quantum_horizon_years: float | None = Form(15),
    data_sensitivity: str | None = Form(None),
    business_criticality: str | None = Form(None),
    public_exposure: bool | None = Form(None),
    confidentiality_required: bool | None = Form(None),
    context_profile: str | None = Form("evidence_first"),
    assumption_basis: str | None = Form("operator"),
    principal: Principal = Depends(require_analyst),
) -> ScanSummary:
    """Create one assessment from multiple independently supplied enterprise sources.

    Each artifact retains a stable source boundary inside the managed intake workspace.
    Scanners run once across the combined workspace, allowing normalization to correlate
    the same cryptographic asset across repository, BOM, image and connector evidence.
    """
    settings = get_settings()
    try:
        kinds = json.loads(source_kinds)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="source_kinds must be a JSON array.") from exc
    if not isinstance(kinds, list) or len(kinds) != len(files):
        raise HTTPException(status_code=400, detail="Every uploaded source must have one matching source kind.")
    if not files:
        raise HTTPException(status_code=400, detail="Add at least one assessment source.")
    if len(files) > settings.max_assessment_sources:
        raise HTTPException(status_code=413, detail=f"An assessment may contain at most {settings.max_assessment_sources} supplied sources.")
    normalized_kinds = [str(kind) for kind in kinds]
    invalid = sorted(set(normalized_kinds) - _SOURCE_KINDS)
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported assessment source kind(s): {', '.join(invalid)}")

    intake_root = Path(settings.intake_dir).resolve()
    scan_root = intake_root / "organizations" / str(principal.organization_id) / str(uuid4())
    workspace = scan_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=False)
    sources: list[dict[str, object]] = []
    context_supplied = False
    total_uploaded = 0
    total_extracted = 0
    total_archive_members = 0

    try:
        for index, (upload, kind) in enumerate(zip(files, normalized_kinds, strict=True), start=1):
            original = Path(upload.filename or f"source-{index}").name
            source_id = f"source-{index:02d}"
            slug = _source_slug(Path(original).stem, source_id)
            staging = scan_root / "uploads" / f"{index:02d}-{_source_slug(original, source_id)}"
            size = await _store_upload(upload, staging)
            total_uploaded += size
            if total_uploaded > settings.max_assessment_upload_bytes:
                raise HTTPException(status_code=413, detail="Combined assessment uploads exceed the configured size limit.")

            if kind == "repository":
                lower = original.lower()
                if not lower.endswith((".zip", ".tar", ".tar.gz", ".tgz")):
                    raise HTTPException(status_code=415, detail=f"Repository source {original} must be ZIP/TAR/TGZ.")
                destination = workspace / "sources" / "repositories" / f"{index:02d}-{slug}"
                destination.mkdir(parents=True, exist_ok=False)
                try:
                    remaining_bytes = settings.max_assessment_extracted_bytes - total_extracted
                    remaining_members = settings.max_assessment_archive_members - total_archive_members
                    if lower.endswith(".zip"):
                        extracted_bytes, extracted_members = _extract_zip(
                            staging, destination,
                            max_extracted_bytes=remaining_bytes,
                            max_members=remaining_members,
                        )
                    else:
                        extracted_bytes, extracted_members = _extract_tar(
                            staging, destination,
                            max_extracted_bytes=remaining_bytes,
                            max_members=remaining_members,
                        )
                    total_extracted += extracted_bytes
                    total_archive_members += extracted_members
                except (zipfile.BadZipFile, tarfile.TarError) as exc:
                    raise HTTPException(status_code=400, detail=f"Repository archive {original} is invalid: {exc}") from exc
                staging.unlink(missing_ok=True)
                logical = str(destination.relative_to(workspace))
            elif kind == "container_image":
                if not original.lower().endswith((".tar", ".tar.gz", ".tgz")):
                    raise HTTPException(status_code=415, detail=f"Container source {original} must be a Docker/OCI TAR archive.")
                _validate_container_tar(staging, original)
                destination = workspace / "sources" / "container-images" / f"{index:02d}-{_source_slug(original, source_id)}"
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(staging), destination)
                logical = str(destination.relative_to(workspace))
            elif kind == "bom":
                if not original.lower().endswith(".json"):
                    raise HTTPException(status_code=415, detail=f"CycloneDX source {original} must be JSON.")
                _validate_cyclonedx(staging, original)
                destination = workspace / "sources" / "boms" / f"{index:02d}-{_source_slug(original, source_id)}"
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(staging), destination)
                logical = str(destination.relative_to(workspace))
            elif kind == "connector":
                _validate_connector_export(staging, original)
                destination = workspace / "sources" / "connectors" / f"{index:02d}-{_source_slug(original, source_id)}"
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(staging), destination)
                logical = str(destination.relative_to(workspace))
            else:
                if context_supplied:
                    raise HTTPException(status_code=400, detail="Add at most one ecdat.context.json file to an assessment.")
                _validate_context_manifest(staging, original)
                destination = workspace / "ecdat.context.json"
                shutil.move(str(staging), destination)
                context_supplied = True
                continue

            sources.append({
                "id": source_id,
                "kind": kind,
                "filename": original,
                "display_name": Path(original).stem.replace("-", " ").replace("_", " ").strip().title(),
                "path_prefix": logical,
                "size_bytes": size,
                "managed": True,
            })

        if not sources:
            raise HTTPException(status_code=400, detail="Add at least one evidence source in addition to optional enterprise context.")

        manifest = {
            "schema": "ecdat.assessment-sources.v1",
            "assessment_name": display_name.strip() or "Enterprise Assessment",
            "source_count": len(sources),
            "enterprise_context_supplied": context_supplied,
            "uploaded_bytes": total_uploaded,
            "extracted_repository_bytes": total_extracted,
            "archive_members": total_archive_members,
            "sources": sources,
        }
        (workspace / "ecdat.sources.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        return await run_directory_scan(
            workspace,
            display_name.strip() or "Enterprise Assessment",
            [],
            _risk_context(
                data_lifetime_years,
                migration_time_years,
                quantum_horizon_years,
                data_sensitivity,
                business_criticality,
                public_exposure,
                confidentiality_required,
                context_profile,
                assumption_basis,
            ),
            metadata={
                "environment": environment,
                "owner": owner,
                "team": team,
                "source": f"Combined assessment · {len(sources)} supplied source{'s' if len(sources) != 1 else ''}",
                "source_count": len(sources),
                "enterprise_context_supplied": context_supplied,
                "uploaded_bytes": total_uploaded,
                "extracted_repository_bytes": total_extracted,
                "archive_members": total_archive_members,
                "sources": sources,
                "managed_intake_root": str(scan_root),
            },
            organization_id=principal.organization_id,
            created_by_user_id=principal.user_id,
        )
    except Exception:
        shutil.rmtree(scan_root, ignore_errors=True)
        raise


@router.post("/archive", response_model=ScanSummary)
async def upload_archive(
    file: UploadFile = File(...),
    display_name: str = Form("Enterprise workspace"),
    environment: str = Form("Production"),
    owner: str = Form("Security Architecture"),
    team: str = Form("Platform Cryptography"),
    scanner_ids: str = Form(""),
    data_lifetime_years: float | None = Form(None),
    migration_time_years: float | None = Form(None),
    quantum_horizon_years: float | None = Form(15),
    data_sensitivity: str | None = Form(None),
    business_criticality: str | None = Form(None),
    public_exposure: bool | None = Form(None),
    confidentiality_required: bool | None = Form(None),
    context_profile: str | None = Form("evidence_first"),
    assumption_basis: str | None = Form("operator"),
    principal: Principal = Depends(require_analyst),
) -> ScanSummary:
    filename = Path(file.filename or "upload.zip").name
    suffix = filename.lower()
    if not (suffix.endswith(".zip") or suffix.endswith(".tar") or suffix.endswith(".tar.gz") or suffix.endswith(".tgz")):
        raise HTTPException(status_code=415, detail="Upload a .zip, .tar, .tar.gz or .tgz archive.")

    settings = get_settings()
    intake_root = Path(settings.intake_dir).resolve()
    scan_root = intake_root / str(uuid4())
    scan_root.mkdir(parents=True, exist_ok=False)
    archive_path = scan_root / filename
    await _store_upload(file, archive_path)
    extracted_root = scan_root / "workspace"
    extracted_root.mkdir()
    try:
        if suffix.endswith(".zip"):
            _extract_zip(archive_path, extracted_root)
        else:
            _extract_tar(archive_path, extracted_root)
    except (zipfile.BadZipFile, tarfile.TarError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid archive: {exc}") from exc
    finally:
        archive_path.unlink(missing_ok=True)

    requested = [item.strip() for item in scanner_ids.split(",") if item.strip()]
    return await run_directory_scan(
        extracted_root,
        display_name.strip() or filename,
        requested,
        _risk_context(
            data_lifetime_years,
            migration_time_years,
            quantum_horizon_years,
            data_sensitivity,
            business_criticality,
            public_exposure,
            confidentiality_required,
            context_profile,
            assumption_basis,
        ),
        metadata={"environment": environment, "owner": owner, "team": team, "source": f"Repository archive: {filename}"},
        organization_id=principal.organization_id,
        created_by_user_id=principal.user_id,
    )


@router.post("/bom", response_model=ScanSummary)
async def upload_bom(
    file: UploadFile = File(...),
    display_name: str = Form("CycloneDX cryptographic inventory"),
    environment: str = Form("Production"),
    owner: str = Form("Security Architecture"),
    team: str = Form("Platform Cryptography"),
    data_lifetime_years: float | None = Form(None),
    migration_time_years: float | None = Form(None),
    quantum_horizon_years: float | None = Form(15),
    principal: Principal = Depends(require_analyst),
) -> ScanSummary:
    filename = Path(file.filename or "bom.json").name
    if not filename.lower().endswith(".json"):
        raise HTTPException(status_code=415, detail="CycloneDX JSON input must use a .json filename.")
    settings = get_settings()
    root = Path(settings.intake_dir).resolve() / str(uuid4())
    root.mkdir(parents=True, exist_ok=False)
    destination = root / filename
    await _store_upload(file, destination)
    return await bom_scan(
        BomScanPayload(
            path=str(destination),
            display_name=display_name.strip() or filename,
            environment=environment,
            owner=owner,
            team=team,
            source_name=f"CycloneDX BOM: {filename}",
            risk_context=RiskContext(
                data_lifetime_years=data_lifetime_years,
                migration_time_years=migration_time_years,
                quantum_horizon_years=quantum_horizon_years,
            ),
        ),
        principal,
    )


@router.post("/container", response_model=ScanSummary)
async def upload_container_image(
    file: UploadFile = File(...),
    display_name: str = Form("Container image assessment"),
    environment: str = Form("Production"),
    owner: str = Form("Security Architecture"),
    team: str = Form("Platform Cryptography"),
    data_lifetime_years: float | None = Form(None),
    migration_time_years: float | None = Form(None),
    quantum_horizon_years: float | None = Form(15),
    data_sensitivity: str | None = Form(None),
    business_criticality: str | None = Form(None),
    public_exposure: bool | None = Form(None),
    confidentiality_required: bool | None = Form(None),
    context_profile: str | None = Form("evidence_first"),
    assumption_basis: str | None = Form("operator"),
    principal: Principal = Depends(require_analyst),
) -> ScanSummary:
    filename = Path(file.filename or "image.tar").name
    if not filename.lower().endswith((".tar", ".tar.gz", ".tgz")):
        raise HTTPException(status_code=415, detail="Container image input must be a TAR archive, e.g. output from docker save.")
    settings = get_settings()
    root = Path(settings.intake_dir).resolve() / str(uuid4())
    root.mkdir(parents=True, exist_ok=False)
    destination = root / filename
    await _store_upload(file, destination)
    request = ScanRequest(
        target=ScanTarget(
            kind=TargetKind.CONTAINER_IMAGE,
            locator=str(destination),
            display_name=display_name.strip() or filename,
            metadata={"environment": environment, "owner": owner, "team": team, "source": f"Container image archive: {filename}"},
        ),
        scanner_ids=(ContainerImageArchiveScanner.scanner_id,),
    )
    from ecdat.persistence.graph.neo4j import Neo4jGraphStore

    graph_store = Neo4jGraphStore()
    try:
        summary = await ScanPipeline(
            scanners=(ContainerImageArchiveScanner(),),
            graph_store=graph_store,
            risk_engine=QuantumRiskEngine(),
        ).run(
            request,
            _risk_context(
                data_lifetime_years,
                migration_time_years,
                quantum_horizon_years,
                data_sensitivity,
                business_criticality,
                public_exposure,
                confidentiality_required,
                context_profile,
                assumption_basis,
            ),
        )
    finally:
        await graph_store.close()
    catalog.put(summary, principal.organization_id, principal.user_id)
    return summary
