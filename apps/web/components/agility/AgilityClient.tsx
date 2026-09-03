"use client";

import { Activity, AlertCircle, ArrowDown, ArrowUp, Gauge, Play, Radar, Sparkles } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell, PageHeader } from "@/components/shell/AppShell";
import { buildMigrationPlan, fetchLatestMigrationPlan, fetchLatestScan, runReferenceAssessment } from "@/lib/api";
import type { CryptoAgilityScore, MigrationConstraints, MigrationRoadmap } from "@/lib/types";

const constraints: MigrationConstraints = { mode: "balanced", prefer_hybrid: true, max_parallel_actions: 3, change_window_weeks: 12 };

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
      setPlan(next); setSelected(next.agility_scores[0] ?? null);
    } finally { setRunning(false); }
  }, []);

  const scores = plan?.agility_scores ?? [];
  const readinessLedger = useMemo(() => [...scores].sort((a, b) => a.score - b.score), [scores]);
  const average = scores.length ? Math.round(scores.reduce((sum, item) => sum + item.score, 0) / scores.length) : 0;
  const critical = scores.filter((item) => item.difficulty === "critical" || item.difficulty === "high").length;
  const goodCoverage = scores.filter((item) => item.coverage === "good").length;
  const strongest = useMemo(() => [...scores].sort((a, b) => b.score - a.score)[0], [scores]);

  return <AppShell><div className="page-wrap agility-page">
    <PageHeader eyebrow="MIGRATION READINESS / OBSERVED CRYPTOGRAPHIC AGILITY" title="Migration Readiness" subtitle="Readiness is scored from observable evidence and declared enterprise context. Higher scores mean easier migration; the readiness ledger intentionally lists the weakest systems first." actions={<button className="primary-action" onClick={generate} disabled={running}>{running ? <Activity className="spin" size={16} /> : <Play size={15} fill="currentColor" />}{running ? "ANALYZING" : plan ? "REANALYZE READINESS" : scanAvailable ? "ANALYZE READINESS" : "RUN REFERENCE ASSESSMENT + ANALYZE"}</button>} />

    <section className="agility-metrics">
      <AgilityMetric icon={<Gauge size={16} />} label="ENTERPRISE AVG" value={average} note="higher = more migration-ready" />
      <AgilityMetric icon={<AlertCircle size={16} />} label="HIGH FRICTION" value={critical} note="services scoring below 56" hot={critical > 0} />
      <AgilityMetric icon={<Radar size={16} />} label="GOOD COVERAGE" value={goodCoverage} note={`of ${scores.length} service contexts`} />
      <AgilityMetric icon={<Sparkles size={16} />} label="STRONGEST" value={strongest?.score ?? 0} note={strongest?.label ?? "no data"} />
    </section>

    <section className="agility-grid">
      <article className="panel-v2 agility-field"><div className="panel-topline"><div><span className="kicker">READINESS MAP</span><h2>Service migration readiness</h2></div><span className="count-chip">{scores.length} SERVICES</span></div>{scores.length ? <AgilityConstellation scores={scores} selected={selected?.node_id ?? null} onSelect={setSelected} /> : <div className="migration-empty"><div className="migration-orbit"><i /><i /><i /><Radar size={26} /></div><strong>NO AGILITY MODEL YET</strong><p>Generate a migration plan to compute observable service-level migration friction.</p></div>}</article>
      <aside className="panel-v2 agility-inspector"><div className="panel-topline"><div><span className="kicker">MIGRATION READINESS DECOMPOSITION</span><h2>{selected?.label ?? "Select a service"}</h2></div>{selected && <div className={`agility-score-orb ${selected.difficulty}`}><strong>{selected.score}</strong><span>READY /100</span></div>}</div>{selected ? <div className="agility-inspector-body"><div className="agility-band"><span>{selected.score < 56 ? "LOW READINESS · " : "READINESS · "}{selected.difficulty.toUpperCase()} FRICTION</span><b>HIGHER SCORE = EASIER TO MIGRATE · {selected.coverage.toUpperCase()} COVERAGE</b></div><div className="factor-waterfall">{selected.factors.map((factor) => <article key={factor.code} className={factor.impact >= 0 ? "positive" : "negative"}><div>{factor.impact >= 0 ? <ArrowUp size={13} /> : <ArrowDown size={13} />}<strong>{factor.impact > 0 ? `+${factor.impact}` : factor.impact}</strong></div><section><b>{factor.label}</b><p>{factor.rationale}</p></section></article>)}</div><div className="coverage-note"><AlertCircle size={14} /><p>This is a defensible observed-agility score, not a claim that ECDAT can infer undocumented abstraction layers, vendor contracts or test coverage from source evidence alone.</p></div></div> : <div className="empty-copy">Select a service in the constellation.</div>}</aside>
    </section>

    {scores.length > 0 && <section className="agility-ledger panel-v2"><div className="panel-topline"><div><span className="kicker">READINESS LEDGER</span><h2>Lowest-agility services first</h2></div></div><div className="agility-list">{readinessLedger.map((score, index) => <button key={score.node_id} className={selected?.node_id === score.node_id ? "selected" : ""} onClick={() => setSelected(score)}><span>{String(index + 1).padStart(2, "0")}</span><strong>{score.label}</strong><div className="agility-mini-bar"><i style={{ width: `${score.score}%` }} /></div><b>{score.score}</b><em>{score.difficulty}</em></button>)}</div></section>}
  </div></AppShell>;
}

function AgilityMetric({ icon, label, value, note, hot }: { icon: React.ReactNode; label: string; value: number; note: string; hot?: boolean }) { return <article className={`plan-metric panel-v2${hot ? " danger" : ""}`}><span>{icon}{label}</span><strong>{String(value).padStart(2, "0")}</strong><small>{note}</small></article>; }

function AgilityConstellation({ scores, selected, onSelect }: { scores: CryptoAgilityScore[]; selected: string | null; onSelect: (score: CryptoAgilityScore) => void }) {
  const width = 860; const height = 560; const cx = width / 2; const cy = height / 2;
  return <svg className="agility-constellation" viewBox={`0 0 ${width} ${height}`}><defs><filter id="agility-glow"><feGaussianBlur stdDeviation="5" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter></defs>{[90,170,250].map((r) => <circle key={r} cx={cx} cy={cy} r={r} className="agility-ring" />)}<line x1={cx - 280} x2={cx + 280} y1={cy} y2={cy} className="agility-axis" /><line x1={cx} x2={cx} y1={cy - 280} y2={cy + 280} className="agility-axis" /><text x={cx + 8} y="26" className="agility-axis-label">LOWER FRICTION</text><text x={cx + 8} y={height - 18} className="agility-axis-label">HIGHER FRICTION</text>{scores.map((score, index) => { const angle = (index / Math.max(1, scores.length)) * Math.PI * 2 - Math.PI / 2; const radius = 245 - score.score * 1.55; const x = cx + Math.cos(angle) * radius; const y = cy + Math.sin(angle) * radius; const selectedNow = selected === score.node_id; return <g key={score.node_id} transform={`translate(${x},${y})`} className={`agility-node ${score.difficulty} ${selectedNow ? "selected" : ""}`} onClick={() => onSelect(score)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(score); } }} role="button" tabIndex={0} aria-label={`${score.label}, migration readiness ${score.score} of 100`}><circle r={selectedNow ? 31 : 25} className="agility-node-pulse" /><circle r={selectedNow ? 20 : 17} className="agility-node-disc" filter="url(#agility-glow)" /><text textAnchor="middle" y="4" className="agility-node-score">{score.score}</text><text textAnchor="middle" y="42" className="agility-node-label">{score.label.slice(0, 22)}</text></g>; })}<g transform={`translate(${cx},${cy})`}><circle r="46" className="agility-center" /><Radar size={26} x={-13} y={-13} /></g></svg>;
}
