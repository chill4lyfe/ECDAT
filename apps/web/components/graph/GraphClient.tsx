"use client";

import { Activity, ArrowRight, Crosshair, Filter, Play, RotateCcw, Search, ShieldAlert, Waypoints } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ForceCryptoGraph } from "@/components/graph/ForceCryptoGraph";
import { AppShell, PageHeader } from "@/components/shell/AppShell";
import { fetchLatestScan, runReferenceAssessment } from "@/lib/api";
import type { GraphNode, RiskAssessment, ScanSummary } from "@/lib/types";

function riskFor(node: GraphNode | null, summary: ScanSummary | null): RiskAssessment | undefined {
  if (!node?.id.startsWith("asset:")) return undefined;
  return summary?.risk_assessments.find((item) => item.asset_id === node.id.slice(6));
}

export function GraphClient() {
  const [summary, setSummary] = useState<ScanSummary | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [running, setRunning] = useState(false);
  const [resetToken, setResetToken] = useState(0);

  useEffect(() => {
    fetchLatestScan().then((value) => {
      setSummary(value);
      if (value?.graph_nodes.length) setSelected(value.graph_nodes.find((node) => node.node_type === "service") ?? value.graph_nodes[0]);
    }).catch(() => undefined);
  }, []);

  const scan = useCallback(async () => {
    setRunning(true);
    try {
      const value = await runReferenceAssessment(15);
      setSummary(value);
      setSelected(value.graph_nodes.find((node) => node.node_type === "service") ?? value.graph_nodes[0] ?? null);
      setResetToken((token) => token + 1);
    } finally {
      setRunning(false);
    }
  }, []);

  const filteredNodes = useMemo(() => {
    if (!summary) return [];
    const lower = query.trim().toLowerCase();
    return summary.graph_nodes.filter((node) => {
      const matchesText = !lower || node.label.toLowerCase().includes(lower) || node.node_type.toLowerCase().includes(lower);
      const matchesType = typeFilter === "all" || node.node_type === typeFilter;
      return matchesText && matchesType;
    });
  }, [summary, query, typeFilter]);

  const filteredEdges = useMemo(() => {
    const visibleIds = new Set(filteredNodes.map((node) => node.id));
    return (summary?.graph_edges ?? []).filter((edge) => visibleIds.has(edge.source_id) && visibleIds.has(edge.target_id));
  }, [summary, filteredNodes]);
  const insight = summary?.graph_insights.find((item) => item.node_id === selected?.id);
  const risk = riskFor(selected, summary);
  const neighbors = selected && summary ? summary.graph_edges.filter((edge) => edge.source_id === selected.id || edge.target_id === selected.id) : [];

  return (
    <AppShell>
      <div className="page-wrap graph-page">
        <PageHeader
          eyebrow="INVENTORY / CRYPTOGRAPHIC DEPENDENCY MAP"
          title="Cryptographic Dependency Map"
          subtitle="Explore how cryptographic assets connect to services and data. Use the map to understand dependency impact, migration blockers and retained evidence before planning changes."
          actions={<button className="primary-action" onClick={scan} disabled={running}>{running ? <Activity className="spin" size={16} /> : <Play size={15} fill="currentColor" />}{running ? "ASSESSING" : "Load Demonstration Assessment"}</button>}
        />

        <section className="graph-toolbar panel-v2">
          <label className="search-box"><Search size={14} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search service, asset, data class…" /></label>
          <div className="filter-group"><Filter size={14} /><button className={typeFilter === "all" ? "active" : ""} onClick={() => setTypeFilter("all")}>ALL</button><button className={typeFilter === "service" ? "active" : ""} onClick={() => setTypeFilter("service")}>SERVICES</button><button className={typeFilter === "algorithm" ? "active" : ""} onClick={() => setTypeFilter("algorithm")}>ALGORITHMS</button><button className={typeFilter === "data_class" ? "active" : ""} onClick={() => setTypeFilter("data_class")}>DATA</button></div>
          <div className="toolbar-actions"><div className="toolbar-stat"><Waypoints size={14} /><strong>{filteredNodes.length}</strong> nodes <strong>{filteredEdges.length}</strong> edges</div><button className="ghost-action" onClick={() => setResetToken((token) => token + 1)}><RotateCcw size={13} /> RESET LAYOUT</button></div>
        </section>

        <section className="graph-workbench">
          <article className="graph-canvas panel-v2">
            {summary ? <ForceCryptoGraph nodes={filteredNodes} edges={filteredEdges} risks={summary.risk_assessments} insights={summary.graph_insights} selectedId={selected?.id} onSelect={setSelected} resetToken={resetToken} /> : <div className="empty-graph tall"><div className="orbital-loader"><i /><i /><i /></div><strong>NO DEPENDENCY MAP AVAILABLE</strong><p>Start an assessment or load the demonstration environment to build an evidence-linked dependency map.</p></div>}
            {summary && <div className="graph-semantic-legend" aria-label="Dependency map colour legend">
              <span><i className="legend-dot legend-service" />Service</span>
              <span><i className="legend-dot legend-crypto" />Cryptography</span>
              <span><i className="legend-dot legend-data" />Data</span>
              <span><i className="legend-dot legend-certificate" />Certificate / key</span>
              <span><i className="legend-ring" />Outer ring = migration priority</span>
              <span><i className="legend-blocker" />Dashed ring = migration blocker</span>
            </div>}
            <div className="canvas-hud"><span>SCROLL / ZOOM</span><span>DRAG / REPOSITION</span><span>CLICK / ISOLATE</span><span>RESET / STABILIZE</span></div>
          </article>

          <aside className="graph-inspector panel-v2">
            <div className="panel-topline"><div><span className="kicker">SELECTED ITEM</span><h2>{selected?.label ?? "Select a node"}</h2></div>{insight?.migration_blocker && <span className="blocker-chip"><ShieldAlert size={12} /> BLOCKER</span>}</div>
            {selected ? <>
              <div className="node-identity"><span className={`node-glyph type-${selected.node_type}`}><Crosshair size={18} /></span><div><small>{selected.node_type.replaceAll("_", " ")}</small><strong>{selected.label}</strong></div></div>
              <div className="fact-grid graph-facts">
                <Fact label="DEGREE" value={String(insight?.degree ?? 0)} />
                <Fact label="AFFECTED SYSTEMS" value={String(insight?.blast_radius ?? 0)} />
                <Fact label="CENTRALITY" value={`${Math.round((insight?.centrality ?? 0) * 100)}%`} />
                <Fact label="PRIORITY" value={risk?.priority ?? "context"} />
              </div>
              {risk && <div className="risk-core-card"><div><span>QUANTUM STATUS</span><strong>{risk.quantum_posture.replaceAll("_", " ")}</strong></div><b>{risk.score ?? 0}</b><p>{risk.rationale[0]}</p>{risk.hndl_exposure && <em>Long-term confidentiality exposure (HNDL)</em>}</div>}
              <div className="relationship-list"><span className="kicker">DIRECT DEPENDENCIES</span>{neighbors.slice(0, 8).map((edge) => {
                const otherId = edge.source_id === selected.id ? edge.target_id : edge.source_id;
                const other = summary?.graph_nodes.find((node) => node.id === otherId);
                const provenance = String(edge.properties.provenance ?? "derived").replaceAll("_", " ");
                return <button key={edge.id} onClick={() => other && setSelected(other)}><i /><div><strong>{edge.edge_type.replaceAll("_", " ")}</strong><span>{other?.label ?? otherId}</span><small className={`relationship-provenance ${String(edge.properties.provenance ?? "derived")}`}>{provenance}</small></div></button>;
              })}{neighbors.length === 0 && <p className="muted-copy">No direct relationships in the filtered graph.</p>}</div>
              {risk && <Link href={`/investigate?asset=${risk.asset_id}`} className="investigate-link">Open evidence-to-action investigation <ArrowRight size={13}/></Link>}
              {insight?.reasons.map((reason) => <div className="graph-reason" key={reason}>{reason}</div>)}
            </> : <div className="empty-copy">Select an item to inspect its relationships, risk and impact.</div>}
          </aside>
        </section>
      </div>
    </AppShell>
  );
}

function Fact({ label, value }: { label: string; value: string }) { return <div className="fact"><span>{label}</span><strong>{value}</strong></div>; }
