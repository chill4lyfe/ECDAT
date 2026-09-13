from __future__ import annotations

from collections.abc import Iterable

from ecdat.scanners.base import Scanner
from ecdat.scanners.binaries.scanner import BinaryHeuristicScanner
from ecdat.scanners.bom import CycloneDXBomScanner
from ecdat.scanners.certificates.scanner import CertificateScanner
from ecdat.scanners.containers.image_archive import ContainerImageArchiveScanner
from ecdat.scanners.containers.scanner import ContainerDefinitionScanner
from ecdat.scanners.connectors.scanner import EnterpriseConnectorScanner
from ecdat.scanners.dependencies.scanner import DependencyScanner
from ecdat.scanners.protocols.scanner import ProtocolConfigScanner
from ecdat.scanners.source.scanner import SourceCodeScanner


def discovery_scanners() -> tuple[Scanner, ...]:
    return (
        SourceCodeScanner(),
        DependencyScanner(),
        ProtocolConfigScanner(),
        CertificateScanner(),
        ContainerDefinitionScanner(),
        ContainerImageArchiveScanner(),
        BinaryHeuristicScanner(),
        EnterpriseConnectorScanner(),
        CycloneDXBomScanner(),
    )


def select_scanners(scanner_ids: Iterable[str] | None = None) -> tuple[Scanner, ...]:
    scanners = discovery_scanners()
    requested = set(scanner_ids or ())
    if not requested:
        return scanners
    return tuple(scanner for scanner in scanners if scanner.scanner_id in requested)
