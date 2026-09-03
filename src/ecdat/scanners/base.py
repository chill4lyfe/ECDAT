from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ecdat.domain.enums import TargetKind
from ecdat.domain.models import Finding, ScanRequest


@dataclass(frozen=True, slots=True)
class ScannerCapabilities:
    target_kinds: frozenset[TargetKind]
    deterministic: bool
    emits_raw_secret_material: bool = False


class Scanner(Protocol):
    scanner_id: str
    version: str
    capabilities: ScannerCapabilities

    async def scan(self, request: ScanRequest) -> tuple[Finding, ...]: ...
