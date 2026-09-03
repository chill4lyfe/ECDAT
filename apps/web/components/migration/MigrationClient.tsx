"use client";

import { Activity, ArrowRight, Boxes, Cable, CircleGauge, GitPullRequestArrow, Play, Route, ShieldCheck, SlidersHorizontal, Sparkles, TimerReset, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell, PageHeader } from "@/components/shell/AppShell";
import { buildMigrationPlan, fetchLatestMigrationPlan, fetchLatestScan, runReferenceAssessment } from "@/lib/api";
import type { MigrationAction, MigrationConstraints, MigrationRoadmap, ScanSummary } from "@/lib/types";

const DEFAULT_CONSTRAINTS: MigrationConstraints = {
  mode: "balanced",
  prefer_hybrid: true,
  max_parallel_actions: 3,
  change_window_weeks: 12,
};

export function MigrationClient() {
  const [scan, setScan] = useState<ScanSummary | null>(null);
  const [plan, setPlan] = useState<MigrationRoadmap | null>(null);
  const [constraints, setConstraints] = useState(DEFAULT_CONSTRAINTS);
  const [horizon, setHorizon] = useState(15);
  const [selected, setSelected] = useState<MigrationAction | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchLatestScan(), fetchLatestMigrationPlan()]).then(([latestScan, latestPlan]) => {
      setScan(latestScan);
      const applicablePlan = latestPlan && latestScan && latestPlan.scan_id === latestScan.scan_id ? latestPlan : null;
      setPlan(applicablePlan);
      setSelected(applicablePlan?.waves.flatMap((wave) => wave.actions)[0] ?? null);
      const baselineHorizon = Number(latestScan?.risk_assessments[0]?.assumptions.quantum_horizon_years ?? 15);
      setHorizon(applicablePlan?.risk_scenario_horizon_years ?? (Number.isFinite(baselineHorizon) ? baselineHorizon : 15));
      if (applicablePlan) setConstraints(applicablePlan.constraints);
    }).catch(() => undefined);
  }, []);

  const generate = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      let current = scan;
      if (!current) {
        current = await runReferenceAssessment(15);
        setScan(current);
      }
      const next = await buildMigrationPlan(constraints, current.scan_id, horizon);
      setPlan(next);
      setSelected(next.waves.flatMap((wave) => wave.actions)[0] ?? null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to build migration plan");
    } finally {
      setRunning(false);
    }
  }, [constraints, horizon, scan]);

  const actions = useMemo(() => plan?.waves.flatMap((wave) => wave.actions) ?? [], [plan]);
  const selectedRecommendation = plan?.recommendations.find((item) => selected?.asset_ids.includes(item.asset_id));
  const baselineHorizon = Number(scan?.risk_assessments[0]?.assumptions.quantum_horizon_years ?? 15);
  const planHorizon = plan?.risk_scenario_horizon_years ?? (Number.isFinite(baselineHorizon) ? baselineHorizon : 15);
  const controlsDiffer = Boolean(plan && (
    planHorizon !== horizon ||
    plan.constraints.mode !== constraints.mode ||
    plan.constraints.prefer_hybrid !== constraints.prefer_hybrid ||
    plan.constraints.max_parallel_actions !== constraints.max_parallel_actions ||
    plan.constraints.change_window_weeks !== constraints.change_window_weeks
  ));

  return (
    <AppShell>
      <div className="page-wrap migration-page">
        <PageHeader
          eyebrow="MIGRATION ROADMAP / DEPENDENCY-AWARE SEQUENCING"
          title="Migration Roadmap"
          subtitle="Prioritization combines evidence, quantum exposure, service dependencies and operational constraints. Change a planning control, rebuild, and the sequence visibly reflects that decision."
          actions={<button className="primary-action" onClick={generate} disabled={running}>{running ? <Activity className="spin" size={16} /> : <Play size={15} fill="currentColor" />}{running ? "PLANNING" : plan ? "REBUILD PLAN" : scan ? "GENERATE ROADMAP" : "RUN REFERENCE ASSESSMENT + PLAN"}</button>}
        />

        {error && <div className="error-strip"><TriangleAlert size={15} />{error}</div>}

        <section className="migration-control panel-v2">
          <div className="control-intro"><SlidersHorizontal size={18} /><div><strong>Planning constraints</strong><span>These controls alter target profiles, concurrency and scheduling. They do not create a new assessment record.</span></div></div>
          <div className="mode-switch">
            {(["performance", "balanced", "conservative"] as const).map((mode) => <button key={mode} className={constraints.mode === mode ? "active" : ""} onClick={() => setConstraints((value) => ({ ...value, mode }))}>{mode}</button>)}
          </div>
          <div className="mode-explanation"><strong>{constraints.mode === "performance" ? "Runtime efficiency" : constraints.mode === "conservative" ? "Risk-minimizing" : "Balanced transition"}</strong><span>{constraints.mode === "performance" ? "Favors smaller standardized profiles and lower runtime overhead where context permits." : constraints.mode === "conservative" ? "Favors stronger profiles, additional validation and more cautious sequencing at greater effort." : "Balances standardized security margin, interoperability and implementation cost."}</span></div>
          <label className="micro-slider migration-horizon"><span>QUANTUM-RISK HORIZON (Z)</span><input type="range" min="8" max="30" value={horizon} onChange={(event) => setHorizon(Number(event.target.value))} /><output>{horizon}y</output><small>Re-evaluates exposure for planning; does not create a new assessment.</small></label>
          <label className="hybrid-toggle"><input type="checkbox" checked={constraints.prefer_hybrid} onChange={(event) => setConstraints((value) => ({ ...value, prefer_hybrid: event.target.checked }))} /><i /><span>Prefer hybrid transition</span></label>
          <label className="micro-slider"><span>PARALLEL ACTIONS</span><input type="range" min="1" max="6" value={constraints.max_parallel_actions} onChange={(event) => setConstraints((value) => ({ ...value, max_parallel_actions: Number(event.target.value) }))} /><output>{constraints.max_parallel_actions}</output></label>
          <label className="micro-slider"><span>CHANGE WINDOW</span><input type="range" min="4" max="32" value={constraints.change_window_weeks} onChange={(event) => setConstraints((value) => ({ ...value, change_window_weeks: Number(event.target.value) }))} /><output>{constraints.change_window_weeks}w</output></label>
          {controlsDiffer && <div className="planning-pending"><RefreshPlanDot /><span><strong>Planning controls changed.</strong> Rebuild the roadmap to apply these values; the metrics and sequence below still represent the last generated plan.</span></div>}
        </section>

        <section className="migration-metrics">
          <PlanMetric icon={<Route size={16} />} label="ACTIONS" value={plan?.summary.total_actions ?? 0} note="evidence-linked changes" />
          <PlanMetric icon={<TimerReset size={16} />} label="WAVE 01" value={plan?.summary.immediate_actions ?? 0} note="urgent / blocker-first" hot />
          <PlanMetric icon={<Cable size={16} />} label="HYBRID" value={plan?.summary.hybrid_actions ?? 0} note="transition actions" />
          <PlanMetric icon={<CircleGauge size={16} />} label="LOWEST READINESS" value={plan?.summary.lowest_agility_score ?? 0} note="higher is easier to migrate" danger={(plan?.summary.lowest_agility_score ?? 100) < 50} />
          <PlanMetric icon={<Boxes size={16} />} label="EFFORT" value={plan?.summary.total_effort_points ?? 0} note="relative planning points" />
          <PlanMetric icon={<TimerReset size={16} />} label="CALENDAR" value={plan?.summary.estimated_calendar_weeks ?? 0} note="estimated weeks" />
          <PlanMetric icon={<ShieldCheck size={16} />} label="DEFERRED" value={plan?.summary.deferred_actions ?? 0} note="outside change window" danger={(plan?.summary.deferred_actions ?? 0) > 0} />
        </section>

        {plan && <section className="plan-explanation panel-v2"><div><span className="kicker">APPLIED PLANNING POLICY</span><h2>{plan.constraints.mode === "performance" ? "Runtime-efficiency strategy" : plan.constraints.mode === "conservative" ? "Risk-minimizing strategy" : "Balanced transition strategy"}</h2><small>Roadmap risk basis: Z = {planHorizon} years</small></div><div>{plan.strategy_explanation.map((item)=><p key={item}>{item}</p>)}</div><div className="strategy-totals"><span><b>{plan.summary.actions_within_window}</b> actions inside {plan.constraints.change_window_weeks}w window</span><span><b>{plan.summary.deferred_actions}</b> deferred</span><span><b>{plan.summary.estimated_calendar_weeks}w</b> estimated program duration</span></div></section>}

        <section className="migration-grid">
          <article className="panel-v2 roadmap-card">
            <div className="panel-topline"><div><span className="kicker">MIGRATION SEQUENCE</span><h2>Dependency-safe execution order</h2></div>{plan && <span className="count-chip">{plan.waves.length} WAVES</span>}</div>
            {plan ? <RoadmapFlow plan={plan} selected={selected?.id ?? null} onSelect={setSelected} /> : <MigrationEmpty onGenerate={generate} running={running} />}
            {plan && <div className="standards-ribbon">{plan.standards_snapshot.map((item) => <span key={item}><ShieldCheck size={11} />{item}</span>)}</div>}
          </article>

          <aside className="panel-v2 migration-inspector">
            <div className="panel-topline"><div><span className="kicker">MIGRATION ACTION</span><h2>{selected?.label ?? "Select an action"}</h2></div>{selected && <span className={`priority-orb ${selected.priority_score >= 75 ? "critical" : selected.priority_score >= 55 ? "elevated" : "moderate"}`}>{selected.priority_score}</span>}</div>
            {selected ? <div className="migration-inspector-body">
              <div className="migration-action-meta"><span>WAVE {String(selected.wave).padStart(2, "0")}</span><span>{selected.effort_points} EFFORT PTS</span><span>{selected.estimated_weeks} EST. WEEKS</span><span>{selected.within_change_window ? "INSIDE CHANGE WINDOW" : "DEFERRED BY WINDOW"}</span></div>
              <div className="target-route">
                <div><small>CURRENT</small><strong>{selectedRecommendation?.current_primitive ?? "Detected primitive"}</strong></div>
                <ArrowRight size={18} />
                <div><small>TARGET</small><strong>{selected.target_profiles[0] ?? "Context review"}</strong></div>
              </div>
              {selectedRecommendation?.target_profiles.map((target) => <article key={target.name} className="target-profile"><div><GitPullRequestArrow size={14} /><strong>{target.name}</strong><span>{target.maturity}</span></div><p>{target.purpose}</p><small>{target.standard}</small></article>)}
              <Section title="WHY NOW" items={selected.rationale} />
              <Section title="PREREQUISITES" items={selectedRecommendation?.prerequisites ?? []} muted />
              <Section title="INTEROPERABILITY" items={selectedRecommendation?.interoperability_notes ?? []} muted />
              <div className="confidence-strip"><Sparkles size={13} /><span>recommendation confidence</span><strong>{Math.round((selectedRecommendation?.confidence.score ?? 0) * 100)}%</strong></div>
            </div> : <div className="empty-copy">Generate a roadmap, then select an action node.</div>}
          </aside>
        </section>

        {plan && <section className="wave-ledger panel-v2">
          <div className="panel-topline"><div><span className="kicker">EXECUTION LEDGER</span><h2>Migration actions by wave</h2></div><span className="count-chip">{actions.length} ACTIONS</span></div>
          <div className="wave-ledger-table">
            {plan.waves.map((wave) => <div className="wave-ledger-section" key={wave.wave}><div className="wave-ledger-head"><b>W{String(wave.wave).padStart(2, "0")}</b><strong>{wave.title}</strong><span>weeks {wave.starts_week}–{wave.ends_week} · {wave.estimated_duration_weeks}w · {wave.parallel_slots} parallel · {wave.within_change_window ? "inside window" : "outside window"}</span></div>{wave.actions.map((action) => <button key={action.id} className={`${selected?.id === action.id ? "selected" : ""}${!action.within_change_window ? " outside-window" : ""}`} onClick={() => setSelected(action)}><span className="action-dot" /><strong>{action.label}</strong><span>{action.target_profiles.join(" + ") || "resolve context"} · {action.estimated_weeks}w</span><b>{action.priority_score}</b></button>)}</div>)}
          </div>
        </section>}
      </div>
    </AppShell>
  );
}

function RefreshPlanDot() { return <i className="planning-pending-dot" aria-hidden="true" />; }

function PlanMetric({ icon, label, value, note, hot, danger }: { icon: React.ReactNode; label: string; value: number; note: string; hot?: boolean; danger?: boolean }) {
  return <article className={`plan-metric panel-v2${hot ? " hot" : ""}${danger ? " danger" : ""}`}><span>{icon}{label}</span><strong>{String(value).padStart(2, "0")}</strong><small>{note}</small></article>;
}

function Section({ title, items, muted }: { title: string; items: string[]; muted?: boolean }) {
  if (!items.length) return null;
  return <div className={`migration-section${muted ? " muted" : ""}`}><span className="kicker">{title}</span>{items.map((item) => <p key={item}>{item}</p>)}</div>;
}

function MigrationEmpty({ onGenerate, running }: { onGenerate: () => void; running: boolean }) {
  return <div className="migration-empty"><div className="migration-orbit"><i /><i /><i /><Route size={26} /></div><strong>NO MIGRATION ROADMAP MATERIALIZED</strong><p>Generate a plan to convert the latest evidence-linked scan into dependency-aware migration waves.</p><button className="ghost-action" onClick={onGenerate} disabled={running}>GENERATE NOW</button></div>;
}

function RoadmapFlow({ plan, selected, onSelect }: { plan: MigrationRoadmap; selected: string | null; onSelect: (action: MigrationAction) => void }) {
  const actions = plan.waves.flatMap((wave) => wave.actions);
  const width = Math.max(920, plan.waves.length * 255 + 150);
  const height = Math.max(440, Math.max(...plan.waves.map((wave) => wave.actions.length), 1) * 105 + 150);
  const positions = new Map<string, { x: number; y: number }>();
  plan.waves.forEach((wave, waveIndex) => wave.actions.forEach((action, actionIndex) => {
    positions.set(action.id, { x: 110 + waveIndex * 255, y: 105 + actionIndex * 105 });
  }));
  return <div className="roadmap-flow-wrap"><svg className="roadmap-flow" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Dependency-aware migration roadmap">
    <defs><marker id="migration-arrow" viewBox="0 -5 10 10" refX="25" markerWidth="5" markerHeight="5" orient="auto"><path d="M0,-5L10,0L0,5" /></marker><filter id="migration-glow"><feGaussianBlur stdDeviation="4" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter></defs>
    {plan.waves.map((wave, index) => <g key={`wave-title-${wave.wave}`}><text x={110 + index * 255} y="42" className="roadmap-wave-no">WAVE {String(wave.wave).padStart(2, "0")}</text><text x={110 + index * 255} y="61" className="roadmap-wave-title">{wave.title.slice(0, 30)}</text><line x1={110 + index * 255} x2={110 + index * 255} y1="76" y2={height - 38} className="wave-guide" /></g>)}
    {actions.flatMap((action) => action.prerequisite_action_ids.map((prereq) => {
      const from = positions.get(prereq); const to = positions.get(action.id); if (!from || !to) return null;
      const mid = (from.x + to.x) / 2;
      return <path key={`${prereq}-${action.id}`} d={`M${from.x + 25},${from.y} C${mid},${from.y} ${mid},${to.y} ${to.x - 25},${to.y}`} className="migration-link" markerEnd="url(#migration-arrow)" />;
    }))}
    {actions.map((action) => {
      const pos = positions.get(action.id)!;
      const isSelected = selected === action.id;
      return <g key={action.id} transform={`translate(${pos.x},${pos.y})`} className={`roadmap-node ${isSelected ? "selected" : ""}`} onClick={() => onSelect(action)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(action); } }} role="button" tabIndex={0} aria-label={`${action.label}, priority ${action.priority_score}`}>
        <circle r="28" className="roadmap-node-halo" />
        <circle r="18" className="roadmap-node-disc" filter="url(#migration-glow)" />
        <text y="4" textAnchor="middle" className="roadmap-node-score">{action.priority_score}</text>
        <text x="33" y="-5" className="roadmap-node-label">{action.label.slice(0, 28)}</text>
        <text x="33" y="12" className="roadmap-node-target">{action.target_profiles[0]?.slice(0, 28) ?? "context review"}</text>
      </g>;
    })}
  </svg></div>;
}
