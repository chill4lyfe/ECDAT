from uuid import uuid4

import ecdat.api.catalog as catalog_module
from ecdat.api.catalog import ScanCatalog
from ecdat.migration.models import MigrationConstraints
from ecdat.migration.planner import MigrationPlanner
from ecdat.risk.scenario import evaluate_scenario
from tests.test_discovery_reference import reference_summary


async def test_scenario_and_roadmap_revisions_do_not_create_assessment_history(monkeypatch) -> None:
    monkeypatch.setattr(catalog_module, "SessionLocal", None)
    history = ScanCatalog()
    summary = await reference_summary()
    history.put(summary)
    assert len(history.list()) == 1

    scenario = evaluate_scenario(summary, 10)
    roadmap = MigrationPlanner().build(summary, MigrationConstraints(mode="conservative"))
    assert scenario.scan_id == summary.scan_id
    assert roadmap.scan_id == summary.scan_id
    assert len(history.list()) == 1

    second_assessment = summary.model_copy(update={"scan_id": uuid4()})
    history.put(second_assessment)
    assert len(history.list()) == 2
