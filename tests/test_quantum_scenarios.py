from ecdat.risk.scenario import evaluate_scenario
from tests.test_discovery_reference import reference_summary


async def test_horizon_scenario_changes_priorities_without_changing_evidence_snapshot() -> None:
    summary = await reference_summary()
    short = evaluate_scenario(summary, 10)
    long = evaluate_scenario(summary, 20)
    assert short.scan_id == summary.scan_id == long.scan_id
    assert short.changed_assets > 0
    assert long.changed_assets > 0
    assert short.quantum_summary.critical_assets > long.quantum_summary.critical_assets
    assert short.quantum_summary.hndl_exposed_assets > long.quantum_summary.hndl_exposed_assets
    assert short.priority_increases > 0
    assert long.priority_decreases > 0


async def test_baseline_horizon_is_deterministic_no_change() -> None:
    summary = await reference_summary()
    same = evaluate_scenario(summary, 15)
    assert same.changed_assets == 0
    assert same.narrative.unchanged_explanation
