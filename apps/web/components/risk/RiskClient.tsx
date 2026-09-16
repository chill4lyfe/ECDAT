"use client";

import { Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, Atom, Clock3, RefreshCw, ShieldCheck, Waves } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AppShell, PageHeader } from "@/components/shell/AppShell";
import { evaluateRiskScenario, fetchLatestScan, runReferenceAssessment } from "@/lib/api";
import type { Finding, RiskAssessment, RiskScenarioResult, ScanSummary } from "@/lib/types";

export function RiskClient() {
  const [summary, setSummary] = useState<ScanSummary | null>(null);
  const [scenario, setScenario] = useState<RiskScenarioResult | null>(null);
  const [horizon, setHorizon] = useState(15);
  const [running, setRunning] = useState(false);
  const [selectedRisk, setSelectedRisk] = useState<RiskAssessment | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { fetchLatestScan().then((value) => {
    setSummary(value);
    const stored = value?.risk_assessments ?? [];
    const first = [...stored].sort((a,b)=>(b.score ?? 0)-(a.score ?? 0))[0] ?? null;
    setSelectedRisk(first);
    const baseline = Number(first?.assumptions.quantum_horizon_years ?? 15);
    if (Number.isFinite(baseline)) setHorizon(baseline);
  }).catch(() => undefined); }, []);

  async function loadReference() {
    setRunning(true); setError(null);
    try { const value = await runReferenceAssessment(15); setSummary(value); setScenario(null); setSelectedRisk([...value.risk_assessments].sort((a,b)=>(b.score ?? 0)-(a.score ?? 0))[0] ?? null); setHorizon(15); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to load demonstration environment"); }
    finally { setRunning(false); }
  }

  async function analyze() {
    if (!summary) return;
    setRunning(true); setError(null);
    try {
      const value = await evaluateRiskScenario(summary.scan_id, horizon);
      setScenario(value);
      setSelectedRisk([...value.assessments].sort((a,b)=>(b.score ?? 0)-(a.score ?? 0))[0] ?? null);
    } catch (e) { setError(e instanceof Error ? e.message : "Scenario analysis failed"); }
    finally { setRunning(false); }
  }

  const activeRisks = scenario?.assessments ?? summary?.risk_assessments ?? [];
  const q = scenario?.quantum_summary ?? summary?.quantum_summary;
  const baselineHorizon = Number(summary?.risk_assessments[0]?.assumptions.quantum_horizon_years ?? 15);
  const appliedHorizon = scenario?.scenario_horizon_years ?? (Number.isFinite(baselineHorizon) ? baselineHorizon : 15);
  const scenarioPending = Boolean(summary && horizon !== appliedHorizon);
  const findingByAsset = useMemo(() => new Map((summary?.findings ?? []).map((finding) => [finding.asset.id, finding])), [summary]);
  const ownerLabelsByAsset = useMemo(() => {
    const nodeById = new Map((summary?.graph_nodes ?? []).map((node) => [node.id, node]));
    const owners = new Map<string, string[]>();
    for (const edge of summary?.graph_edges ?? []) {
      if (edge.edge_type !== "uses" || !edge.target_id.startsWith("asset:")) continue;
      const owner = nodeById.get(edge.source_id);
      if (!owner || !["service", "repository", "container", "application"].includes(owner.node_type)) continue;
      const assetId = edge.target_id.slice(6);
      const values = owners.get(assetId) ?? [];
      if (!values.includes(owner.label)) values.push(owner.label);
      owners.set(assetId, values);
    }
    return owners;
  }, [summary]);
  const sorted = useMemo(() => [...activeRisks].sort((a,b)=>(b.score ?? 0)-(a.score ?? 0)), [activeRisks]);

  return <AppShell><div className="page-wrap risk-page">
    <PageHeader eyebrow="RISK / QUANTUM PLANNING SCENARIOS" title="QUANTUM VULNERABILITY PROFILES" actions={summary ? <button className="primary-action" onClick={analyze} disabled={running}>{running ? <Activity className="spin" size={16}/> : <RefreshCw size={15}/>} Apply Scenario</button> : <button className="primary-action" onClick={loadReference}>Load Demonstration Assessment</button>} />
    {error && <div className="error-strip">{error}</div>}

    <section className="scenario-strip panel-v2">
      <div className="scenario-heading"><Atom size={18}/><div><strong>Quantum planning horizon (Z)</strong><span>Planning assumption selected by the operator</span></div></div>
      <div className="horizon-control"><span>08y</span><input type="range" min="8" max="30" value={horizon} onChange={(e)=>setHorizon(Number(e.target.value))}/><span>30y</span><output>{horizon} YEARS{scenarioPending ? " · PENDING" : ""}</output></div>
      <button className="scenario-play" onClick={analyze} disabled={!summary || running}><RefreshCw size={13}/> Recalculate</button>
      {scenarioPending && <div className="scenario-pending">The slider is a draft assumption. Apply it to recompute priority and long-term confidentiality exposure for this assessment.</div>}
    </section>

    <section className="mosca-explainer panel-v2">
      <div className="mosca-summary">
        <span className="kicker">MIGRATION TIMING TEST (MOSCA)</span>
        <h2>X + Y &gt; Z</h2>
        <p>WHEN COMBINED DATA PROTECTION AND MIGRATION TIMELINES EXCEED THE PLANNING HORIZON, MARGIN EXPIRES AND ASSET PRIORITY INCREASES.</p>
      </div>
      <div className="mosca-variable-grid" aria-label="Mosca planning variables">
        <article><b>X</b><div><strong>Data lifetime</strong></div></article>
        <article><b>Y</b><div><strong>Migration lead time</strong></div></article>
        <article><b>Z</b><div><strong>Planning horizon</strong></div></article>
      </div>
      <div className="model-caveat"><ShieldCheck size={14}/><span>Deterministic planning rule — not a probability score or CRQC prediction. Long-term confidentiality exposure (HNDL) is evaluated separately where applicable.</span></div>
    </section>

    {scenario && <section className="scenario-impact panel-v2">
      <div className="scenario-impact-head">
        <span className="kicker">SCENARIO INTERPRETATION</span>
        <h2>{scenario.narrative.headline}</h2>
        <p>{scenario.narrative.interpretation}</p>
      </div>
      <div className="scenario-delta-metrics" aria-label="Scenario changes">
        <article><ArrowUpRight/><div><strong>{scenario.priority_increases}</strong><span>Priority increases</span></div></article>
        <article><ArrowDownRight/><div><strong>{scenario.priority_decreases}</strong><span>Priority decreases</span></div></article>
        <article><Waves/><div><strong>{scenario.hndl_added} / {scenario.hndl_removed}</strong><span>Long-term exposures added / removed</span></div></article>
      </div>
      <div className="scenario-change-section">
        <div className="scenario-change-heading"><span className="kicker">MATERIAL CHANGES</span><small>Assets whose modeled posture changed under this horizon</small></div>
        <div className="scenario-change-list">{scenario.narrative.material_changes.map((item)=><p key={item}>{item}</p>)}</div>
        {scenario.narrative.unchanged_explanation && <div className="scenario-unchanged"><ShieldCheck size={14}/><p>{scenario.narrative.unchanged_explanation}</p></div>}
      </div>
    </section>}

    <section className="risk-metrics-grid">
      <RiskMetric icon={<AlertTriangle size={16}/>} label="QUANTUM-VULNERABLE" value={q?.vulnerable_assets ?? 0} note="public-key assets requiring quantum transition planning" />
      <RiskMetric icon={<Waves size={16}/>} label="LONG-TERM EXPOSURE (HNDL)" value={q?.hndl_exposed_assets ?? 0} note="captured data may need protection beyond the planning horizon" hot={(q?.hndl_exposed_assets ?? 0)>0}/>
      <RiskMetric icon={<Clock3 size={16}/>} label="HIGH PRIORITY" value={(q?.elevated_assets ?? 0)+(q?.critical_assets ?? 0)} note="elevated + critical assets"/>
      <RiskMetric icon={<ShieldCheck size={16}/>} label="MIGRATION BLOCKERS" value={q?.migration_blockers ?? 0} note="dependency-derived migration constraints"/>
    </section>

    <section className="risk-lab-grid">
      <article className="panel-v2 risk-table-card"><div className="panel-topline"><div><span className="kicker">PRIORITY REGISTER</span><h2>Cryptographic risk and timing</h2></div><span className="count-chip">{sorted.length} ASSETS</span></div>
        <div className="risk-table"><div className="risk-table-head"><span>ASSET</span><span>POSTURE</span><span>TIMING</span><span>HNDL</span><span>SCORE</span></div>
          {sorted.map((risk)=>{ const finding=findingByAsset.get(risk.asset_id); const owners=ownerLabelsByAsset.get(risk.asset_id) ?? []; const detail=finding ? riskAssetDetail(finding, owners) : "asset"; return <button key={risk.asset_id} className={selectedRisk?.asset_id===risk.asset_id?"risk-table-row selected":"risk-table-row"} onClick={()=>setSelectedRisk(risk)}><span><strong>{finding ? riskDisplayName(finding) : "Unknown"}</strong><small>{detail}</small></span><span className={`posture ${risk.quantum_posture}`}>{risk.quantum_posture.replaceAll("_"," ")}</span><span className={risk.mosca_margin_years!=null&&risk.mosca_margin_years<0?"negative-margin":""}>{risk.mosca_margin_years==null?"—":`${risk.mosca_margin_years}y`}</span><span>{risk.hndl_exposure?<b className="hndl-flag">YES</b>:"—"}</span><span><b className={`score-orb ${risk.priority}`}>{risk.score ?? 0}</b></span></button>;})}
          {!summary && <div className="empty-copy">Start an assessment to populate quantum exposure analysis.</div>}
        </div>
      </article>
      <aside className="panel-v2 risk-explainer"><div className="panel-topline"><div><span className="kicker">WHY THIS ASSET IS PRIORITIZED</span><h2>{selectedRisk ? (findingByAsset.get(selectedRisk.asset_id) ? riskDisplayName(findingByAsset.get(selectedRisk.asset_id)!) : "Asset") : "Select an asset"}</h2>{selectedRisk && findingByAsset.get(selectedRisk.asset_id) && <><p className="risk-asset-context">{riskAssetDetail(findingByAsset.get(selectedRisk.asset_id)!, ownerLabelsByAsset.get(selectedRisk.asset_id) ?? [])}</p>{findingByAsset.get(selectedRisk.asset_id)!.asset.canonical_name !== riskDisplayName(findingByAsset.get(selectedRisk.asset_id)!) && <details className="risk-full-identity"><summary>Full cryptographic identity</summary><code>{findingByAsset.get(selectedRisk.asset_id)!.asset.canonical_name}</code></details>}</>}</div>{selectedRisk&&<span className={`risk-badge ${selectedRisk.priority}`}>{selectedRisk.score ?? 0} / 100</span>}</div>
        {selectedRisk ? <><MoscaTimeline risk={selectedRisk} finding={findingByAsset.get(selectedRisk.asset_id)} horizon={appliedHorizon}/><div className="factor-stack">{selectedRisk.factors.map((factor)=><article key={factor.code} className="factor-row"><b>+{factor.contribution}</b><div><strong>{factor.label}</strong><p>{factor.rationale}</p></div></article>)}</div><div className="assumption-note"><Atom size={14}/><p>{selectedRisk.rationale[selectedRisk.rationale.length-1]}</p></div><Link className="ghost-action investigation-link" href={`/investigate?asset=${selectedRisk.asset_id}`}>Open Full Investigation</Link></> : <div className="empty-copy">Select a risk row to inspect its deterministic factors.</div>}
      </aside>
    </section>
  </div></AppShell>;
}

function riskDisplayName(finding: Finding) {
  const raw = finding.asset.canonical_name;
  if (finding.asset.asset_type === "certificate") {
    const cn = raw.match(/(?:^|,)CN=([^,]+)/i)?.[1]?.trim();
    const org = raw.match(/(?:^|,)O=([^,]+)/i)?.[1]?.trim();
    if (cn) return org && org !== cn ? `${cn} · ${org}` : cn;
  }
  return raw.length > 120 ? `${raw.slice(0, 117)}…` : raw;
}

function riskAssetDetail(finding: Finding, owners: string[]) {
  const traits = [finding.asset.asset_type.replaceAll("_", " ")];
  if (finding.asset.key_size_bits) traits.push(`${finding.asset.key_size_bits}-bit`);
  if (finding.asset.mode) traits.push(finding.asset.mode);
  if (finding.asset.version) traits.push(`v${finding.asset.version}`);
  const owner = owners.length ? `${owners[0]}${owners.length > 1 ? ` +${owners.length - 1}` : ""}` : finding.evidence[0]?.location.path ?? "unowned evidence";
  return `${traits.join(" · ")} · ${owner} · ${finding.evidence.length} evidence record${finding.evidence.length === 1 ? "" : "s"}`;
}

function RiskMetric({icon,label,value,note,hot}:{icon:React.ReactNode;label:string;value:number;note:string;hot?:boolean}){return <article className={`risk-metric panel-v2${hot?" hot":""}`}><span>{icon}{label}</span><strong>{String(value).padStart(2,"0")}</strong><small>{note}</small></article>}
function MoscaTimeline({risk,finding,horizon}:{risk:RiskAssessment;finding?:Finding;horizon:number}){const lifetime=Number(risk.assumptions.data_lifetime_years??0);const migration=Number(risk.assumptions.migration_time_years??0);const total=Math.max(1,lifetime+migration,horizon);const horizonX=36+(horizon/total)*548;const lifeWidth=(lifetime/total)*548;const migrationWidth=(migration/total)*548;return <div className="mosca-card"><div className="mosca-head"><span>TIMING WINDOW</span><strong>{risk.mosca_margin_years==null?"context incomplete":risk.mosca_margin_years<0?`${Math.abs(risk.mosca_margin_years)}y OVERLAP`:`${risk.mosca_margin_years}y MARGIN`}</strong></div><svg viewBox="0 0 620 126"><line x1="36" x2="584" y1="94" y2="94" className="timeline-axis"/><rect x="36" y="45" width={lifeWidth} height="12" rx="6" className="timeline-life"/><rect x={36+lifeWidth} y="45" width={migrationWidth} height="12" rx="6" className="timeline-migration"/><line x1={horizonX} x2={horizonX} y1="26" y2="103" className="timeline-horizon"/><text x="36" y="30">X · DATA {lifetime}y</text><text x={Math.min(540,36+lifeWidth)} y="74">Y · MIGRATION {migration}y</text><text x={Math.min(548,horizonX+5)} y="20">Z · {horizon}y</text></svg><p>{finding?.asset.canonical_name ?? "Asset"} · {risk.hndl_exposure?"HNDL condition applies in this scenario":"No modeled HNDL condition in this scenario"}</p></div>}
