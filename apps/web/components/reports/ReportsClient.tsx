"use client";

import { Activity, ArrowRight, BookOpenCheck, Download, FileJson2, FileSpreadsheet, FileText, RefreshCw, ShieldAlert, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState, type ChangeEvent } from "react";
import { AppShell, PageHeader } from "@/components/shell/AppShell";
import { API_BASE, fetchExecutiveReport, fetchScan, fetchScanHistory } from "@/lib/api";
import type { ExecutiveReport, ScanHistoryItem, ScanSummary } from "@/lib/types";

export function ReportsClient() {
  const params = useSearchParams();
  const [history,setHistory]=useState<ScanHistoryItem[]>([]); const [scan,setScan]=useState<ScanSummary|null>(null); const [report,setReport]=useState<ExecutiveReport|null>(null); const [selectedId,setSelectedId]=useState(params.get("scan")??""); const [loading,setLoading]=useState(true); const [error,setError]=useState<string|null>(null);
  async function load(preferred?:string) { setLoading(true); setError(null); try { const items=await fetchScanHistory(60); setHistory(items); const scanId=preferred||selectedId||params.get("scan")||items[0]?.scan_id; if(!scanId){setScan(null);setReport(null);return;} setSelectedId(scanId); setScan(await fetchScan(scanId)); setReport(await fetchExecutiveReport(scanId)); } catch(e){setError(e instanceof Error?e.message:"Unable to generate report");} finally{setLoading(false);} }
  useEffect(()=>{void load();},[]);
  async function choose(e:ChangeEvent<HTMLSelectElement>){const id=e.target.value;setSelectedId(id);if(id)await load(id);}

  return <AppShell><div className="page-wrap reports-page">
    <PageHeader eyebrow="GOVERNANCE / REPORTS & EXPORTS" title="Reports & Exports" subtitle="Produce decision-ready summaries for leadership while retaining exact evidence, affected systems, planning assumptions, limitations and machine-readable outputs for engineering teams." actions={<div className="report-header-tools"><select aria-label="Assessment to report" value={selectedId} onChange={choose}><option value="">Select assessment</option>{history.map((item)=><option key={item.scan_id} value={item.scan_id}>{item.display_name} · {item.scan_id.slice(0,6)}</option>)}</select><button className="ghost-action" onClick={()=>load()} disabled={loading}>{loading?<Activity className="spin" size={14}/>:<RefreshCw size={14}/>} Refresh</button></div>}/>
    {error&&<div className="error-strip">{error}</div>}
    {!report||!scan ? <div className="panel-v2 report-empty"><FileText size={32}/><strong>NO ASSESSMENT AVAILABLE</strong><p>Start or import an enterprise assessment first.</p></div> : <>
      <section className="report-hero panel-v2"><div className="report-posture"><span>ASSESSMENT POSTURE</span><strong className={report.posture}>{report.posture.toUpperCase()}</strong><small>Assessment {report.scan_id.slice(0,8)}</small></div><div className="report-headline"><span className="kicker">EXECUTIVE SUMMARY</span><h2>{report.title}</h2><p>{report.headline}</p><div className="report-scope-line">{Object.entries(report.scope).slice(0,4).map(([k,v])=><span key={k}><b>{k.replaceAll("_"," ")}</b>{String(v)}</span>)}</div></div></section>

      <section className="report-metrics">{Object.entries(report.metrics).map(([key,value])=><article className="enterprise-stat panel-v2" key={key}><span>{key.replaceAll("_"," ").toUpperCase()}</span><strong>{String(value).padStart(2,"0")}</strong></article>)}</section>

      <section className="report-executive-grid">
        <article className="panel-v2 management-summary"><div className="panel-topline"><div><span className="kicker">DECISION CONTEXT</span><h2>What this assessment means operationally</h2></div><BookOpenCheck size={17}/></div><div className="narrative-list">{report.management_summary.map((item,i)=><div key={item}><span>{String(i+1).padStart(2,"0")}</span><p>{item}</p></div>)}</div></article>
        <article className="panel-v2 migration-program-report"><div className="panel-topline"><div><span className="kicker">MIGRATION PROGRAM</span><h2>Migration programme overview</h2></div></div><div className="program-facts"><div><span>WAVES</span><strong>{report.migration.waves}</strong></div><div><span>ACTIONS</span><strong>{report.migration.actions}</strong></div><div><span>PLANNING HORIZON</span><strong>{report.migration.risk_scenario_horizon_years ?? "—"}y</strong></div><div><span>EST. WEEKS</span><strong>{report.migration.estimated_calendar_weeks}</strong></div><div><span>DEFERRED</span><strong>{report.migration.deferred_actions}</strong></div></div>{report.migration.strategy_explanation.map((item)=><p key={item}>{item}</p>)}<Link className="ghost-action" href="/migration">OPEN MIGRATION ROADMAP <ArrowRight size={13}/></Link></article>
      </section>

      <section className="report-grid wide-report-grid">
        <article className="panel-v2 priority-report"><div className="panel-topline"><div><span className="kicker">PRIORITY FINDINGS</span><h2>Evidence → impact → action</h2></div><ShieldAlert size={17}/></div><div className="report-findings detailed">{report.priority_findings.map((item,index)=><div key={item.asset_id}><span>{String(index+1).padStart(2,"0")}</span><section><div className="finding-title-row"><strong>{item.asset}</strong><b className={item.priority}>{item.score??"—"}/100</b></div><small>{item.type} · {item.quantum_posture.replaceAll("_"," ")}{item.hndl?" · long-term confidentiality exposure (HNDL)":""}</small><p>{item.reason}</p><div className="finding-detail"><span><b>AFFECTED SYSTEMS</b>{item.affected_services.join(", ")||"No explicit service linkage supplied"}</span><span><b>EVIDENCE</b>{item.evidence_locations.slice(0,3).join(" · ")||"No printable source location"}</span><span><b>RECOMMENDED TRANSITION</b>{item.recommended_action}{item.target_profiles.length?` → ${item.target_profiles.join(" + ")}`:""}</span></div><Link href={`/investigate?asset=${item.asset_id}`} className="investigate-link">Open Investigation <ArrowRight size={13}/></Link></section></div>)}</div></article>

        <aside className="report-side-stack"><article className="panel-v2 report-context"><div className="panel-topline"><div><span className="kicker">ASSUMPTIONS</span><h2>Planning assumptions used in this assessment</h2></div></div><div className="assumption-ledger">{Object.entries(report.assumptions).map(([key,value])=><div key={key}><span>{key.replaceAll("_"," ")}</span><strong>{String(value)}</strong></div>)}</div></article><article className="panel-v2 limitation-panel"><div className="panel-topline"><div><span className="kicker">KNOWN LIMITATIONS</span><h2>Known limitations and visibility boundaries</h2></div><TriangleAlert size={17}/></div><div className="limitation-list">{report.limitations.map((item)=><p key={item}>{item}</p>)}</div></article></aside>
      </section>

      <section className="panel-v2 coverage-report"><div className="panel-topline"><div><span className="kicker">ANALYSIS COVERAGE</span><h2>What was inspected and how much evidence was retained</h2></div></div><div className="coverage-facts">{Object.entries(report.coverage).filter(([key])=>key!=="observations").map(([key,value])=><div key={key}><span>{key.replaceAll("_"," ")}</span><strong>{typeof value==="number"&&key.includes("confidence")?`${Math.round(value*100)}%`:String(value??"—")}</strong></div>)}</div><div className="coverage-observations">{Array.isArray(report.coverage.observations)&&report.coverage.observations.map((item)=><p key={String(item)}>{String(item)}</p>)}</div></section>

      <section className="export-grid"><ExportCard icon={<FileText/>} title="Executive Markdown" format="MD" note="Portable decision report with scope, findings, evidence, migration program, assumptions and limitations." href={`${API_BASE}/v1/reports/scans/${report.scan_id}/executive.md`}/><ExportCard icon={<FileSpreadsheet/>} title="Finding Register" format="CSV" note="Analyst-ready evidence register with source locations, confidence, posture, affected services and risk score." href={`${API_BASE}/v1/reports/scans/${report.scan_id}/findings.csv`}/><ExportCard icon={<FileJson2/>} title="CycloneDX Cryptographic BOM" format="JSON" note="Machine-readable cryptographic inventory for interoperability and downstream tooling." href={`${API_BASE}/v1/exports/scans/${report.scan_id}/cyclonedx`}/></section>

      <section className="panel-v2 technical-observations"><div className="panel-topline"><div><span className="kicker">ENGINEERING OBSERVATIONS</span><h2>For security and platform engineering</h2></div></div>{report.technical_observations.map((item)=><p key={item}>{item}</p>)}</section>
    </>}
  </div></AppShell>;
}

function ExportCard({icon,title,format,note,href}:{icon:React.ReactNode;title:string;format:string;note:string;href:string}) { return <a className="panel-v2 export-card" href={href}><i>{icon}</i><div><span>{format}</span><strong>{title}</strong><p>{note}</p></div><Download size={17}/></a>; }
