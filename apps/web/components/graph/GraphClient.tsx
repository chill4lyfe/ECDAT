"use client";

import { Activity, ArrowRight, Check, Crosshair, Filter, Maximize2, Play, RotateCcw, Search, ShieldAlert, Waypoints, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ForceCryptoGraph } from "@/components/graph/ForceCryptoGraph";
import { AppShell, PageHeader } from "@/components/shell/AppShell";
import { fetchLatestScan, runReferenceAssessment } from "@/lib/api";
import type { GraphNode, RiskAssessment, ScanSummary } from "@/lib/types";

function riskFor(node: GraphNode | null, summary: ScanSummary | null): RiskAssessment | undefined {
  if (!node?.id.startsWith("asset:")) return undefined;
  return summary?.risk_assessments.find((item) => item.asset_id === node.id.slice(6));
}

function readableNodeLabel(node: GraphNode | null) {
  if (!node) return "Select a node";
  const label = node.label;
  if (["certificate", "key"].includes(node.node_type)) {
    const cn = label.match(/(?:^|,)CN=([^,]+)/i)?.[1]?.trim();
    const org = label.match(/(?:^|,)O=([^,]+)/i)?.[1]?.trim();
    if (cn) return org && org !== cn ? `${cn} · ${org}` : cn;
  }
  return label.length > 110 ? `${label.slice(0, 107)}…` : label;
}

export function GraphClient() {
  const [summary, setSummary] = useState<ScanSummary | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [running, setRunning] = useState(false);
  const [resetToken, setResetToken] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const [labelMode, setLabelMode] = useState<"selection" | "focus">("selection");

  useEffect(() => {
    fetchLatestScan().then((value) => {
      setSummary(value);
      if (value?.graph_nodes.length) setSelected(value.graph_nodes.find((node) => node.node_type === "service") ?? value.graph_nodes[0]);
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!expanded) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previous; };
  }, [expanded]);

  const scan = useCallback(async () => {
    setRunning(true);
    try {
      const value = await runReferenceAssessment(15);
      setSummary(value);
      setSelected(value.graph_nodes.find((node) => node.node_type === "service") ?? value.graph_nodes[0] ?? null);
      setLabelMode("selection");
      setResetToken((token) => token + 1);
    } finally {
      setRunning(false);
    }
  }, []);

  // Filters still change graph scope. Search does not remove graph data: it locates and
  // focuses a node so a large estate keeps its surrounding topology visible.
  const visibleNodes = useMemo(() => {
    if (!summary) return [];
    return summary.graph_nodes.filter((node) => typeFilter === "all" || node.node_type === typeFilter);
  }, [summary, typeFilter]);

  const visibleEdges = useMemo(() => {
    const visibleIds = new Set(visibleNodes.map((node) => node.id));
    return (summary?.graph_edges ?? []).filter((edge) => visibleIds.has(edge.source_id) && visibleIds.has(edge.target_id));
  }, [summary, visibleNodes]);

  const selectFromGraph = useCallback((node: GraphNode) => {
    setSelected(node);
    setLabelMode("selection");
  }, []);

  const selectFromSearch = useCallback((node: GraphNode) => {
    setSelected(node);
    setLabelMode("focus");
    setQuery("");
  }, []);

  const insight = summary?.graph_insights.find((item) => item.node_id === selected?.id);
  const risk = riskFor(selected, summary);
  const neighbors = selected && summary ? summary.graph_edges.filter((edge) => edge.source_id === selected.id || edge.target_id === selected.id) : [];

  return (
    <AppShell>
      <div className="page-wrap graph-page">
        <PageHeader
          eyebrow="INVENTORY / CRYPTOGRAPH"
          title="CRYPTOGRAPHIC DEPENDENCY MAP"
          actions={<button className="primary-action" onClick={scan} disabled={running}>{running ? <Activity className="spin" size={16} /> : <Play size={15} fill="currentColor" />}{running ? "ASSESSING" : "Load Demonstration Assessment"}</button>}
        />

        <section className="graph-toolbar panel-v2">
          <GraphSearch query={query} onQuery={setQuery} nodes={visibleNodes} selectedId={selected?.id ?? null} onChoose={selectFromSearch} placeholder="Find a node without hiding the graph…" />
          <div className="filter-group"><Filter size={14} /><button className={typeFilter === "all" ? "active" : ""} onClick={() => setTypeFilter("all")}>ALL</button><button className={typeFilter === "service" ? "active" : ""} onClick={() => setTypeFilter("service")}>SERVICES</button><button className={typeFilter === "algorithm" ? "active" : ""} onClick={() => setTypeFilter("algorithm")}>ALGORITHMS</button><button className={typeFilter === "data_class" ? "active" : ""} onClick={() => setTypeFilter("data_class")}>DATA</button></div>
          <div className="toolbar-actions"><div className="toolbar-stat"><Waypoints size={14} /><strong>{visibleNodes.length}</strong> nodes <strong>{visibleEdges.length}</strong> edges</div><button className="ghost-action" onClick={() => setResetToken((token) => token + 1)}><RotateCcw size={13} /> RESET LAYOUT</button></div>
        </section>

        <section className="graph-workbench">
          <article className="graph-canvas panel-v2">
            {summary ? (expanded ? <div className="graph-expansion-placeholder"><Waypoints size={18}/><span>Expanded graph view is open</span></div> : <ForceCryptoGraph nodes={visibleNodes} edges={visibleEdges} risks={summary.risk_assessments} insights={summary.graph_insights} selectedId={selected?.id} labelMode={labelMode} onSelect={selectFromGraph} resetToken={resetToken} />) : <div className="empty-graph tall"><div className="orbital-loader"><i /><i /><i /></div><strong>NO DEPENDENCY MAP AVAILABLE</strong><p>Start an assessment or load the demonstration environment to build an evidence-linked dependency map.</p></div>}
            {summary && <div className="graph-semantic-legend" aria-label="Dependency map colour legend">
              <span><i className="legend-dot legend-service" />Service / application</span>
              <span><i className="legend-score legend-score-critical" />Critical</span>
              <span><i className="legend-score legend-score-elevated" />Elevated</span>
              <span><i className="legend-score legend-score-moderate" />Moderate</span>
              <span><i className="legend-score legend-score-low" />Low</span>
              <span><i className="legend-blocker" />Dashed ring = migration blocker</span>
            </div>}
            <div className="canvas-hud"><span>SCROLL / ZOOM</span><span>DRAG / REPOSITION</span><span>CLICK / INSPECT</span><span>RESET / STABILIZE</span></div>
            {summary && <button type="button" className="graph-expand-button" onClick={() => setExpanded(true)} aria-label="Expand dependency graph"><Maximize2 size={15}/> EXPAND</button>}
          </article>

          <aside className="graph-inspector panel-v2">
            <div className="panel-topline"><div><span className="kicker">SELECTED ITEM</span><h2>{readableNodeLabel(selected)}</h2></div>{insight?.migration_blocker && <span className="blocker-chip"><ShieldAlert size={12} /> BLOCKER</span>}</div>
            {selected ? <>
              <div className="node-identity"><span className={`node-glyph type-${selected.node_type}`}><Crosshair size={18} /></span><div><small>{selected.node_type.replaceAll("_", " ")}</small><strong>{readableNodeLabel(selected)}</strong></div></div>{selected.label !== readableNodeLabel(selected) && <details className="graph-full-identity"><summary>Full identifier</summary><code>{selected.label}</code></details>}
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
                return <button key={edge.id} onClick={() => other && selectFromGraph(other)}><i /><div><strong>{edge.edge_type.replaceAll("_", " ")}</strong><span>{other ? readableNodeLabel(other) : otherId}</span><small className={`relationship-provenance ${String(edge.properties.provenance ?? "derived")}`}>{provenance}</small></div></button>;
              })}{neighbors.length === 0 && <p className="muted-copy">No direct relationships in the current graph scope.</p>}</div>
              {risk && <Link href={`/investigate?asset=${risk.asset_id}`} className="investigate-link">Open evidence-to-action investigation <ArrowRight size={13}/></Link>}
              {insight?.reasons.map((reason) => <div className="graph-reason" key={reason}>{reason}</div>)}
            </> : <div className="empty-copy">Select an item to inspect its relationships, risk and impact.</div>}
          </aside>
        </section>

        {expanded && summary && <div className="graph-expanded-backdrop" role="dialog" aria-modal="true" aria-label="Expanded cryptographic dependency map" onMouseDown={(event) => { if (event.target === event.currentTarget) setExpanded(false); }}>
          <section className="graph-expanded-panel panel-v2">
            <div className="graph-expanded-toolbar">
              <div className="graph-expanded-title"><span className="kicker">EXPANDED DEPENDENCY MAP</span><strong>{visibleNodes.length} nodes · {visibleEdges.length} edges</strong></div>
              <GraphSearch compact query={query} onQuery={setQuery} nodes={visibleNodes} selectedId={selected?.id ?? null} onChoose={selectFromSearch} placeholder="Search this graph…" />
              <div className="graph-expanded-actions"><button className="ghost-action" onClick={() => setResetToken((token) => token + 1)}><RotateCcw size={13}/> RESET LAYOUT</button><button className="ghost-action graph-close-button" onClick={() => setExpanded(false)}><X size={15}/> CLOSE</button></div>
            </div>
            <div className="graph-expanded-stage"><ForceCryptoGraph expanded nodes={visibleNodes} edges={visibleEdges} risks={summary.risk_assessments} insights={summary.graph_insights} selectedId={selected?.id} labelMode={labelMode} onSelect={selectFromGraph} resetToken={resetToken} /></div>
            <div className="graph-expanded-footer"><span>Search focuses one node; click a node to label it and its direct connections</span><span>Drag keeps the same force behavior; dense estates idle when untouched</span></div>
          </section>
        </div>}
      </div>
    </AppShell>
  );
}

function GraphSearch({ query, onQuery, nodes, selectedId, onChoose, placeholder, compact = false }: { query: string; onQuery: (value: string) => void; nodes: GraphNode[]; selectedId: string | null; onChoose: (node: GraphNode) => void; placeholder: string; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const results = useMemo(() => {
    const tokens = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!tokens.length) return [];
    return nodes.filter((node) => {
      const haystack = `${node.label} ${node.node_type}`.toLowerCase();
      return tokens.every((token) => haystack.includes(token));
    }).slice(0, 12);
  }, [nodes, query]);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => { if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  return <div className={`graph-node-search${compact ? " compact" : ""}`} ref={rootRef}>
    <label className="search-box"><Search size={14} /><input value={query} onFocus={() => setOpen(Boolean(query.trim()))} onChange={(event) => { onQuery(event.target.value); setOpen(Boolean(event.target.value.trim())); }} onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); }} placeholder={placeholder} /></label>
    {open && <div className="graph-search-results" role="listbox" aria-label="Dependency graph search results">
      {results.map((node) => <button type="button" role="option" aria-selected={node.id === selectedId} key={node.id} onClick={() => { onChoose(node); setOpen(false); }}><span><strong>{readableNodeLabel(node)}</strong><small>{node.node_type.replaceAll("_", " ")}</small></span>{node.id === selectedId && <Check size={13}/>}</button>)}
      {!results.length && <p>No matching nodes.</p>}
    </div>}
  </div>;
}

function Fact({ label, value }: { label: string; value: string }) { return <div className="fact"><span>{label}</span><strong>{value}</strong></div>; }
