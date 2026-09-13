"use client";

import { Activity, AlertTriangle, ArrowDown, ArrowUp, CheckCircle2, Gauge, Layers3, Network, Play, Radar, ShieldCheck, Sparkles, Wrench } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell, PageHeader } from "@/components/shell/AppShell";
import { buildMigrationPlan, fetchLatestMigrationPlan, fetchLatestScan, runReferenceAssessment } from "@/lib/api";
import type { CryptoAgilityScore, MigrationConstraints, MigrationRoadmap } from "@/lib/types";

const constraints: MigrationConstraints = { mode: "balanced", prefer_hybrid: true, max_parallel_actions: 3, change_window_weeks: 12 };

const band = (score: number) => score >= 76 ? "Ready with validation" : score >= 56 ? "Preparation required" : score >= 31 ? "Significant preparation" : "Major migration constraint";
const humanNode = (nodeId: string) => nodeId.replace(/^service:/, "").replace(/^container:/, "").replace(/^source:/, "").replaceAll("-", " ");

export function AgilityClient() {
  const [plan, setPlan] = useState<MigrationRoadmap | null>(null);
  const [selected, setSelected] = useState<CryptoAgilityScore | null>(null);
  const [scanAvailable, setScanAvailable] = useState(false);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    Promise.all([fetchLatestScan(), fetchLatestMigrationPlan()])
      .then(([scan, value]) => {
        const current = scan && value?.scan_id === scan.scan_id ? value : null;
        setScanAvailable(Boolean(scan));
        setPlan(current);
        setSelected(current?.agility_scores[0] ?? null);
      })
      .catch(() => undefined);
  }, []);

  const generate = useCallback(async () => {
    setRunning(true);
    try {
      let scan = await fetchLatestScan();
      if (!scan) { scan = await runReferenceAssessment(15); setScanAvailable(true); }
      const baselineHorizon = Number(scan.risk_assessments[0]?.assumptions.quantum_horizon_years ?? 15);
      const next = await buildMigrationPlan(constraints, scan.scan_id, Number.isFinite(baselineHorizon) ? baselineHorizon : 15);
      setPlan(next);
      setSelected(next.agility_scores[0] ?? null);
    } finally { setRunning(false); }
  }, []);

  const scores = plan?.agility_scores ?? [];
  const ledger = useMemo(() => [...scores].sort((a, b) => a.score - b.score), [scores]);
  const average = scores.length ? Math.round(scores.reduce((sum, item) => sum + item.score, 0) / scores.length) : 0;
  const constrained = scores.filter((item) => item.score < 56).length;
  const goodCoverage = scores.filter((item) => item.coverage === "good").length;
  const technicalOnly = scores.filter((item) => item.basis === "technical_evidence").length;
  const strongest = useMemo(() => [...scores].sort((a, b) => b.score - a.score)[0], [scores]);
  const negativeFactors = selected?.factors.filter((factor) => factor.impact < 0) ?? [];
  const positiveFactors = selected?.factors.filter((factor) => factor.impact >= 0) ?? [];

  return <AppShell><div className="page-wrap agility-page phase8-readiness">
    <PageHeader
      eyebrow="READINESS / CRYPTOGRAPHIC TRANSITION PREPAREDNESS"
      title="Migration Readiness"
      subtitle="Understand which systems can transition quickly, which need engineering preparation, and exactly what evidence is driving that conclusion. Higher scores mean an easier migration path; low-readiness systems are intentionally shown first."
      actions={<button className="primary-action" onClick={generate} disabled={running}>{running ? <Activity className="spin" size={16} /> : <Play size={15} fill="currentColor" />}{running ? "Analyzing" : plan ? "Reanalyze Readiness" : scanAvailable ? "Analyze Readiness" : "Load Demonstration + Analyze"}</button>}
    />

    <section className="phase8-readiness-hero panel-v2">
      <div className="phase8-readiness-hero-copy">
        <span className="kicker">ENTERPRISE READINESS POSTURE</span>
        <h2>{scores.length ? `${average}/100 — ${band(average)}` : "No readiness model generated"}</h2>
        <p>Readiness is not a risk score. {technicalOnly === scores.length && scores.length ? "This assessment has no enterprise topology, so ECDAT is showing a technical-evidence readiness estimate from the supplied repositories, binaries, BOMs and operational exports. Business sequencing remains intentionally unknown." : "It estimates migration friction from observable cryptographic surface, dependency coupling and declared migration context."} A higher score means the system appears easier to transition—not that it is more secure.</p>
      </div>
      <div className="phase8-readiness-gauge" aria-label={`Enterprise migration readiness ${average} out of 100`}>
        <svg viewBox="0 0 180 104" role="img"><path d="M22 92 A68 68 0 0 1 158 92" className="readiness-gauge-track"/><path d="M22 92 A68 68 0 0 1 158 92" className="readiness-gauge-value" pathLength="100" strokeDasharray={`${average} 100`}/></svg>
        <div className="phase81-readiness-gauge-value"><strong>{average}</strong><span>/100</span></div>
      </div>
    </section>

    <section className="phase8-readiness-metrics">
      <ReadinessMetric icon={<Gauge size={18}/>} label="Enterprise average" value={average ? `${average}/100` : "—"} note="higher = easier transition" />
      <ReadinessMetric icon={<AlertTriangle size={18}/>} label="Needs preparation" value={String(constrained)} note="systems below 56 readiness" danger={constrained > 0} />
      <ReadinessMetric icon={<ShieldCheck size={18}/>} label="Enterprise-context ready" value={`${goodCoverage}/${scores.length || 0}`} note={technicalOnly ? `${technicalOnly} technical-only context${technicalOnly === 1 ? "" : "s"}` : "full planning context available"} />
      <ReadinessMetric icon={<Sparkles size={18}/>} label="Strongest system" value={strongest ? String(strongest.score) : "—"} note={strongest?.label ?? "no data"} />
    </section>

    <section className="phase8-readiness-layout">
      <article className="panel-v2 phase8-readiness-map">
        <div className="panel-topline"><div><span className="kicker">READINESS MAP</span><h2>Where engineering effort is concentrated</h2><p className="panel-description">Select a system or supplied source context to inspect the factors that make migration easier or harder.</p></div><span className="count-chip">{scores.length} SYSTEMS</span></div>
        {scores.length ? <AgilityConstellation scores={scores} selected={selected?.node_id ?? null} onSelect={setSelected} /> : <div className="migration-empty"><div className="migration-orbit"><i/><i/><i/><Radar size={26}/></div><strong>NO READINESS MODEL YET</strong><p>Generate a migration plan to compute evidence-bounded service readiness.</p></div>}
      </article>

      <aside className="panel-v2 phase8-readiness-detail">
        <div className="phase8-readiness-detail-head">
          <div><span className="kicker">SELECTED SYSTEM</span><h2>{selected?.label ?? "Select a system"}</h2>{selected && <p>{band(selected.score)} · {selected.basis === "technical_evidence" ? "technical-evidence estimate" : "enterprise-context estimate"}</p>}</div>
          {selected && <div className={`agility-score-orb phase81-score-orb ${selected.difficulty}`}><strong>{selected.score}</strong><span>/100</span><small>READINESS</small></div>}
        </div>
        {selected ? <>
          <div className="phase8-readiness-explainer"><CheckCircle2 size={17}/><p><strong>Interpretation:</strong> this system/source context is scored on migration difficulty, not vulnerability. {selected.basis === "technical_evidence" ? "The score uses observable implementation signals such as crypto surface, hardcoded choices, evidence diversity, legacy primitives and opaque binaries. It does not claim to know service coupling or business migration lead time." : "ECDAT combines observable evidence with declared enterprise context such as coupling and migration lead time."} Undocumented vendor constraints and test maturity remain unknown.</p></div>
          <div className="phase8-factor-columns">
            <section><div className="phase8-factor-title"><Wrench size={16}/><strong>Preparation required</strong><span>{negativeFactors.length}</span></div>{negativeFactors.length ? negativeFactors.map((factor) => <FactorCard key={factor.code} factor={factor}/>) : <p className="phase8-none">No negative readiness factors were observed.</p>}</section>
            <section><div className="phase8-factor-title"><ShieldCheck size={16}/><strong>Readiness strengths</strong><span>{positiveFactors.length}</span></div>{positiveFactors.length ? positiveFactors.map((factor) => <FactorCard key={factor.code} factor={factor}/>) : <p className="phase8-none">No positive readiness factors were observed.</p>}</section>
          </div>
          <div className="phase8-preparation-plan"><span className="kicker">RECOMMENDED PREPARATION</span><ol>{preparationActions(selected).map((item) => <li key={item}>{item}</li>)}</ol></div>
        </> : <div className="empty-copy">Select a system from the map or readiness register.</div>}
      </aside>
    </section>

    {scores.length > 0 && <section className="panel-v2 phase8-readiness-register">
      <div className="panel-topline"><div><span className="kicker">READINESS REGISTER</span><h2>Systems requiring the most preparation</h2><p className="panel-description">Lowest readiness is listed first so teams can address migration friction before execution begins.</p></div></div>
      <div className="phase8-readiness-table-head"><span>System / source</span><span>Readiness</span><span>Difficulty</span><span>Evidence</span><span>Main constraint</span></div>
      <div className="phase8-readiness-rows">{ledger.map((score) => {
        const constraint = score.factors.find((factor) => factor.impact < 0);
        return <button key={score.node_id} className={selected?.node_id === score.node_id ? "selected" : ""} onClick={() => setSelected(score)}>
          <div><Network size={16}/><span><strong>{score.label}</strong><small>{humanNode(score.node_id)}</small></span></div>
          <div className="phase8-readiness-score"><strong>{score.score}</strong><div><i style={{width:`${score.score}%`}}/></div></div>
          <span className={`readiness-band ${score.difficulty}`}>{score.difficulty}</span>
          <span>{score.coverage}</span>
          <span>{constraint?.label ?? "No major observed constraint"}</span>
        </button>;
      })}</div>
    </section>}
  </div></AppShell>;
}

function ReadinessMetric({icon, label, value, note, danger}: {icon: React.ReactNode; label: string; value: string; note: string; danger?: boolean}) {
  return <article className={`panel-v2 phase8-readiness-metric${danger ? " danger" : ""}`}><div>{icon}<span>{label}</span></div><strong>{value}</strong><small>{note}</small></article>;
}

function FactorCard({factor}: {factor: CryptoAgilityScore["factors"][number]}) {
  const positive = factor.impact >= 0;
  return <article className={`phase8-factor-card ${positive ? "positive" : "negative"}`}><div>{positive ? <ArrowUp size={15}/> : <ArrowDown size={15}/>}<strong>{positive && factor.impact > 0 ? `+${factor.impact}` : factor.impact}</strong></div><section><b>{factor.label}</b><p>{factor.rationale}</p></section></article>;
}

function preparationActions(score: CryptoAgilityScore): string[] {
  const actions: string[] = [];
  for (const factor of score.factors) {
    if (factor.impact >= 0) continue;
    if (factor.code === "hardcoded-crypto") actions.push("Move algorithm and key-selection choices behind an approved crypto-provider or configuration boundary before changing primitives.");
    else if (factor.code === "crypto-surface") actions.push("Create an owned cryptographic inventory for this service and group compatible changes into one controlled migration workstream.");
    else if (factor.code === "long-migration") actions.push("Break the declared migration programme into staged milestones with rollback and interoperability gates.");
    else if (factor.code === "coupling") actions.push("Validate dependent services and contract boundaries before scheduling a cryptographic cutover.");
    else if (factor.code === "no-observed-crypto") actions.push("Resolve the system's runtime cryptographic dependencies before treating readiness as complete.");
    else if (factor.code === "source-context-only") actions.push("Add or integrate service ownership and dependency context before treating sequencing or organization-specific migration effort as complete.");
    else if (factor.code === "opaque-binary") actions.push("Obtain vendor/runtime ownership information or a more inspectable build artifact before committing the opaque binary to a cutover schedule.");
    else if (factor.code === "legacy-crypto-pressure") actions.push("Separate classical hygiene work from PQC transition so MD5/SHA-1/DES-family cleanup does not become hidden inside the quantum programme.");
  }
  if (!actions.length) actions.push("Maintain compatibility tests, rollback procedures and evidence capture while executing the recommended migration actions.");
  return [...new Set(actions)];
}

function AgilityConstellation({ scores, selected, onSelect }: { scores: CryptoAgilityScore[]; selected: string | null; onSelect: (score: CryptoAgilityScore) => void }) {
  const width = 860; const height = 540; const cx = width / 2; const cy = height / 2;
  return <svg className="agility-constellation phase8-constellation" viewBox={`0 0 ${width} ${height}`}><defs><filter id="agility-glow"><feGaussianBlur stdDeviation="5" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>{[90,170,250].map((r) => <circle key={r} cx={cx} cy={cy} r={r} className="agility-ring"/>)}<line x1={cx-280} x2={cx+280} y1={cy} y2={cy} className="agility-axis"/><line x1={cx} x2={cx} y1={cy-260} y2={cy+260} className="agility-axis"/><text x={cx+8} y="24" className="agility-axis-label">EASIER TRANSITION</text><text x={cx+8} y={height-16} className="agility-axis-label">MORE PREPARATION</text>{scores.map((score,index)=>{const angle=(index/Math.max(1,scores.length))*Math.PI*2-Math.PI/2; const radius=245-score.score*1.55; const x=cx+Math.cos(angle)*radius; const y=cy+Math.sin(angle)*radius; const chosen=selected===score.node_id; return <g key={score.node_id} transform={`translate(${x},${y})`} className={`agility-node ${score.difficulty} ${chosen?"selected":""}`} onClick={()=>onSelect(score)} onKeyDown={(event)=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();onSelect(score);}}} role="button" tabIndex={0} aria-label={`${score.label}, migration readiness ${score.score} of 100`}><circle r={chosen?31:25} className="agility-node-pulse"/><circle r={chosen?20:17} className="agility-node-disc" filter="url(#agility-glow)"/><text textAnchor="middle" y="4" className="agility-node-score">{score.score}</text><text textAnchor="middle" y="42" className="agility-node-label">{score.label.slice(0,24)}</text></g>;})}<g transform={`translate(${cx},${cy})`}><circle r="46" className="agility-center"/><Layers3 size={26} x={-13} y={-13}/></g></svg>;
}
