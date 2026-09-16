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
      title="ENTERPRISE READINESS"
      actions={<button className="primary-action" onClick={generate} disabled={running}>{running ? <Activity className="spin" size={16} /> : <Play size={15} fill="currentColor" />}{running ? "Analyzing" : plan ? "Reanalyze Readiness" : scanAvailable ? "Analyze Readiness" : "Load Demonstration + Analyze"}</button>}
    />

    <section className="phase8-readiness-hero panel-v2">
      <div className="phase8-readiness-hero-copy">
        <span className="kicker">ENTERPRISE READINESS POSTURE</span>
        <h2>{scores.length ? `${average}/100 — ${band(average)}` : "No readiness model generated"}</h2>
        <p>Readiness is not a risk score. {technicalOnly === scores.length && scores.length ? "This assessment has no enterprise topology, so QDeX is showing a technical-evidence readiness estimate from the supplied repositories, binaries, BOMs and operational exports. Business sequencing remains intentionally unknown." : "It estimates migration friction from observable cryptographic surface, dependency coupling and declared migration context."} A higher score means the system appears easier to transition—not that it is more secure.</p>
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
      <ReadinessMetric icon={<Sparkles size={18}/>} label="Strongest context" value={strongest ? String(strongest.score) : "—"} note={strongest?.label ?? "no data"} />
    </section>

    <section className="phase8-readiness-layout">
      <article className="panel-v2 phase8-readiness-map">
        <div className="panel-topline"><div><span className="kicker">READINESS MAP</span><h2>Select a system or context to inspect engineering effort and migration complexity.</h2></div><span className="count-chip">{scores.length} CONTEXTS</span></div>
        {scores.length ? <AgilityConstellation scores={scores} selected={selected?.node_id ?? null} onSelect={setSelected} /> : <div className="migration-empty"><div className="migration-orbit"><i/><i/><i/><Radar size={26}/></div><strong>NO READINESS MODEL YET</strong><p>Generate a migration plan to compute evidence-bounded service readiness.</p></div>}
      </article>

      <aside className="panel-v2 phase8-readiness-detail">
        <div className="phase8-readiness-detail-head">
          <div><span className="kicker">SELECTED SYSTEM / TECHNICAL CONTEXT</span><h2>{selected?.label ?? "Select a system"}</h2>{selected && <p>{band(selected.score)} · {selected.basis === "technical_evidence" ? "technical-evidence estimate" : "enterprise-context estimate"}</p>}</div>
          {selected && <div className={`agility-score-orb phase81-score-orb ${selected.difficulty}`}><strong>{selected.score}</strong><span>/100</span></div>}
        </div>
        {selected ? <>
          <div className="phase8-readiness-explainer"><CheckCircle2 size={17}/><p><strong>Interpretation:</strong> this system/source context is scored on migration difficulty, not vulnerability. {selected.basis === "technical_evidence" ? "The score uses observable implementation signals such as crypto surface, hardcoded choices, evidence diversity, legacy primitives and opaque binaries. It does not claim to know service coupling or business migration lead time." : "QDeX combines observable evidence with declared enterprise context such as coupling and migration lead time."} Undocumented vendor constraints and test maturity remain unknown.</p></div>
          <div className="phase8-factor-columns">
            <section><div className="phase8-factor-title"><Wrench size={16}/><strong>Preparation required</strong><span>{negativeFactors.length}</span></div>{negativeFactors.length ? negativeFactors.map((factor) => <FactorCard key={factor.code} factor={factor}/>) : <p className="phase8-none">No negative readiness factors were observed.</p>}</section>
            <section><div className="phase8-factor-title"><ShieldCheck size={16}/><strong>Readiness strengths</strong><span>{positiveFactors.length}</span></div>{positiveFactors.length ? positiveFactors.map((factor) => <FactorCard key={factor.code} factor={factor}/>) : <p className="phase8-none">No positive readiness factors were observed.</p>}</section>
          </div>
          <div className="phase8-preparation-plan"><span className="kicker">RECOMMENDED PREPARATION</span><ol>{preparationActions(selected).map((item) => <li key={item}>{item}</li>)}</ol></div>
        </> : <div className="empty-copy">Select a system from the map or readiness register.</div>}
      </aside>
    </section>

    {scores.length > 0 && <section className="panel-v2 phase8-readiness-register">
      <div className="panel-topline"><div><span className="kicker">READINESS REGISTER</span><h2>Systems ordered by lowest readiness to address high-friction migration targets first.</h2></div></div>
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
  const width = 900; const height = 640; const cx = width / 2; const cy = 355;
  const dense = scores.length > 28;
  const bands = [
    { min: 76, max: 100, radius: 84, label: "READY / VALIDATE", range: "76–100" },
    { min: 56, max: 75, radius: 148, label: "PREPARATION", range: "56–75" },
    { min: 31, max: 55, radius: 214, label: "SIGNIFICANT PREP", range: "31–55" },
    { min: 0, max: 30, radius: 278, label: "MAJOR CONSTRAINT", range: "0–30" },
  ];
  const grouped = bands.map((band) => scores.filter((score) => score.score >= band.min && score.score <= band.max));
  const positioned = grouped.flatMap((items, bandIndex) => items.map((score, itemIndex) => {
    const count = Math.max(1, items.length);
    const stagger = .32 + bandIndex * .49;
    const angle = count === 1 ? -Math.PI / 2 + stagger : -Math.PI / 2 + stagger + (itemIndex / count) * Math.PI * 2;
    const radius = bands[bandIndex].radius;
    return { score, x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius };
  }));

  const nodeBoxes = positioned.map(({ score, x, y }) => ({ id: score.node_id, left: x - 29, right: x + 29, top: y - 29, bottom: y + 29 }));
  const occupied: Array<{ left: number; right: number; top: number; bottom: number }> = [];
  const overlaps = (a: { left: number; right: number; top: number; bottom: number }, b: { left: number; right: number; top: number; bottom: number }) => !(a.right < b.left || a.left > b.right || a.bottom < b.top || a.top > b.bottom);
  const labelPlacements = new Map<string, { x: number; y: number; anchor: "start" | "middle" | "end"; lineX: number; lineY: number }>();

  for (const { score, x, y } of [...positioned].sort((a, b) => a.score.node_id === selected ? -1 : b.score.node_id === selected ? 1 : a.y - b.y)) {
    const text = score.label.length > 25 ? `${score.label.slice(0, 24)}…` : score.label;
    const labelWidth = Math.min(166, Math.max(54, text.length * 6.2));
    const labelHeight = 16;
    const dx = x - cx; const dy = y - cy; const mag = Math.max(1, Math.hypot(dx, dy));
    const ux = dx / mag; const uy = dy / mag;
    const outward = { x: ux, y: uy };
    const side = { x: -uy, y: ux };
    const candidates = [34, 46, 60, 76].flatMap((distance) => [0, 16, -16, 30, -30].map((shift) => {
      const lx = x + outward.x * distance + side.x * shift;
      const ly = y + outward.y * distance + side.y * shift;
      const anchor: "start" | "middle" | "end" = Math.abs(outward.x) < .3 ? "middle" : outward.x > 0 ? "start" : "end";
      return { x: lx, y: ly, anchor, lineX: x + outward.x * 23, lineY: y + outward.y * 23 };
    }));
    let chosen = candidates[0];
    for (const candidate of candidates) {
      const left = candidate.anchor === "start" ? candidate.x : candidate.anchor === "end" ? candidate.x - labelWidth : candidate.x - labelWidth / 2;
      const box = { left, right: left + labelWidth, top: candidate.y - labelHeight / 2, bottom: candidate.y + labelHeight / 2 };
      const inBounds = box.left >= 18 && box.right <= width - 18 && box.top >= 76 && box.bottom <= height - 14;
      const hitsNode = nodeBoxes.some((other) => other.id !== score.node_id && overlaps(box, other));
      const hitsLabel = occupied.some((other) => overlaps(box, other));
      if (inBounds && !hitsNode && !hitsLabel) { chosen = candidate; occupied.push(box); break; }
    }
    labelPlacements.set(score.node_id, chosen);
  }

  return <svg className={`agility-constellation phase8-constellation${dense ? " dense" : ""}`} viewBox={`0 0 ${width} ${height}`}><defs><filter id="agility-glow"><feGaussianBlur stdDeviation="4" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
    <text x="28" y="24" className="agility-map-help">Closer to the centre = easier migration · farther out = more preparation</text>
    <g className="agility-band-key">{bands.map((band, index) => <g key={band.label} transform={`translate(${28 + index * 214},50)`}><circle r="4"/><text x="10" y="4">{band.label} · {band.range}</text></g>)}</g>
    {bands.map((band) => <circle key={band.label} cx={cx} cy={cy} r={band.radius} className="agility-ring"/>)}
    {positioned.map(({ score, x, y }) => {
      const chosen = selected === score.node_id;
      const label = labelPlacements.get(score.node_id)!;
      const labelText = score.label.length > 25 ? `${score.label.slice(0, 24)}…` : score.label;
      return <g key={score.node_id} className={`agility-node ${score.difficulty} ${chosen ? "selected" : ""}`} onClick={() => onSelect(score)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(score); } }} role="button" tabIndex={0} aria-label={`${score.label}, migration readiness ${score.score} of 100`}>
        <line x1={label.lineX} y1={label.lineY} x2={label.x} y2={label.y} className="agility-label-leader"/>
        <g transform={`translate(${x},${y})`}>
          <circle r={chosen ? 27 : 22} className="agility-node-pulse"/>
          <circle r={chosen ? 19 : 16} className="agility-node-disc" filter="url(#agility-glow)"/>
          <text textAnchor="middle" y="4" className="agility-node-score">{score.score}</text>
        </g>
        <text x={label.x} y={label.y + 4} textAnchor={label.anchor} className="agility-node-label">{labelText}</text>
      </g>;
    })}
    <g transform={`translate(${cx},${cy})`} className="agility-center-group"><circle r="48" className="agility-center"/><Layers3 size={25} x={-12.5} y={-17}/><text textAnchor="middle" y="22" className="agility-center-label">EASIER</text></g>
  </svg>;
}

