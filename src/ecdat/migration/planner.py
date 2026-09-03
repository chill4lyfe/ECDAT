from __future__ import annotations

from collections import defaultdict
from math import ceil
from uuid import UUID

from ecdat.domain.enums import GraphEdgeType
from ecdat.domain.models import ScanSummary
from ecdat.migration.agility import CryptoAgilityEngine
from ecdat.migration.models import MigrationAction, MigrationConstraints, MigrationPlanSummary, MigrationRoadmap, MigrationWave
from ecdat.migration.recommendations import MigrationRecommendationEngine


class MigrationPlanner:
    def __init__(self) -> None:
        self.recommendation_engine = MigrationRecommendationEngine()
        self.agility_engine = CryptoAgilityEngine()

    def build(self, summary: ScanSummary, constraints: MigrationConstraints) -> MigrationRoadmap:
        risk_by_asset = {risk.asset_id: risk for risk in summary.risk_assessments}
        insight_by_node = {item.node_id: item for item in summary.graph_insights}
        recommendations = tuple(
            self.recommendation_engine.recommend(finding, risk_by_asset[finding.asset.id], constraints)
            for finding in summary.findings if finding.asset.id in risk_by_asset
        )
        owners: dict[UUID, set[str]] = defaultdict(set)
        for edge in summary.graph_edges:
            if edge.edge_type is GraphEdgeType.USES and edge.target_id.startswith("asset:") and edge.source_id.startswith("service:"):
                try:
                    owners[UUID(edge.target_id.removeprefix("asset:"))].add(edge.source_id)
                except ValueError:
                    continue

        candidates = [
            rec for rec in recommendations
            if rec.strategy != "retain_monitor" and (rec.priority_score >= 30 or rec.strategy in {"classical_remediation", "context_review"})
        ]
        action_by_asset: dict[UUID, str] = {}
        staged: list[dict[str, object]] = []
        for rec in candidates:
            asset_node = f"asset:{rec.asset_id}"
            service_ids = tuple(sorted(owners.get(rec.asset_id, set())))
            blocker = insight_by_node.get(asset_node)
            blocker_bonus = 12 if blocker and blocker.migration_blocker else 0
            breadth_bonus = min(10, len(service_ids) * 3)
            effective = min(100, rec.priority_score + blocker_bonus + breadth_bonus)
            action_id = f"migrate:{str(rec.asset_id)[:8]}"
            action_by_asset[rec.asset_id] = action_id
            staged.append({"rec": rec, "services": service_ids, "score": effective, "id": action_id})

        service_assets: dict[str, list[UUID]] = defaultdict(list)
        for asset_id, service_ids in owners.items():
            if asset_id in action_by_asset:
                for service_id in service_ids:
                    service_assets[service_id].append(asset_id)

        service_prereqs: dict[str, set[str]] = defaultdict(set)
        all_services = {node.id for node in summary.graph_nodes if node.id.startswith("service:")}
        for edge in summary.graph_edges:
            if edge.edge_type is GraphEdgeType.DEPENDS_ON and edge.source_id.startswith("service:") and edge.target_id.startswith("service:"):
                service_prereqs[edge.source_id].add(edge.target_id)

        depth_cache: dict[str, int] = {}
        def service_depth(service_id: str, visiting: set[str] | None = None) -> int:
            if service_id in depth_cache:
                return depth_cache[service_id]
            visiting = set() if visiting is None else visiting
            if service_id in visiting:
                return 1
            dependencies = service_prereqs.get(service_id, set())
            if not dependencies:
                depth_cache[service_id] = 1
                return 1
            depth = 1 + max(service_depth(dep, visiting | {service_id}) for dep in dependencies)
            depth_cache[service_id] = min(depth, 6)
            return depth_cache[service_id]
        for service_id in all_services:
            service_depth(service_id)

        wave_by_action: dict[str, int] = {}
        for item in staged:
            action_id = str(item["id"])
            services = tuple(item["services"])
            rec = item["rec"]
            insight = insight_by_node.get(f"asset:{rec.asset_id}")
            shared_or_blocking = len(services) >= 2 or bool(insight and insight.migration_blocker)
            if shared_or_blocking:
                wave_by_action[action_id] = 1
            elif services:
                wave_by_action[action_id] = max(service_depth(service_id) for service_id in services)
            else:
                wave_by_action[action_id] = 1

        prereq_by_action: dict[str, set[str]] = defaultdict(set)
        for item in staged:
            action_id = str(item["id"])
            current_wave = wave_by_action.get(action_id, 1)
            for service_id in tuple(item["services"]):
                for dependency_service in service_prereqs.get(service_id, set()):
                    for asset_id in service_assets.get(dependency_service, []):
                        dependency_action = action_by_asset.get(asset_id)
                        if dependency_action and dependency_action != action_id and wave_by_action.get(dependency_action, 1) < current_wave:
                            prereq_by_action[action_id].add(dependency_action)

        staged.sort(key=lambda item: (wave_by_action.get(str(item["id"]), 1), -int(item["score"]), -len(item["services"]), str(item["id"])))

        provisional: list[MigrationAction] = []
        for item in staged:
            rec = item["rec"]
            action_id = str(item["id"])
            services = tuple(item["services"])
            estimated_weeks = max(1, ceil(rec.effort_points / max(2, constraints.max_parallel_actions)))
            provisional.append(MigrationAction(
                id=action_id,
                wave=wave_by_action.get(action_id, 1),
                node_id=f"asset:{rec.asset_id}",
                label=f"{rec.strategy.replace('_', ' ').title()}: {rec.current_primitive}",
                action_type=rec.strategy,
                asset_ids=(rec.asset_id,),
                priority_score=int(item["score"]),
                effort_points=rec.effort_points,
                estimated_weeks=estimated_weeks,
                prerequisite_action_ids=tuple(sorted(prereq_by_action.get(action_id, set()))),
                affected_service_ids=services,
                target_profiles=tuple(profile.name for profile in rec.target_profiles),
                rationale=rec.rationale,
            ))

        waves: list[MigrationWave] = []
        current_week = 1
        action_window: dict[str, bool] = {}
        for wave_no in sorted({action.wave for action in provisional}):
            wave_actions_raw = tuple(sorted((action for action in provisional if action.wave == wave_no), key=lambda a: (-a.priority_score, a.label)))
            slots = min(constraints.max_parallel_actions, max(1, len(wave_actions_raw)))
            # Approximate calendar duration from relative effort with bounded parallelism.
            duration = max(1, ceil(sum(action.estimated_weeks for action in wave_actions_raw) / slots))
            starts = current_week
            ends = starts + duration - 1
            within = starts <= constraints.change_window_weeks
            wave_actions = tuple(action.model_copy(update={"within_change_window": starts <= constraints.change_window_weeks}) for action in wave_actions_raw)
            for action in wave_actions:
                action_window[action.id] = action.within_change_window
            title = "Stabilize shared blockers and urgent exposure" if wave_no == 1 else f"Dependency-safe transition wave {wave_no}"
            waves.append(MigrationWave(
                wave=wave_no,
                title=title,
                actions=wave_actions,
                estimated_effort_points=sum(action.effort_points for action in wave_actions),
                parallel_slots=slots,
                estimated_duration_weeks=duration,
                starts_week=starts,
                ends_week=ends,
                within_change_window=within,
            ))
            current_week = ends + 1

        actions = [action for wave in waves for action in wave.actions]
        agility = self.agility_engine.score(summary)
        critical_path = self._critical_path(actions)
        within_count = sum(action.within_change_window for action in actions)
        strategy_explanation = (
            {
                "performance": "Runtime efficiency: favors smaller standardized parameter sets and lower transition overhead where security policy permits.",
                "balanced": "Balanced transition: favors broadly deployable standardized profiles with interoperability safeguards.",
                "conservative": "Risk-minimizing transition: favors stronger parameter sets, staged validation and additional safety checks at higher cost.",
            }[constraints.mode],
            f"Concurrency limit: at most {constraints.max_parallel_actions} migration actions are planned in parallel within a wave.",
            f"Change window: actions starting after week {constraints.change_window_weeks} remain visible but are marked outside the current execution window.",
            "Calendar weeks are planning estimates derived from relative effort points; they are not project commitments and should be replaced with organization-specific delivery estimates.",
        )
        summary_model = MigrationPlanSummary(
            total_actions=len(actions),
            immediate_actions=sum(action.wave == 1 for action in actions),
            hybrid_actions=sum(action.action_type == "hybrid_transition" for action in actions),
            pqc_actions=sum(action.action_type == "pqc_transition" for action in actions),
            classical_remediations=sum(action.action_type == "classical_remediation" for action in actions),
            total_effort_points=sum(action.effort_points for action in actions),
            lowest_agility_score=min((item.score for item in agility), default=None),
            estimated_calendar_weeks=max((wave.ends_week for wave in waves), default=0),
            actions_within_window=within_count,
            deferred_actions=len(actions) - within_count,
        )
        return MigrationRoadmap(
            scan_id=summary.scan_id,
            constraints=constraints,
            recommendations=recommendations,
            agility_scores=agility,
            waves=tuple(waves),
            critical_path=critical_path,
            summary=summary_model,
            strategy_explanation=strategy_explanation,
        )

    def _critical_path(self, actions: list[MigrationAction]) -> tuple[str, ...]:
        if not actions:
            return ()
        by_id = {item.id: item for item in actions}
        memo: dict[str, tuple[str, ...]] = {}
        def path(action_id: str, visiting: set[str]) -> tuple[str, ...]:
            if action_id in memo:
                return memo[action_id]
            if action_id in visiting:
                return (action_id,)
            action = by_id[action_id]
            candidates = [path(item, visiting | {action_id}) for item in action.prerequisite_action_ids if item in by_id]
            best = max(candidates, key=len, default=())
            memo[action_id] = (*best, action_id)
            return memo[action_id]
        return max((path(item.id, set()) for item in actions), key=len, default=())
