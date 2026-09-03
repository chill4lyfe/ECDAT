from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from ecdat.domain.models import Confidence


class MigrationModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MigrationConstraints(MigrationModel):
    mode: Literal["balanced", "conservative", "performance"] = "balanced"
    prefer_hybrid: bool = True
    max_parallel_actions: int = Field(default=3, ge=1, le=8)
    change_window_weeks: int = Field(default=12, ge=1, le=52)


class TargetProfile(MigrationModel):
    name: str
    category: Literal["kem", "signature", "hybrid_tls", "classical", "retain", "review"]
    standard: str
    maturity: Literal["standardized", "transitional", "review"]
    purpose: str
    operational_notes: tuple[str, ...] = ()


class MigrationRecommendation(MigrationModel):
    asset_id: UUID
    current_primitive: str
    strategy: Literal[
        "hybrid_transition",
        "pqc_transition",
        "classical_remediation",
        "retain_monitor",
        "context_review",
    ]
    priority_score: int = Field(ge=0, le=100)
    target_profiles: tuple[TargetProfile, ...]
    rationale: tuple[str, ...]
    prerequisites: tuple[str, ...] = ()
    interoperability_notes: tuple[str, ...] = ()
    performance_notes: tuple[str, ...] = ()
    effort_points: int = Field(ge=1, le=21)
    confidence: Confidence
    standards_basis: tuple[str, ...] = ()
    recommendation_version: str = "migration-intelligence.v2"


class AgilityFactor(MigrationModel):
    code: str
    label: str
    impact: int = Field(ge=-40, le=20)
    rationale: str


class CryptoAgilityScore(MigrationModel):
    node_id: str
    label: str
    score: int = Field(ge=0, le=100)
    difficulty: Literal["low", "moderate", "high", "critical"]
    coverage: Literal["partial", "good"]
    factors: tuple[AgilityFactor, ...]


class MigrationAction(MigrationModel):
    id: str
    wave: int = Field(ge=1)
    node_id: str
    label: str
    action_type: str
    asset_ids: tuple[UUID, ...]
    priority_score: int = Field(ge=0, le=100)
    effort_points: int = Field(ge=1)
    estimated_weeks: int = Field(ge=1)
    within_change_window: bool = True
    prerequisite_action_ids: tuple[str, ...] = ()
    affected_service_ids: tuple[str, ...] = ()
    target_profiles: tuple[str, ...] = ()
    rationale: tuple[str, ...] = ()


class MigrationWave(MigrationModel):
    wave: int = Field(ge=1)
    title: str
    actions: tuple[MigrationAction, ...]
    estimated_effort_points: int = Field(ge=0)
    parallel_slots: int = Field(ge=1)
    estimated_duration_weeks: int = Field(ge=1)
    starts_week: int = Field(ge=1)
    ends_week: int = Field(ge=1)
    within_change_window: bool = True


class MigrationPlanSummary(MigrationModel):
    total_actions: int = Field(ge=0)
    immediate_actions: int = Field(ge=0)
    hybrid_actions: int = Field(ge=0)
    pqc_actions: int = Field(ge=0)
    classical_remediations: int = Field(ge=0)
    total_effort_points: int = Field(ge=0)
    lowest_agility_score: int | None = Field(default=None, ge=0, le=100)
    estimated_calendar_weeks: int = Field(default=0, ge=0)
    actions_within_window: int = Field(default=0, ge=0)
    deferred_actions: int = Field(default=0, ge=0)


class MigrationRoadmap(MigrationModel):
    plan_id: UUID = Field(default_factory=uuid4)
    scan_id: UUID
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    risk_scenario_horizon_years: float | None = Field(default=None, gt=0)
    constraints: MigrationConstraints
    recommendations: tuple[MigrationRecommendation, ...]
    agility_scores: tuple[CryptoAgilityScore, ...]
    waves: tuple[MigrationWave, ...]
    critical_path: tuple[str, ...]
    summary: MigrationPlanSummary
    strategy_explanation: tuple[str, ...] = ()
    standards_snapshot: tuple[str, ...] = (
        "NIST FIPS 203 (ML-KEM)",
        "NIST FIPS 204 (ML-DSA)",
        "NIST FIPS 205 (SLH-DSA)",
        "IETF RFC 10024 (TLS 1.3 PQ/T hybrid ECDHE-MLKEM groups)",
    )
