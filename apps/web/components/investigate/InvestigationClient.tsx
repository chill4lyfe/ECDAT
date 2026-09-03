"use client";

import { Activity, ArrowRight, Cable, FileSearch, GitBranch, Route, ShieldAlert, SlidersHorizontal, Sparkles, Target } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { AppShell, PageHeader } from "@/components/shell/AppShell";
import { buildMigrationPlan, evaluateRiskScenario, fetchLatestMigrationPlan, fetchLatestScan, runReferenceAssessment } from "@/lib/api";
import type { Finding, MigrationRoadmap, RiskAssessment, RiskScenarioResult, ScanSummary } from "@/lib/types";

const constraints = { mode: "balanced" as const, prefer_hybrid: true, max_parallel_actions: 3, change_window_weeks: 12 };

export function InvestigationClient() {
  const params = useSearchParams();
  const [scan, setScan] = useState<ScanSummary | null>(null);
  const [plan, setPlan] = useState<MigrationRoadmap | null>(null);
  const [assetId, setAssetId] = useState(params.get("asset") ?? "");
  const [horizon, setHorizon] = useState(15);
  const [scenario, setScenario] = useState<RiskScenarioResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchLatestScan(), fetchLatestMigrationPlan()]).then(([latest, latestPlan]) => {
      setScan(latest);
      setPlan(latestPlan?.scan_id === latest?.scan_id ? latestPlan : null);
      if (latest) {
        const requested = params.get("asset");
        const initial = requested && latest.findings.some((f) => f.asset.id === requested) ? requested : [...latest.risk_assessments].sort((a,b)=>(b.score??0)-(a.score??0))[0]?.asset_id;
        setAssetId(initial ?? latest.findings[0]?.asset.id ?? "");
        const baseline = latest.risk_assessments[0]?.assumptions.quantum_horizon_years;
        if (typeof baseline === "number") setHorizon(baseline);
      }
    }).catch(() => undefined);
  }, [params]);

  const finding = useMemo(() => scan?.findings.find((f) => f.asset.id === assetId) ?? null, [scan, assetId]);
  const baselineRisk = useMemo(() => scan?.risk_assessments.find((r) => r.asset_id === assetId), [scan, assetId]);
  const scenarioRisk = useMemo(() => scenario?.assessments.find((r) => r.asset_id === assetId), [scenario, assetId]);
  const risk = scenarioRisk ?? baselineRisk;
  const delta = scenario?.deltas.find((d) => d.asset_id === assetId);
  const assetNodeId = assetId ? `asset:${assetId}` : "";
  const affected = useMemo(() => {
    if (!scan || !assetNodeId) return [];
    const labels = new Map(scan.graph_nodes.map((node) => [node.id, node.label]));
    const serviceIds = new Set<string>();
    for (const edge of scan.graph_edges) {
      if (edge.target_id === assetNodeId && edge.source_id.startsWith("service:")) serviceIds.add(edge.source_id);
      if (edge.source_id === assetNodeId && edge.target_id.startsWith("service:")) serviceIds.add(edge.target_id);
    }
    return [...serviceIds].map((id) => ({ id, label: labels.get(id) ?? id }));
  }, [scan, assetNodeId]);
  const insight = scan?.graph_insights.find((item) => item.node_id === assetNodeId);
  const recommendation = plan?.recommendations.find((item) => item.asset_id === assetId);
  const action = plan?.waves.flatMap((wave) => wave.actions).find((item) => item.asset_ids.includes(assetId));
  const baselineHorizon = Number(scan?.risk_assessments[0]?.assumptions.quantum_horizon_years ?? 15);
  const appliedHorizon = scenario?.scenario_horizon_years ?? (Number.isFinite(baselineHorizon) ? baselineHorizon : 15);
  const roadmapHorizon = plan?.risk_scenario_horizon_years ?? (Number.isFinite(baselineHorizon) ? baselineHorizon : 15);
  const roadmapNeedsRefresh = Boolean(plan && roadmapHorizon !== appliedHorizon);
  const ranked = useMemo(() => {
    if (!scan) return [];
    const risks = new Map(scan.risk_assessments.map((item) => [item.asset_id, item]));
    return [...scan.findings].sort((a,b)=>(risks.get(b.asset.id)?.score??0)-(risks.get(a.asset.id)?.score??0));
  }, [scan]);

  async function loadReference() {
    setBusy(true); setError(null);
    try { const next = await runReferenceAssessment(15); setScan(next); setAssetId([...next.risk_assessments].sort((a,b)=>(b.score??0)-(a.score??0))[0]?.asset_id ?? next.findings[0]?.asset.id ?? ""); setScenario(null); setPlan(null); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to load reference estate"); }
    finally { setBusy(false); }
  }
  async function applyScenario() {
    if (!scan) return;
    setBusy(true); setError(null);
    try { setScenario(await evaluateRiskScenario(scan.scan_id, horizon)); }
    catch (e) { setError(e instanceof Error ? e.message : "Scenario evaluation failed"); }
    finally { setBusy(false); }
  }
  async function makePlan() {
    if (!scan) return;
    setBusy(true); setError(null);
    try { setPlan(await buildMigrationPlan(constraints, scan.scan_id, appliedHorizon)); }
    catch (e) { setError(e instanceof Error ? e.message : "Migration planning failed"); }
    finally { setBusy(false); }
  }

  return <AppShell><div className="page-wrap investigate-page">
    <PageHeader eyebrow="ASSET INVESTIGATION / TRACEABLE DECISION PATH" title="Asset Investigation" subtitle="Every conclusion stays anchored to retained evidence, declared enterprise context and explicit planning assumptions. Scenario analysis changes prioritization without creating a new assessment." actions={!scan ? <button className="primary-action" onClick={loadReference} disabled={busy}>{busy ? <Activity className="spin" size={15}/> : <Sparkles size={15}/>} RUN REFERENCE ASSESSMENT</button> : undefined} />
    {error && <div className="error-strip">{error}</div>}
    {scan && <>
      <section className="investigation-picker panel-v2"><div><Target size={16}/><span>CRYPTOGRAPHIC ASSET</span></div><select value={assetId} onChange={(e)=>{setAssetId(e.target.value); setScenario(null);}}>{ranked.map((item)=><option key={item.asset.id} value={item.asset.id}>{item.asset.canonical_name} · {item.asset.asset_type.replaceAll("_"," ")}</option>)}</select><Link href="/graph" className="ghost-action">VIEW ESTATE GRAPH <ArrowRight size={13}/></Link></section>
      {finding && risk ? <>
        <section className="investigation-flow" aria-label="Investigation path">
          <FlowStep n="01" icon={<ShieldAlert/>} title="Exposure" value={`${risk.score ?? 0}/100 · ${risk.priority}`} note={risk.quantum_posture.replaceAll("_"," ")} hot={risk.priority === "critical" || risk.priority === "elevated"}/>
          <ArrowRight className="flow-arrow"/>
          <FlowStep n="02" icon={<FileSearch/>} title="Evidence" value={`${finding.evidence.length} retained record${finding.evidence.length === 1 ? "" : "s"}`} note={bestLocation(finding)}/>
          <ArrowRight className="flow-arrow"/>
          <FlowStep n="03" icon={<Cable/>} title="Impact" value={`${affected.length} directly linked service${affected.length === 1 ? "" : "s"}`} note={`blast radius ${insight?.blast_radius ?? 0}`}/>
          <ArrowRight className="flow-arrow"/>
          <FlowStep n="04" icon={<Route/>} title="Action" value={recommendation?.strategy.replaceAll("_"," ") ?? "plan not generated"} note={recommendation?.target_profiles[0]?.name ?? "Build roadmap to resolve target"}/>
        </section>

        <section className="investigation-grid">
          <article className="panel-v2 investigation-evidence"><div className="panel-topline"><div><span className="kicker">EVIDENCE CHAIN</span><h2>{finding.asset.canonical_name}</h2></div><span className={`risk-badge ${risk.priority}`}>{risk.score ?? 0} / 100</span></div><div className="evidence-chain">
            {finding.evidence.map((evidence)=><div key={evidence.id} className="evidence-record"><div><FileSearch size={14}/><strong>{location(evidence.location)}</strong></div><p>{evidence.summary}</p><span>{evidence.method.replaceAll("_"," ")} · {evidence.detector} · fingerprint {evidence.fingerprint.slice(0,12)}</span></div>)}
          </div></article>

          <article className="panel-v2 investigation-impact"><div className="panel-topline"><div><span className="kicker">AFFECTED ESTATE</span><h2>Dependency impact</h2></div><GitBranch size={17}/></div><div className="impact-facts"><div><span>DIRECT SERVICES</span><strong>{affected.length}</strong></div><div><span>BLAST RADIUS</span><strong>{insight?.blast_radius ?? 0}</strong></div><div><span>CENTRALITY</span><strong>{Math.round((insight?.centrality ?? 0)*100)}%</strong></div><div><span>MIGRATION BLOCKER</span><strong>{insight?.migration_blocker ? "YES" : "NO"}</strong></div></div><div className="affected-services">{affected.map((item)=><span key={item.id}><i/>{item.label}</span>)}{!affected.length && <p>Direct service ownership was not supplied for this asset. This is an evidence limitation, not proof of no impact.</p>}</div></article>
        </section>

        <section className="investigation-grid scenario-action-grid">
          <article className="panel-v2 investigation-scenario"><div className="panel-topline"><div><span className="kicker">PLANNING ASSUMPTION</span><h2>Change the quantum-risk horizon</h2></div><SlidersHorizontal size={17}/></div><div className="scenario-investigator"><div className="mosca-mini"><b>X</b><span>data lifetime</span><strong>{String(risk.assumptions.data_lifetime_years ?? "—")}y</strong><i>+</i><b>Y</b><span>migration lead time</span><strong>{String(risk.assumptions.migration_time_years ?? "—")}y</strong><i>&gt;</i><b>Z</b><span>planning horizon</span><strong>{horizon}y</strong></div><label><span>QUANTUM-RISK PLANNING HORIZON</span><input type="range" min="5" max="35" step="1" value={horizon} onChange={(e)=>setHorizon(Number(e.target.value))}/><output>{horizon} YEARS</output></label><button className="primary-action" onClick={applyScenario} disabled={busy}>APPLY TO CURRENT ASSESSMENT</button>{delta && <div className="scenario-delta"><strong>{delta.before_score} → {delta.after_score}</strong><span>{delta.before_priority} → {delta.after_priority}</span><p>{scenario?.narrative.interpretation}</p>{delta.before_hndl !== delta.after_hndl && <em>HNDL exposure changed: {delta.after_hndl ? "now exposed" : "no longer exposed under this assumption"}</em>}</div>}</div></article>

          <article className="panel-v2 investigation-action"><div className="panel-topline"><div><span className="kicker">MIGRATION DECISION</span><h2>Actionable path</h2></div><Route size={17}/></div>{recommendation ? <div className="actionable-route"><span className="strategy-chip">{recommendation.strategy.replaceAll("_"," ")}</span><h3>{recommendation.current_primitive} <ArrowRight size={15}/> {recommendation.target_profiles.map((p)=>p.name).join(" + ") || "Context review"}</h3><p>{recommendation.rationale[0]}</p><div className="action-metadata"><span>priority {recommendation.priority_score}/100</span><span>{recommendation.effort_points} effort pts</span><span>{action ? `wave ${action.wave}` : "unsequenced"}</span><span>{action?.estimated_weeks ?? "—"} estimated weeks</span></div><p className="roadmap-basis">Roadmap risk basis: Z = {roadmapHorizon} years{roadmapNeedsRefresh ? ` · applied scenario is Z = ${appliedHorizon} years` : ""}</p>{roadmapNeedsRefresh && <button className="primary-action" onClick={makePlan} disabled={busy}>REBUILD ROADMAP FOR APPLIED SCENARIO</button>}{action && <p className="window-note">{action.within_change_window ? "Fits inside the current planning change window." : "Deferred beyond the current planning change window."}</p>}<Link href="/migration" className="ghost-action">OPEN MIGRATION ROADMAP <ArrowRight size={13}/></Link></div> : <div className="investigation-plan-empty"><p>No migration plan has been generated for this assessment at the applied Z = {appliedHorizon} year risk horizon. Planning is a revision and does not create another assessment record.</p><button className="primary-action" onClick={makePlan} disabled={busy}>BUILD MIGRATION ROADMAP</button></div>}</article>
        </section>
      </> : <div className="panel-v2 empty-copy">Select an evidence-backed cryptographic asset to investigate.</div>}
    </>}
  </div></AppShell>;
}

function FlowStep({n,icon,title,value,note,hot}:{n:string;icon:React.ReactNode;title:string;value:string;note:string;hot?:boolean}) { return <article className={`flow-step panel-v2${hot?" hot":""}`}><span>{n}</span><i>{icon}</i><div><small>{title}</small><strong>{value}</strong><p>{note}</p></div></article>; }
function location(value: Finding["evidence"][number]["location"]) { const base=value.path || value.uri; return value.line_start ? `${base}:${value.line_start}` : base; }
function bestLocation(finding: Finding) { return finding.evidence[0] ? location(finding.evidence[0].location) : "No printable location"; }
