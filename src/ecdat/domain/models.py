from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    AssetType,
    ConfidenceLevel,
    GraphEdgeType,
    GraphNodeType,
    QuantumPosture,
    RiskPriority,
    ScanStatus,
    TargetKind,
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceLocation(FrozenModel):
    uri: str
    path: str | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    symbol: str | None = None


class Evidence(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    detector: str
    detector_version: str
    method: str
    location: SourceLocation
    fingerprint: str
    summary: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Confidence(FrozenModel):
    level: ConfidenceLevel
    score: float = Field(ge=0.0, le=1.0)
    reasons: tuple[str, ...] = ()


class CryptoAsset(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    asset_type: AssetType
    canonical_name: str
    version: str | None = None
    algorithm_family: str | None = None
    key_size_bits: int | None = Field(default=None, gt=0)
    mode: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class Finding(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    scanner_id: str
    title: str
    asset: CryptoAsset
    evidence: tuple[Evidence, ...]
    confidence: Confidence
    tags: tuple[str, ...] = ()


class ScanTarget(FrozenModel):
    kind: TargetKind
    locator: str
    display_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScanRequest(FrozenModel):
    id: UUID = Field(default_factory=uuid4)
    target: ScanTarget
    scanner_ids: tuple[str, ...] = ()
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GraphNode(FrozenModel):
    id: str
    node_type: GraphNodeType
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(FrozenModel):
    id: str
    source_id: str
    target_id: str
    edge_type: GraphEdgeType
    properties: dict[str, Any] = Field(default_factory=dict)


class RiskContext(FrozenModel):
    data_lifetime_years: float | None = Field(default=None, ge=0)
    migration_time_years: float | None = Field(default=None, ge=0)
    quantum_horizon_years: float | None = Field(default=None, gt=0)
    data_sensitivity: str | None = None
    business_criticality: str | None = None
    public_exposure: bool | None = None
    confidentiality_required: bool | None = None


class RiskFactor(FrozenModel):
    code: str
    label: str
    contribution: int
    rationale: str


class RiskAssessment(FrozenModel):
    asset_id: UUID
    priority: RiskPriority
    model_version: str
    rationale: tuple[str, ...]
    assumptions: dict[str, Any] = Field(default_factory=dict)
    score: int | None = Field(default=None, ge=0, le=100)
    quantum_posture: QuantumPosture = QuantumPosture.UNKNOWN
    hndl_exposure: bool = False
    mosca_margin_years: float | None = None
    factors: tuple[RiskFactor, ...] = ()
    computed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GraphInsight(FrozenModel):
    node_id: str
    degree: int = Field(ge=0)
    inbound: int = Field(ge=0)
    outbound: int = Field(ge=0)
    blast_radius: int = Field(ge=0)
    centrality: float = Field(ge=0.0, le=1.0)
    migration_blocker: bool = False
    reasons: tuple[str, ...] = ()


class QuantumRiskSummary(FrozenModel):
    vulnerable_assets: int = Field(ge=0)
    hndl_exposed_assets: int = Field(ge=0)
    critical_assets: int = Field(ge=0)
    elevated_assets: int = Field(ge=0)
    migration_blockers: int = Field(ge=0)


class ScannerExecution(FrozenModel):
    scanner_id: str
    status: str
    finding_count: int = Field(ge=0)
    duration_ms: float = Field(ge=0)
    error: str | None = None




class ScanCoverage(FrozenModel):
    files_observed: int = Field(default=0, ge=0)
    source_files: int = Field(default=0, ge=0)
    config_files: int = Field(default=0, ge=0)
    dependency_manifests: int = Field(default=0, ge=0)
    certificate_files: int = Field(default=0, ge=0)
    binary_files: int = Field(default=0, ge=0)
    container_definitions: int = Field(default=0, ge=0)
    scanners_completed: int = Field(default=0, ge=0)
    scanners_failed: int = Field(default=0, ge=0)
    evidence_records: int = Field(default=0, ge=0)
    confidence_average: float | None = Field(default=None, ge=0.0, le=1.0)
    observations: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


class ScanSummary(FrozenModel):
    scan_id: UUID
    status: ScanStatus
    target: ScanTarget
    findings: tuple[Finding, ...]
    graph_nodes: tuple[GraphNode, ...]
    graph_edges: tuple[GraphEdge, ...]
    risk_assessments: tuple[RiskAssessment, ...]
    scanner_executions: tuple[ScannerExecution, ...] = ()
    graph_insights: tuple[GraphInsight, ...] = ()
    quantum_summary: QuantumRiskSummary | None = None
    context_manifest_loaded: bool = False
    coverage: ScanCoverage | None = None
