"use client";

import { Activity, ArrowUpRight, DatabaseZap, Fingerprint, Import, Play, Route, ShieldAlert, Sparkles, TimerReset, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ForceCryptoGraph } from "@/components/graph/ForceCryptoGraph";
import { AppShell, PageHeader } from "@/components/shell/AppShell";
import { fetchLatestScan, runReferenceAssessment } from "@/lib/api";
import type { GraphNode, RiskAssessment, ScanSummary } from "@/lib/types";

function pct(value: number) { return `${Math.round(value * 100)}%`; }

function assessmentForNode(node: GraphNode | null, risks: RiskAssessment[]) {
  if (!node?.id.startsWith("asset:")) return undefined;
  return risks.find((item) => item.asset_id === node.id.slice("asset:".length));
}

export function DashboardClient() {
  const [summary, setSummary] = useState<ScanSummary | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  useEffect(() => {
    fetchLatestScan().then((value) => {
      setSummary(value);
      if (value?.graph_nodes.length) setSelectedNode(value.graph_nodes.find((node) => node.node_type === "service") ?? value.graph_nodes[0]);
    }).catch(() => undefined);
  }, []);

  const scan = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      const next = await runReferenceAssessment(15);
      setSummary(next);
      setSelectedNode(next.graph_nodes.find((node) => node.node_type === "service") ?? next.graph_nodes[0] ?? null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unknown scan failure");
    } finally {
      setRunning(false);
    }
  }, []);

  const stats = useMemo(() => {
    const q = summary?.quantum_summary;
    return {
      assets: summary?.findings.length ?? 0,
      vulnerable: q?.vulnerable_assets ?? 0,
      hndl: q?.hndl_exposed_assets ?? 0,
      blockers: q?.migration_blockers ?? 0,
    };
  }, [summary]);

  const selectedRisk = assessmentForNode(selectedNode, summary?.risk_assessments ?? []);
  const topRisks = useMemo(() => [...(summary?.risk_assessments ?? [])].sort((a, b) => (b.score ?? 0) - (a.score ?? 0)).slice(0, 5), [summary]);
  const findingByAsset = new Map((summary?.findings ?? []).map((finding) => [finding.asset.id, finding]));

  return (
    <AppShell>
      <div className="page-wrap dashboard-page">
        <PageHeader
          eyebrow="OVERVIEW / ENTERPRISE CRYPTOGRAPHIC POSTURE"
          title="CRYPTOGRAPHIC OVERVIEW"
          actions={<div className="dashboard-header-actions"><Link href="/intake" className="primary-action"><Import size={15} /> Start Assessment</Link><button className="ghost-action" onClick={scan} disabled={running}>{running ? <Activity className="spin" size={14} /> : <Play size={14} fill="currentColor" />}{running ? "Analyzing Demonstration" : "Load Demonstration Assessment"}</button></div>}
        />

        {error && <div className="error-strip"><TriangleAlert size={15} />{error}</div>}

        <section className="hero-grid">
          <article className="graph-preview panel-v2">
            <div className="panel-topline">
              <div><span className="kicker">CRYPTOGRAPHIC INVENTORY</span><h2>Cryptographic dependency map</h2></div>
              <Link href="/graph" className="text-link">Open dependency map <ArrowUpRight size={13} /></Link>
            </div>
            {summary ? (
              <ForceCryptoGraph
                nodes={summary.graph_nodes}
                edges={summary.graph_edges}
                risks={summary.risk_assessments}
                insights={summary.graph_insights}
                selectedId={selectedNode?.id}
                onSelect={setSelectedNode}
                compact
              />
            ) : (
              <EmptyGraph />
            )}
            <div className="graph-legend">
              <span><i className="legend-node service" /> service</span>
              <span><i className="legend-node crypto" /> cryptography</span>
              <span><i className="legend-risk-ring" /> priority ring</span>
              <span><i className="legend-pulse" /> blocker ring</span>
            </div>
          </article>

          <aside className="signal-column">
            <MetricCard icon={<Fingerprint size={16} />} label="CRYPTOGRAPHIC ASSETS" value={stats.assets} note="verified, normalized cryptographic assets" />
            <MetricCard icon={<ShieldAlert size={16} />} label="QUANTUM-VULNERABLE" value={stats.vulnerable} note="public-key cryptography requiring transition planning" emphasis />
            <MetricCard icon={<TimerReset size={16} />} label="LONG-TERM EXPOSURE" value={stats.hndl} note="Harvest-now-decrypt-later (HNDL) conditions" danger={stats.hndl > 0} />
            <MetricCard icon={<DatabaseZap size={16} />} label="MIGRATION BLOCKERS" value={stats.blockers} note="dependencies that can constrain migration sequencing" />
          </aside>
        </section>

        <section className="intel-grid">
          <article className="panel-v2 node-inspector">
            <div className="panel-topline"><div><span className="kicker">SELECTED ITEM</span><h2>{selectedNode?.label ?? "No node selected"}</h2></div>{selectedRisk && <RiskBadge priority={selectedRisk.priority} score={selectedRisk.score} />}</div>
            {selectedNode ? (
              <div className="node-inspector-body">
                <div className="node-type-chip">{selectedNode.node_type.replaceAll("_", " ")}</div>
                <div className="fact-grid">
                  <Fact label="CENTRALITY" value={formatInsight(summary, selectedNode.id, "centrality")} />
                  <Fact label="AFFECTED SYSTEMS" value={formatInsight(summary, selectedNode.id, "blast_radius")} />
                  <Fact label="QUANTUM STATUS" value={selectedRisk?.quantum_posture.replaceAll("_", " ") ?? "context node"} />
                  <Fact label="TIMING MARGIN" value={selectedRisk?.mosca_margin_years == null ? "—" : `${selectedRisk.mosca_margin_years}y`} />
                </div>
                {selectedRisk?.factors.slice(0, 3).map((factor) => <div className="reason-row" key={factor.code}><span>+{factor.contribution}</span><div><strong>{factor.label}</strong><p>{factor.rationale}</p></div></div>)}
                {!selectedRisk && <p className="muted-copy">Select a cryptographic asset node to inspect the explainable risk factors attached to it.</p>}
                {selectedRisk && <Link href={`/investigate?asset=${selectedRisk.asset_id}`} className="investigate-link">OPEN FULL ASSET INVESTIGATION <ArrowUpRight size={13}/></Link>}
              </div>
            ) : <div className="empty-copy">Start an assessment or load the demonstration environment to build the evidence-linked dependency map.</div>}
          </article>

          <article className="panel-v2 risk-stack">
            <div className="panel-topline"><div><span className="kicker">PRIORITY ACTIONS</span><h2>Assets requiring the most attention</h2></div><Link href="/risk" className="text-link">Quantum Risk <ArrowUpRight size={13} /></Link></div>
            <div className="risk-list">
              {topRisks.map((risk, index) => {
                const finding = findingByAsset.get(risk.asset_id);
                return <button key={risk.asset_id} className="risk-row" onClick={() => setSelectedNode(summary?.graph_nodes.find((node) => node.id === `asset:${risk.asset_id}`) ?? null)}>
                  <span className="rank">0{index + 1}</span>
                  <div><strong>{finding?.asset.canonical_name ?? "Unknown asset"}</strong><small>{risk.quantum_posture.replaceAll("_", " ")}{risk.hndl_exposure ? " · HNDL" : ""}</small></div>
                  <RiskBadge priority={risk.priority} score={risk.score} />
                </button>;
              })}
              {!summary && <div className="empty-copy">No risk model has been evaluated yet.</div>}
            </div>
          </article>

          <article className="panel-v2 evidence-pulse">
            <div className="panel-topline"><div><span className="kicker">ASSESSMENT EVIDENCE</span><h2>Traceable evidence coverage</h2></div><Sparkles size={16} /></div>
            <div className="evidence-metric"><strong>{summary?.findings.reduce((count, finding) => count + finding.evidence.length, 0) ?? 0}</strong><span>evidence records retained</span></div>
            <div className="scanner-bars">
              {(summary?.scanner_executions ?? []).map((scanner) => <div key={scanner.scanner_id} className="scanner-bar"><span>{scanner.scanner_id}</span><i style={{ width: `${Math.max(8, Math.min(100, scanner.finding_count * 8))}%` }} /><code>{scanner.finding_count}</code></div>)}
            </div>
            {summary && <div className="context-state"><span className={summary.context_manifest_loaded ? "online-dot" : "offline-dot"} /> enterprise context {summary.context_manifest_loaded ? "verified" : "not supplied"}</div>}
          </article>
        </section>

        {summary?.coverage && <section className={`coverage-disclosure panel-v2${summary.findings.length === 0 ? " zero" : ""}`}><div><span className="kicker">ASSESSMENT COVERAGE</span><h2>{summary.findings.length === 0 ? "No supported cryptographic evidence was detected." : "What this assessment actually inspected"}</h2><p>{summary.findings.length === 0 ? `QDeX inspected ${summary.coverage.files_observed} files with ${summary.coverage.scanners_completed} completed analyzers. A zero result is not proof that no cryptography exists; unsupported formats, runtime-generated use and dynamically loaded implementations can remain outside static visibility.` : `${summary.coverage.files_observed} files observed · ${summary.coverage.evidence_records} evidence records · ${summary.coverage.scanners_completed} analyzers completed.`}</p></div><div className="coverage-mini"><span><b>{summary.coverage.source_files}</b> source</span><span><b>{summary.coverage.config_files}</b> config</span><span><b>{summary.coverage.dependency_manifests}</b> manifests</span><span><b>{summary.coverage.binary_files}</b> binaries</span></div></section>}

        <section className="roadmap-launch-strip panel-v2">
          <div><Route size={18} /><span><b>MIGRATION PLANNING READY</b><small>Convert the current graph into dependency-safe execution waves and contextual PQC/hybrid targets.</small></span></div>
          <Link href="/migration" className="ghost-action">OPEN MIGRATION ROADMAP <ArrowUpRight size={13} /></Link>
          <Link href="/agility" className="ghost-action">INSPECT MIGRATION READINESS <ArrowUpRight size={13} /></Link>
        </section>
      </div>
    </AppShell>
  );
}

function MetricCard({ icon, label, value, note, emphasis, danger }: { icon: React.ReactNode; label: string; value: number; note: string; emphasis?: boolean; danger?: boolean }) {
  return <article className={`metric-v2 panel-v2${emphasis ? " emphasis" : ""}${danger ? " danger" : ""}`}><div className="metric-v2-label">{icon}{label}</div><strong>{String(value).padStart(2, "0")}</strong><p>{note}</p><span className="metric-trace" /></article>;
}

function RiskBadge({ priority, score }: { priority: string; score?: number | null }) {
  return <span className={`risk-badge ${priority}`}>{score == null ? priority : `${score} / 100`}</span>;
}

function Fact({ label, value }: { label: string; value: string }) { return <div className="fact"><span>{label}</span><strong>{value}</strong></div>; }

function formatInsight(summary: ScanSummary | null, nodeId: string, field: "centrality" | "blast_radius") {
  const insight = summary?.graph_insights.find((item) => item.node_id === nodeId);
  if (!insight) return "—";
  return field === "centrality" ? pct(insight.centrality) : String(insight.blast_radius);
}

function EmptyGraph() {
  return <div className="empty-graph"><div className="orbital-loader"><i /><i /><i /></div><strong>NO ENTERPRISE GRAPH MATERIALIZED</strong><p>Start an assessment to bind deterministic cryptographic evidence to declared service and data context.</p></div>;
}
