import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from ecdat.api.catalog import catalog
from ecdat.auth.security import Principal, require_authenticated
from ecdat.integrations.cyclonedx.exporter import CycloneDXExporter

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/scans/{scan_id}/cyclonedx")
async def export_cyclonedx(scan_id: UUID, principal: Principal = Depends(require_authenticated)) -> Response:
    summary = catalog.get(scan_id, principal.organization_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Assessment not found.")
    payload = json.dumps(CycloneDXExporter().export(summary), indent=2, sort_keys=False)
    return Response(payload, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="ecdat-{scan_id}-cyclonedx.json"'})
