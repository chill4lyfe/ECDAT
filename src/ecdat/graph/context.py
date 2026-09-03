from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ecdat.domain.models import RiskContext


class ContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DataClassContext(ContextModel):
    id: str
    name: str
    sensitivity: str = "medium"
    lifetime_years: float = Field(ge=0)


class ServiceContext(ContextModel):
    id: str
    name: str
    path_prefixes: list[str] = Field(default_factory=list)
    business_criticality: str = "medium"
    public_exposure: bool = False
    confidentiality_required: bool = True
    migration_time_years: float = Field(default=3.0, ge=0)
    protects: list[str] = Field(default_factory=list)
    kind: str = "service"


class RelationshipContext(ContextModel):
    source: str
    target: str
    type: str = "depends_on"


class EnterpriseContextManifest(ContextModel):
    schema_name: str = Field(default="ecdat.context.v1", alias="schema")
    services: list[ServiceContext] = Field(default_factory=list)
    data_classes: list[DataClassContext] = Field(default_factory=list)
    relationships: list[RelationshipContext] = Field(default_factory=list)

    def service_for_path(self, path: str | None) -> ServiceContext | None:
        if not path:
            return None
        normalized = path.replace("\\", "/").lstrip("./")
        best: tuple[int, ServiceContext] | None = None
        for service in self.services:
            for prefix in service.path_prefixes:
                candidate = prefix.replace("\\", "/").lstrip("./")
                if normalized.startswith(candidate):
                    score = len(candidate)
                    if best is None or score > best[0]:
                        best = (score, service)
        return best[1] if best else None

    def risk_context_for_service(
        self,
        service: ServiceContext | None,
        fallback: RiskContext,
    ) -> RiskContext:
        if service is None:
            return fallback
        data_by_id = {item.id: item for item in self.data_classes}
        protected = [data_by_id[item] for item in service.protects if item in data_by_id]
        lifetime = max((item.lifetime_years for item in protected), default=fallback.data_lifetime_years)
        sensitivity = max(
            (item.sensitivity for item in protected),
            key=lambda value: {"low": 0, "medium": 1, "high": 2, "critical": 3, "restricted": 4}.get(value.lower(), 1),
            default=fallback.data_sensitivity,
        )
        return fallback.model_copy(
            update={
                "data_lifetime_years": lifetime,
                "migration_time_years": service.migration_time_years,
                "data_sensitivity": sensitivity,
                "business_criticality": service.business_criticality,
                "public_exposure": service.public_exposure,
                "confidentiality_required": service.confidentiality_required,
            }
        )


def load_context_manifest(target_locator: str) -> EnterpriseContextManifest | None:
    root = Path(target_locator)
    if not root.is_dir():
        return None
    path = root / "ecdat.context.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return EnterpriseContextManifest.model_validate(payload)
    except (OSError, ValueError):
        return None
