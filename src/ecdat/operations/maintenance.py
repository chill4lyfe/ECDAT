from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import SQLAlchemyError

from ecdat.api.catalog import catalog
from ecdat.auth.security import verify_password
from ecdat.migration.catalog import migration_catalog
from ecdat.persistence.sql.models import MigrationPlanRecord, ScanRecord, UserRecord
from ecdat.persistence.sql.session import SessionLocal
from ecdat.settings import get_settings


@dataclass(frozen=True)
class AssessmentResetResult:
    scans_deleted: int
    migration_plans_deleted: int
    graph_nodes_deleted: int
    graph_edges_deleted: int
    intake_workspaces_deleted: int = 0
    graph_cleanup_warning: str | None = None


def _graph_ids(records: list[ScanRecord]) -> tuple[set[str], set[str]]:
    node_ids: set[str] = set()
    edge_ids: set[str] = set()
    for record in records:
        payload = record.summary_json or {}
        for item in payload.get("graph_nodes", ()):
            if isinstance(item, dict) and item.get("id"):
                node_ids.add(str(item["id"]))
        for item in payload.get("graph_edges", ()):
            if isinstance(item, dict) and item.get("id"):
                edge_ids.add(str(item["id"]))
    return node_ids, edge_ids


def _managed_intake_roots(records: list[ScanRecord], organization_id: UUID) -> set[Path]:
    intake_root = Path(get_settings().intake_dir).resolve()
    roots: set[Path] = set()
    for record in records:
        payload = record.summary_json or {}
        target = payload.get("target") if isinstance(payload, dict) else None
        if not isinstance(target, dict):
            continue
        metadata = target.get("metadata")
        managed = metadata.get("managed_intake_root") if isinstance(metadata, dict) else None
        candidates: list[Path] = []
        if isinstance(managed, str) and managed.strip():
            candidates.append(Path(managed).expanduser())
        locator = target.get("locator")
        if isinstance(locator, str) and locator.strip():
            try:
                resolved_locator = Path(locator).expanduser().resolve()
                relative = resolved_locator.relative_to(intake_root)
                parts = relative.parts
                if parts[:1] == ("organizations",) and len(parts) >= 3:
                    candidates.append(intake_root / "organizations" / parts[1] / parts[2])
                elif parts:
                    candidates.append(intake_root / parts[0])
            except (OSError, ValueError):
                pass
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
                relative = resolved.relative_to(intake_root)
            except (OSError, ValueError):
                continue
            if resolved == intake_root or len(relative.parts) < 1:
                continue
            if relative.parts[:1] == ("organizations",):
                if len(relative.parts) < 3 or relative.parts[1] != str(organization_id):
                    continue
            roots.add(resolved)
    return roots



async def reset_organization_assessment_data(
    organization_id: UUID,
    user_id: UUID,
    current_password: str,
) -> AssessmentResetResult:
    """Remove one organization's assessment state while retaining identity/RBAC data.

    PostgreSQL is authoritative for history and migration-plan persistence. Neo4j cleanup
    removes only graph IDs that are not referenced by another organization's persisted
    scan summaries, which avoids deleting a shared legacy graph entity.
    """
    if SessionLocal is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Persistence database is unavailable.")

    try:
        with SessionLocal() as session:
            user = session.get(UserRecord, user_id)
            if user is None or not user.is_active or not verify_password(current_password, user.password_hash):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect.")

            target_scans = session.scalars(
                select(ScanRecord).where(ScanRecord.organization_id == organization_id)
            ).all()
            other_scans = session.scalars(
                select(ScanRecord).where(
                    or_(ScanRecord.organization_id != organization_id, ScanRecord.organization_id.is_(None))
                )
            ).all()
            managed_intake_roots = _managed_intake_roots(list(target_scans), organization_id)
            target_nodes, target_edges = _graph_ids(list(target_scans))
            other_nodes, other_edges = _graph_ids(list(other_scans))
            exclusive_nodes = target_nodes - other_nodes
            exclusive_edges = target_edges - other_edges

            plans = session.scalars(
                select(MigrationPlanRecord.id).where(MigrationPlanRecord.organization_id == organization_id)
            ).all()
            scans_deleted = len(target_scans)
            plans_deleted = len(plans)

            session.execute(delete(MigrationPlanRecord).where(MigrationPlanRecord.organization_id == organization_id))
            session.execute(delete(ScanRecord).where(ScanRecord.organization_id == organization_id))
            session.commit()
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Assessment data could not be reset.") from exc

    # Durable state is gone; now remove same-process caches so stale results cannot reappear.
    catalog.clear_organization(organization_id)
    migration_catalog.clear_organization(organization_id)

    intake_workspaces_deleted = 0
    for managed_root in managed_intake_roots:
        if managed_root.exists():
            shutil.rmtree(managed_root, ignore_errors=True)
            if not managed_root.exists():
                intake_workspaces_deleted += 1

    graph_nodes_deleted = 0
    graph_edges_deleted = 0
    warning: str | None = None
    try:
        from ecdat.persistence.graph.neo4j import Neo4jGraphStore
        graph_store = Neo4jGraphStore()
    except Exception:
        graph_store = None
        warning = "Assessment history was cleared, but retained Neo4j cache entries could not be purged. They are not available through organization history and can be removed during maintenance."

    try:
        if graph_store is None:
            return AssessmentResetResult(
                scans_deleted=scans_deleted,
                migration_plans_deleted=plans_deleted,
                graph_nodes_deleted=0,
                graph_edges_deleted=0,
                intake_workspaces_deleted=intake_workspaces_deleted,
                graph_cleanup_warning=warning,
            )
        graph_nodes_deleted, graph_edges_deleted = await graph_store.purge_entities(exclusive_nodes, exclusive_edges)
    except Exception:
        # Graph persistence is derivative of scan summaries. Do not resurrect SQL history if
        # Neo4j is temporarily unavailable; disclose the cleanup limitation to the operator.
        warning = "Assessment history was cleared, but retained Neo4j cache entries could not be purged. They are not available through organization history and can be removed during maintenance."
    finally:
        if graph_store is not None:
            try:
                await graph_store.close()
            except Exception:
                pass

    return AssessmentResetResult(
        scans_deleted=scans_deleted,
        migration_plans_deleted=plans_deleted,
        graph_nodes_deleted=graph_nodes_deleted,
        graph_edges_deleted=graph_edges_deleted,
        intake_workspaces_deleted=intake_workspaces_deleted,
        graph_cleanup_warning=warning,
    )
