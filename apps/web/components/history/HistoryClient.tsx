"use client";

import { Activity, ArrowDownRight, ArrowRight, ArrowUpRight, Building2, GitCompareArrows, History, Minus, RefreshCw, ShieldCheck, UserRound } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import { AppShell, PageHeader } from "@/components/shell/AppShell";
import { compareScans, fetchScanHistory } from "@/lib/api";
import type { ScanComparison, ScanHistoryItem } from "@/lib/types";

export function HistoryClient() {
  const [history, setHistory] = useState<ScanHistoryItem[]>([]);
  const [base, setBase] = useState("");
  const [target, setTarget] = useState("");
  const [comparison, setComparison] = useState<ScanComparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true); setError(null);
    try {
      const items = await fetchScanHistory(60); setHistory(items);
      if (items.length >= 2) { setTarget(items[0].scan_id); setBase(items[1].scan_id); }
      else if (items.length === 1) setTarget(items[0].scan_id);
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to load assessments"); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);

  async function compare() {
    if (!base || !target || base === target) return;
    try { setComparison(await compareScans(base, target)); }
    catch (e) { setError(e instanceof Error ? e.message : "Comparison failed"); }
  }

  const latest = history[0];
  const totals = useMemo(() => ({ assessments: history.length, assets: latest?.assets ?? 0, evidence: latest?.evidence_count ?? 0, confidence: Math.round((latest?.average_confidence ?? 0) * 100) }), [history, latest]);

  return <AppShell><div className="page-wrap history-page">
    <PageHeader eyebrow="ASSESSMENTS / POSTURE OVER TIME" title="Assessment History" subtitle="Each new enterprise assessment creates one immutable snapshot. Scenario analysis and migration-plan rebuilds are planning revisions against an existing assessment, so they do not create duplicate history entries." actions={<button className="ghost-action" onClick={load} disabled={loading}>{loading ? <Activity className="spin" size={14}/> : <RefreshCw size={14}/>} REFRESH</button>} />
    {error && <div className="error-strip">{error}</div>}

    <section className="workspace-disclosure panel-v2"><div><Building2 size={17}/><span><strong>Default enterprise workspace</strong><small>Assessment records shown here belong to the active local workspace.</small></span></div><div><UserRound size={15}/><span><strong>Security Architecture</strong><small>Current assessment owner</small></span></div><div><ShieldCheck size={15}/><span><strong>Single-workspace access model</strong><small>Multi-tenant deployment requires identity-backed organization isolation before production use.</small></span></div></section>

    <section className="history-metrics">
      <HistoryMetric label="ASSESSMENTS" value={totals.assessments}/><HistoryMetric label="LATEST ASSETS" value={totals.assets}/><HistoryMetric label="EVIDENCE RECORDS" value={totals.evidence}/><HistoryMetric label="AVG CONFIDENCE" value={totals.confidence} suffix="%"/>
    </section>

    <section className="history-grid">
      <article className="panel-v2 history-ledger"><div className="panel-topline"><div><span className="kicker">ASSESSMENT REGISTER</span><h2>Enterprise assessment history</h2></div><History size={17}/></div><div className="assessment-table-head"><span>Assessment</span><span>Scope / ownership</span><span>Evidence quality</span><span>Posture</span><span/></div><div className="history-table">
        {history.map((item)=><div className="history-row detailed" key={item.scan_id}>
          <div className="history-primary"><strong>{item.display_name}</strong><small>Last observed {new Date(item.created_at).toLocaleString()}</small><code>{item.scan_id}</code></div>
          <div className="history-scope"><span className="environment-chip">{item.environment}</span><strong>{item.source}</strong><small>{item.owner} · {item.team}</small><small>{item.files_observed} files observed · {item.target_kind.replaceAll("_"," ")}</small></div>
          <div className="history-evidence"><strong>{item.evidence_count} evidence records</strong><span>{item.average_confidence == null ? "Confidence unavailable" : `${Math.round(item.average_confidence * 100)}% average confidence`}</span><span>{item.context_manifest_loaded ? "Business context linked" : "Artifact-only context"}</span></div>
          <div className="history-counters"><span>{item.assets}<small>assets</small></span><span>{item.vulnerable}<small>vulnerable</small></span><span>{item.hndl}<small>HNDL</small></span><span>{item.critical}<small>critical</small></span></div>
          <Link href={`/reports?scan=${item.scan_id}`} className="row-arrow" title="Open decision report"><ArrowRight size={14}/></Link>
        </div>)}
        {!loading && history.length === 0 && <div className="empty-copy">No assessments exist in this workspace yet. Start an assessment from New Assessment.</div>}
      </div></article>

      <aside className="panel-v2 compare-panel"><div className="panel-topline"><div><span className="kicker">POSTURE COMPARISON</span><h2>Compare cryptographic drift</h2></div><GitCompareArrows size={17}/></div><p className="compare-help">Compare two separate assessment snapshots. Planning scenarios do not appear here because they do not represent newly observed enterprise evidence.</p><div className="compare-selects"><label><span>BASELINE</span><select value={base} onChange={(e:ChangeEvent<HTMLSelectElement>)=>setBase(e.target.value)}><option value="">Select assessment</option>{history.map((item)=><option key={item.scan_id} value={item.scan_id}>{item.display_name} · {item.scan_id.slice(0,6)}</option>)}</select></label><ArrowRight size={16}/><label><span>TARGET</span><select value={target} onChange={(e:ChangeEvent<HTMLSelectElement>)=>setTarget(e.target.value)}><option value="">Select assessment</option>{history.map((item)=><option key={item.scan_id} value={item.scan_id}>{item.display_name} · {item.scan_id.slice(0,6)}</option>)}</select></label></div><button className="primary-action compare-run" onClick={compare} disabled={!base || !target || base===target}>COMPARE ASSESSMENTS</button>{comparison ? <ComparisonView value={comparison}/> : <div className="compare-empty"><GitCompareArrows size={30}/><strong>NO COMPARISON SELECTED</strong><p>Select two distinct assessments to inspect asset and exposure drift.</p></div>}</aside>
    </section>
  </div></AppShell>;
}

function HistoryMetric({label,value,suffix=""}:{label:string;value:number;suffix?:string}) { return <article className="enterprise-stat panel-v2"><span>{label}</span><strong>{String(value).padStart(2,"0")}{suffix}</strong></article>; }
function Delta({label,value}:{label:string;value:number}) { const Icon=value>0?ArrowUpRight:value<0?ArrowDownRight:Minus; return <div className={value>0?"delta bad":value<0?"delta good":"delta neutral"}><Icon size={14}/><span>{label}</span><strong>{value>0?`+${value}`:value}</strong></div>; }
function ComparisonView({value}:{value:ScanComparison}) { return <div className="comparison-view"><div className="delta-grid"><Delta label="ASSETS" value={value.asset_delta}/><Delta label="VULNERABLE" value={value.vulnerable_delta}/><Delta label="HNDL" value={value.hndl_delta}/><Delta label="BLOCKERS" value={value.blocker_delta}/></div><div className="change-columns"><section><span className="kicker">NEW ASSETS</span>{value.new_assets.slice(0,8).map((item)=><div key={item.identity}><b>+</b><strong>{item.name}</strong><small>{item.asset_type}</small></div>)}{!value.new_assets.length&&<p>No newly introduced crypto assets.</p>}</section><section><span className="kicker">RESOLVED ASSETS</span>{value.resolved_assets.slice(0,8).map((item)=><div key={item.identity}><b>−</b><strong>{item.name}</strong><small>{item.asset_type}</small></div>)}{!value.resolved_assets.length&&<p>No resolved crypto assets.</p>}</section></div><div className="unchanged-note">{value.unchanged_assets} canonical crypto identities remained unchanged.</div></div>; }
