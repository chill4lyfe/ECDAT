from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ecdat.api.catalog import catalog
from ecdat.auth.security import Principal, require_analyst, require_authenticated
from ecdat.domain.enums import TargetKind
from ecdat.domain.models import RiskContext, ScanRequest, ScanSummary, ScanTarget
from ecdat.orchestration.pipeline import ScanPipeline
from ecdat.risk.quantum import QuantumRiskEngine
from ecdat.scanners.registry import select_scanners
from ecdat.settings import get_settings

router = APIRouter(prefix="/scans", tags=["scans"])

REFERENCE_PATH = "/workspace/sample/asteria-financial"


class DirectoryScanPayload(BaseModel):
    path: str = REFERENCE_PATH
    display_name: str | None = "Asteria Financial Services — Cryptographic Estate"
    scanner_ids: list[str] = Field(default_factory=list)
    environment: str = "Production"
    owner: str = "Security Architecture"
    team: str = "Platform Cryptography"
    source_name: str = "Mounted workspace"
    risk_context: RiskContext = Field(
        default_factory=lambda: RiskContext(
            quantum_horizon_years=15,
            context_profile="evidence_first",
            assumption_basis="operator",
        )
    )


class BomScanPayload(BaseModel):
    path: str
    display_name: str | None = None
    environment: str = "Production"
    owner: str = "Security Architecture"
    team: str = "Platform Cryptography"
    source_name: str = "CycloneDX BOM"
    risk_context: RiskContext = Field(default_factory=RiskContext)


class ScanHistoryItem(BaseModel):
    scan_id: UUID
    created_at: datetime
    status: str
    target_kind: str
    display_name: str
    locator: str
    source: str
    environment: str
    owner: str
    team: str
    assets: int
    vulnerable: int
    hndl: int
    blockers: int
    critical: int
    evidence_count: int
    average_confidence: float | None
    files_observed: int
    context_manifest_loaded: bool


class AssetDelta(BaseModel):
    identity: str
    name: str
    asset_type: str
    version: str | None = None


class ScanComparison(BaseModel):
    base_scan_id: UUID
    target_scan_id: UUID
    new_assets: tuple[AssetDelta, ...]
    resolved_assets: tuple[AssetDelta, ...]
    unchanged_assets: int
    asset_delta: int
    vulnerable_delta: int
    hndl_delta: int
    blocker_delta: int
    critical_delta: int


def _validate_scan_path(path: str) -> Path:
    settings = get_settings()
    candidate = Path(path).expanduser().resolve()
    if not candidate.exists():
        raise HTTPException(status_code=404, detail=f"Scan path does not exist: {candidate}")
    allowed = [Path(item.strip()).expanduser().resolve() for item in settings.allowed_scan_roots.split(",") if item.strip()]
    if allowed and not any(candidate == root or root in candidate.parents for root in allowed):
        raise HTTPException(status_code=403, detail={"message": "Scan path is outside configured allowed roots.", "allowed_roots": [str(root) for root in allowed]})
    return candidate


async def run_directory_scan(
    root: Path,
    display_name: str,
    scanner_ids: list[str] | tuple[str, ...],
    risk_context: RiskContext,
    *,
    metadata: dict[str, object] | None = None,
    organization_id: UUID | None = None,
    created_by_user_id: UUID | None = None,
) -> ScanSummary:
    scanners = select_scanners(scanner_ids)
    if scanner_ids and not scanners:
        raise HTTPException(status_code=400, detail="None of the requested scanner IDs are registered.")
    request = ScanRequest(
        target=ScanTarget(kind=TargetKind.DIRECTORY, locator=str(root), display_name=display_name, metadata=metadata or {}),
        scanner_ids=tuple(scanner.scanner_id for scanner in scanners),
    )
    from ecdat.persistence.graph.neo4j import Neo4jGraphStore
    graph_store = Neo4jGraphStore()
    try:
        summary = await ScanPipeline(scanners=scanners, graph_store=graph_store, risk_engine=QuantumRiskEngine()).run(request, risk_context)
    finally:
        await graph_store.close()
    catalog.put(summary, organization_id, created_by_user_id)
    return summary


@router.post("/reference", response_model=ScanSummary)
async def reference_assessment(
    quantum_horizon_years: float = Query(default=15, gt=0, le=100),
    data_lifetime_years: float = Query(default=12, ge=0, le=100),
    migration_time_years: float = Query(default=4, ge=0, le=50),
    data_sensitivity: str = Query(default="high"),
    business_criticality: str = Query(default="high"),
    public_exposure: bool = Query(default=True),
    confidentiality_required: bool = Query(default=True),
    context_profile: str = Query(default="reference_demo"),
    assumption_basis: str = Query(default="demonstration"),
    display_name: str = Query(default="Asteria Financial Services — Cryptographic Estate"),
    environment: str = Query(default="Production"),
    owner: str = Query(default="Security Architecture"),
    team: str = Query(default="Platform Cryptography"),
    principal: Principal = Depends(require_analyst),
) -> ScanSummary:
    root = _validate_scan_path(REFERENCE_PATH)
    return await run_directory_scan(
        root,
        display_name,
        [],
        RiskContext(
            data_lifetime_years=data_lifetime_years,
            migration_time_years=migration_time_years,
            quantum_horizon_years=quantum_horizon_years,
            data_sensitivity=data_sensitivity,
            business_criticality=business_criticality,
            public_exposure=public_exposure,
            confidentiality_required=confidentiality_required,
            context_profile=context_profile,
            assumption_basis=assumption_basis,
        ),
        metadata={
            "environment": environment,
            "owner": owner,
            "team": team,
            "source": "Reference enterprise workspace",
            "reference": "true",
        },
        organization_id=principal.organization_id,
        created_by_user_id=principal.user_id,
    )


@router.post("/directory", response_model=ScanSummary)
async def directory_scan(payload: DirectoryScanPayload, principal: Principal = Depends(require_analyst)) -> ScanSummary:
    root = _validate_scan_path(payload.path)
    return await run_directory_scan(
        root,
        payload.display_name or root.name,
        payload.scanner_ids,
        payload.risk_context,
        metadata={"environment": payload.environment, "owner": payload.owner, "team": payload.team, "source": payload.source_name},
        organization_id=principal.organization_id,
        created_by_user_id=principal.user_id,
    )


@router.post("/bom", response_model=ScanSummary)
async def bom_scan(payload: BomScanPayload, principal: Principal = Depends(require_analyst)) -> ScanSummary:
    path = _validate_scan_path(payload.path)
    scanners = select_scanners(("bom.cyclonedx",))
    request = ScanRequest(
        target=ScanTarget(
            kind=TargetKind.BOM,
            locator=str(path),
            display_name=payload.display_name or path.name,
            metadata={"environment": payload.environment, "owner": payload.owner, "team": payload.team, "source": payload.source_name},
        ),
        scanner_ids=("bom.cyclonedx",),
    )
    from ecdat.graph.memory import InMemoryGraphStore
    summary = await ScanPipeline(scanners=scanners, graph_store=InMemoryGraphStore(), risk_engine=QuantumRiskEngine()).run(request, payload.risk_context)
    catalog.put(summary, principal.organization_id, principal.user_id)
    return summary


@router.get("", response_model=list[ScanHistoryItem])
async def scan_history(limit: int = Query(default=20, ge=1, le=100), principal: Principal = Depends(require_authenticated)) -> list[ScanHistoryItem]:
    items: list[ScanHistoryItem] = []
    for summary, created_at in catalog.list(limit, principal.organization_id):
        q = summary.quantum_summary
        metadata = summary.target.metadata
        coverage = summary.coverage
        items.append(ScanHistoryItem(
            scan_id=summary.scan_id,
            created_at=created_at,
            status=summary.status.value,
            target_kind=summary.target.kind,
            display_name=summary.target.display_name or Path(summary.target.locator).name or summary.target.locator,
            locator=summary.target.locator,
            source=str(metadata.get("source", summary.target.kind)),
            environment=str(metadata.get("environment", "Unspecified")),
            owner=str(metadata.get("owner", "Unassigned")),
            team=str(metadata.get("team", "Unassigned")),
            assets=len(summary.findings),
            vulnerable=q.vulnerable_assets if q else 0,
            hndl=q.hndl_exposed_assets if q else 0,
            blockers=q.migration_blockers if q else 0,
            critical=q.critical_assets if q else 0,
            evidence_count=coverage.evidence_records if coverage else sum(len(item.evidence) for item in summary.findings),
            average_confidence=coverage.confidence_average if coverage else ((sum(item.confidence.score for item in summary.findings) / len(summary.findings)) if summary.findings else None),
            files_observed=coverage.files_observed if coverage else 0,
            context_manifest_loaded=summary.context_manifest_loaded,
        ))
    return items


def _asset_identity(summary: ScanSummary) -> dict[str, AssetDelta]:
    result: dict[str, AssetDelta] = {}
    for finding in summary.findings:
        asset = finding.asset
        identity = "|".join([asset.asset_type.value, asset.canonical_name.strip().lower(), (asset.version or "").strip().lower(), str(asset.key_size_bits or ""), (asset.mode or "").strip().lower()])
        result[identity] = AssetDelta(identity=identity, name=asset.canonical_name, asset_type=asset.asset_type.value, version=asset.version)
    return result


@router.get("/compare", response_model=ScanComparison)
async def compare_scans(base_id: UUID, target_id: UUID, principal: Principal = Depends(require_authenticated)) -> ScanComparison:
    base = catalog.get(base_id, principal.organization_id)
    target = catalog.get(target_id, principal.organization_id)
    if base is None or target is None:
        raise HTTPException(status_code=404, detail="One or both assessments were not found.")
    left, right = _asset_identity(base), _asset_identity(target)
    new_keys, resolved_keys = sorted(set(right) - set(left)), sorted(set(left) - set(right))
    bq, tq = base.quantum_summary, target.quantum_summary
    return ScanComparison(
        base_scan_id=base.scan_id,
        target_scan_id=target.scan_id,
        new_assets=tuple(right[key] for key in new_keys),
        resolved_assets=tuple(left[key] for key in resolved_keys),
        unchanged_assets=len(set(left) & set(right)),
        asset_delta=len(right) - len(left),
        vulnerable_delta=(tq.vulnerable_assets if tq else 0) - (bq.vulnerable_assets if bq else 0),
        hndl_delta=(tq.hndl_exposed_assets if tq else 0) - (bq.hndl_exposed_assets if bq else 0),
        blocker_delta=(tq.migration_blockers if tq else 0) - (bq.migration_blockers if bq else 0),
        critical_delta=(tq.critical_assets if tq else 0) - (bq.critical_assets if bq else 0),
    )


@router.get("/latest", response_model=ScanSummary)
async def latest_scan(principal: Principal = Depends(require_authenticated)) -> ScanSummary:
    summary = catalog.latest(principal.organization_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="No assessments have been executed yet.")
    return summary


@router.get("/{scan_id}", response_model=ScanSummary)
async def get_scan(scan_id: UUID, principal: Principal = Depends(require_authenticated)) -> ScanSummary:
    summary = catalog.get(scan_id, principal.organization_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Assessment not found.")
    return summary
