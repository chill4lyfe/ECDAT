from __future__ import annotations

from time import perf_counter

from ecdat.domain.enums import QuantumPosture, RiskPriority, ScanStatus
from ecdat.domain.models import (
    QuantumRiskSummary,
    RiskContext,
    ScanRequest,
    ScanSummary,
    ScannerExecution,
)
from ecdat.graph.analysis import GraphAnalyzer
from ecdat.graph.builder import EnterpriseGraphBuilder
from ecdat.graph.contracts import GraphStore
from ecdat.normalization.normalizer import FindingNormalizer
from ecdat.orchestration.coverage import build_coverage
from ecdat.risk.contracts import RiskEngine
from ecdat.scanners.base import Scanner


class ScanPipeline:
    def __init__(
        self,
        *,
        scanners: tuple[Scanner, ...],
        graph_store: GraphStore,
        risk_engine: RiskEngine,
        normalizer: FindingNormalizer | None = None,
        graph_builder: EnterpriseGraphBuilder | None = None,
        graph_analyzer: GraphAnalyzer | None = None,
    ) -> None:
        self.scanners = scanners
        self.graph_store = graph_store
        self.risk_engine = risk_engine
        self.normalizer = normalizer or FindingNormalizer()
        self.graph_builder = graph_builder or EnterpriseGraphBuilder()
        self.graph_analyzer = graph_analyzer or GraphAnalyzer()

    async def run(self, request: ScanRequest, risk_context: RiskContext) -> ScanSummary:
        raw = []
        executions: list[ScannerExecution] = []
        applicable = [scanner for scanner in self.scanners if request.target.kind in scanner.capabilities.target_kinds]

        for scanner in applicable:
            started = perf_counter()
            try:
                scanner_findings = await scanner.scan(request)
                raw.extend(scanner_findings)
                executions.append(
                    ScannerExecution(
                        scanner_id=scanner.scanner_id,
                        status="completed",
                        finding_count=len(scanner_findings),
                        duration_ms=(perf_counter() - started) * 1000,
                    )
                )
            except Exception as exc:  # scanner isolation is deliberate
                executions.append(
                    ScannerExecution(
                        scanner_id=scanner.scanner_id,
                        status="failed",
                        finding_count=0,
                        duration_ms=(perf_counter() - started) * 1000,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )

        findings = self.normalizer.normalize(tuple(raw))
        graph = self.graph_builder.build(request.target, findings, risk_context)
        for node in graph.nodes:
            await self.graph_store.upsert_node(node)
        for edge in graph.edges:
            await self.graph_store.upsert_edge(edge)
        nodes, edges = await self.graph_store.snapshot()
        graph_insights = self.graph_analyzer.analyze(nodes, edges)

        assessments = tuple(
            self.risk_engine.assess(
                finding.asset,
                graph.asset_contexts.get(finding.asset.id, risk_context),
            )
            for finding in findings
        )

        failed = [execution for execution in executions if execution.status == "failed"]
        if executions and len(failed) == len(executions):
            status = ScanStatus.FAILED
        elif failed:
            status = ScanStatus.PARTIAL
        else:
            status = ScanStatus.COMPLETED

        quantum_summary = QuantumRiskSummary(
            vulnerable_assets=sum(item.quantum_posture is QuantumPosture.VULNERABLE for item in assessments),
            hndl_exposed_assets=sum(item.hndl_exposure for item in assessments),
            critical_assets=sum(item.priority is RiskPriority.CRITICAL for item in assessments),
            elevated_assets=sum(item.priority is RiskPriority.ELEVATED for item in assessments),
            migration_blockers=sum(item.migration_blocker for item in graph_insights),
        )

        coverage = build_coverage(request, findings, tuple(executions))

        return ScanSummary(
            scan_id=request.id,
            status=status,
            target=request.target,
            findings=findings,
            graph_nodes=nodes,
            graph_edges=edges,
            risk_assessments=assessments,
            scanner_executions=tuple(executions),
            graph_insights=graph_insights,
            quantum_summary=quantum_summary,
            context_manifest_loaded=graph.manifest_loaded,
            coverage=coverage,
        )
