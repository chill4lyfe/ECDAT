from ecdat.migration.models import MigrationConstraints
from ecdat.migration.planner import MigrationPlanner
from tests.test_discovery_reference import reference_summary


async def test_planning_mode_changes_target_profiles_and_effort() -> None:
    summary = await reference_summary()
    planner = MigrationPlanner()
    performance = planner.build(summary, MigrationConstraints(mode="performance", prefer_hybrid=True, max_parallel_actions=3, change_window_weeks=12))
    balanced = planner.build(summary, MigrationConstraints(mode="balanced", prefer_hybrid=True, max_parallel_actions=3, change_window_weeks=12))
    conservative = planner.build(summary, MigrationConstraints(mode="conservative", prefer_hybrid=True, max_parallel_actions=3, change_window_weeks=12))
    perf_targets = {p.name for r in performance.recommendations for p in r.target_profiles}
    balanced_targets = {p.name for r in balanced.recommendations for p in r.target_profiles}
    conservative_targets = {p.name for r in conservative.recommendations for p in r.target_profiles}
    assert any("ML-KEM-512" in name for name in perf_targets)
    assert any("ML-KEM-768" in name for name in balanced_targets)
    assert any("ML-KEM-1024" in name for name in conservative_targets)
    assert performance.summary.total_effort_points < balanced.summary.total_effort_points < conservative.summary.total_effort_points
    assert conservative.summary.estimated_calendar_weeks >= balanced.summary.estimated_calendar_weeks


async def test_parallelism_and_change_window_change_schedule() -> None:
    summary = await reference_summary()
    planner = MigrationPlanner()
    serial = planner.build(summary, MigrationConstraints(mode="balanced", prefer_hybrid=True, max_parallel_actions=1, change_window_weeks=8))
    parallel = planner.build(summary, MigrationConstraints(mode="balanced", prefer_hybrid=True, max_parallel_actions=5, change_window_weeks=8))
    assert serial.summary.estimated_calendar_weeks > parallel.summary.estimated_calendar_weeks
    assert serial.summary.deferred_actions > parallel.summary.deferred_actions
    assert len(serial.waves) >= 2


async def test_hybrid_preference_changes_key_establishment_strategy() -> None:
    summary = await reference_summary()
    planner = MigrationPlanner()
    hybrid = planner.build(summary, MigrationConstraints(mode="balanced", prefer_hybrid=True, max_parallel_actions=3, change_window_weeks=12))
    direct = planner.build(summary, MigrationConstraints(mode="balanced", prefer_hybrid=False, max_parallel_actions=3, change_window_weeks=12))
    assert hybrid.summary.hybrid_actions > direct.summary.hybrid_actions


async def test_quantum_horizon_propagates_into_migration_prioritization() -> None:
    from ecdat.api.catalog import catalog
    from ecdat.api.routes.migration import MigrationPlanPayload, create_plan

    summary = await reference_summary()
    catalog.put(summary)
    short = await create_plan(MigrationPlanPayload(
        scan_id=summary.scan_id,
        quantum_horizon_years=10,
        constraints=MigrationConstraints(mode="balanced"),
    ))
    long = await create_plan(MigrationPlanPayload(
        scan_id=summary.scan_id,
        quantum_horizon_years=20,
        constraints=MigrationConstraints(mode="balanced"),
    ))

    assert short.scan_id == long.scan_id == summary.scan_id
    assert short.risk_scenario_horizon_years == 10
    assert long.risk_scenario_horizon_years == 20
    short_scores = {item.asset_id: item.priority_score for item in short.recommendations}
    long_scores = {item.asset_id: item.priority_score for item in long.recommendations}
    assert any(short_scores[asset_id] > long_scores[asset_id] for asset_id in short_scores.keys() & long_scores.keys())
    assert [item.id for item in short.waves[0].actions] != [item.id for item in long.waves[0].actions]
