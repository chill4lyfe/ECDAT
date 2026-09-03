from __future__ import annotations

import shutil
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ecdat.api.routes.scans import BomScanPayload, bom_scan, run_directory_scan
from ecdat.domain.enums import TargetKind
from ecdat.domain.models import RiskContext, ScanRequest, ScanSummary, ScanTarget
from ecdat.orchestration.pipeline import ScanPipeline
from ecdat.risk.quantum import QuantumRiskEngine
from ecdat.scanners.containers.image_archive import ContainerImageArchiveScanner
from ecdat.api.catalog import catalog
from ecdat.settings import get_settings

router = APIRouter(prefix="/intake", tags=["intake"])


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


def _extract_zip(archive: Path, root: Path) -> None:
    settings = get_settings()
    extracted = 0
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > settings.max_archive_members:
            raise HTTPException(status_code=413, detail="Archive contains too many members.")
        for member in members:
            mode = (member.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise HTTPException(status_code=400, detail="Symbolic links are not accepted in uploaded archives.")
            target = _safe_member_path(root, member.filename)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            extracted += member.file_size
            if extracted > settings.max_extracted_bytes:
                raise HTTPException(status_code=413, detail="Expanded archive exceeds configured size limit.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def _extract_tar(archive: Path, root: Path) -> None:
    settings = get_settings()
    extracted = 0
    with tarfile.open(archive, mode="r:*") as bundle:
        members = bundle.getmembers()
        if len(members) > settings.max_archive_members:
            raise HTTPException(status_code=413, detail="Archive contains too many members.")
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
            if extracted > settings.max_extracted_bytes:
                raise HTTPException(status_code=413, detail="Expanded archive exceeds configured size limit.")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                continue
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def _risk_context(
    data_lifetime_years: float,
    migration_time_years: float,
    quantum_horizon_years: float,
    data_sensitivity: str,
    business_criticality: str,
    public_exposure: bool,
    confidentiality_required: bool,
) -> RiskContext:
    return RiskContext(
        data_lifetime_years=data_lifetime_years,
        migration_time_years=migration_time_years,
        quantum_horizon_years=quantum_horizon_years,
        data_sensitivity=data_sensitivity,
        business_criticality=business_criticality,
        public_exposure=public_exposure,
        confidentiality_required=confidentiality_required,
    )


@router.post("/archive", response_model=ScanSummary)
async def upload_archive(
    file: UploadFile = File(...),
    display_name: str = Form("Enterprise workspace"),
    environment: str = Form("Production"),
    owner: str = Form("Security Architecture"),
    team: str = Form("Platform Cryptography"),
    scanner_ids: str = Form(""),
    data_lifetime_years: float = Form(12),
    migration_time_years: float = Form(4),
    quantum_horizon_years: float = Form(15),
    data_sensitivity: str = Form("high"),
    business_criticality: str = Form("high"),
    public_exposure: bool = Form(True),
    confidentiality_required: bool = Form(True),
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
        ),
        metadata={"environment": environment, "owner": owner, "team": team, "source": f"Repository archive: {filename}"},
    )


@router.post("/bom", response_model=ScanSummary)
async def upload_bom(
    file: UploadFile = File(...),
    display_name: str = Form("CycloneDX cryptographic inventory"),
    environment: str = Form("Production"),
    owner: str = Form("Security Architecture"),
    team: str = Form("Platform Cryptography"),
    data_lifetime_years: float = Form(12),
    migration_time_years: float = Form(4),
    quantum_horizon_years: float = Form(15),
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
        )
    )


@router.post("/container", response_model=ScanSummary)
async def upload_container_image(
    file: UploadFile = File(...),
    display_name: str = Form("Container image assessment"),
    environment: str = Form("Production"),
    owner: str = Form("Security Architecture"),
    team: str = Form("Platform Cryptography"),
    data_lifetime_years: float = Form(12),
    migration_time_years: float = Form(4),
    quantum_horizon_years: float = Form(15),
    data_sensitivity: str = Form("high"),
    business_criticality: str = Form("high"),
    public_exposure: bool = Form(True),
    confidentiality_required: bool = Form(True),
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
            ),
        )
    finally:
        await graph_store.close()
    catalog.put(summary)
    return summary
