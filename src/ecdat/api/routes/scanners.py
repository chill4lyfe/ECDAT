from fastapi import APIRouter

from ecdat.scanners.registry import discovery_scanners

router = APIRouter(prefix="/scanners", tags=["scanners"])


@router.get("")
async def list_scanners() -> list[dict[str, object]]:
    return [
        {
            "scanner_id": scanner.scanner_id,
            "version": scanner.version,
            "target_kinds": sorted(kind.value for kind in scanner.capabilities.target_kinds),
            "deterministic": scanner.capabilities.deterministic,
            "emits_raw_secret_material": scanner.capabilities.emits_raw_secret_material,
        }
        for scanner in discovery_scanners()
    ]
