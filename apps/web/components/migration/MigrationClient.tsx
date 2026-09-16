"use client";

import { Activity, ArrowRight, Boxes, Cable, CheckCircle2, ChevronDown, ChevronRight, CircleGauge, Clock3, GitPullRequestArrow, ListChecks, Network, Play, Route, Search, ShieldAlert, ShieldCheck, SlidersHorizontal, Sparkles, TimerReset, TriangleAlert } from "lucide-react";
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
  const [ledgerQuery, setLedgerQuery] = useState("");
  const [expandedStages, setExpandedStages] = useState<Set<number>>(() => new Set());

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
  const criticalPathLabels = useMemo(() => {
    if (!plan) return [];
    const byId = new Map(actions.map((action) => [action.id, action.label]));
    return plan.critical_path.map((id) => byId.get(id) ?? id);
  }, [actions, plan]);
  const servicesAffected = useMemo(() => new Set(actions.flatMap((action) => action.affected_service_ids)).size, [actions]);
  const urgentActions = actions.filter((action) => action.priority_score >= 75).length;
  const dependencyAware = plan?.sequencing_mode !== "evidence_prioritized";
  const executionLabel = dependencyAware ? "wave" : "stage";
  const graphLabelById = useMemo(() => new Map((scan?.graph_nodes ?? []).map((node) => [node.id, node.label])), [scan]);
  const ledgerWaves = useMemo(() => {
    if (!plan) return [];
    const needle = ledgerQuery.trim().toLowerCase();
    if (!needle) return plan.waves;
    return plan.waves.map((wave) => ({
      ...wave,
      actions: wave.actions.filter((action) => {
        const contexts = action.affected_service_ids.map((id) => graphLabelById.get(id) ?? id).join(" ");
        const haystack = [wave.title, action.label, action.target_profiles.join(" "), contexts, action.rationale.join(" ")].join(" ").toLowerCase();
        return haystack.includes(needle);
      }),
    })).filter((wave) => wave.actions.length > 0);
  }, [plan, ledgerQuery, graphLabelById]);

  const toggleStage = (wave: number) => setExpandedStages((current) => {
    const next = new Set(current);
    if (next.has(wave)) next.delete(wave); else next.add(wave);
    return next;
  });

  return (
    <AppShell>
      <div className="page-wrap migration-page">
        <PageHeader
          eyebrow="PLANNING / MIGRATION PROGRAMME"
          title="MIGRATION PLANNER"
          actions={<button className="primary-action" onClick={generate} disabled={running}>{running ? <Activity className="spin" size={16} /> : <Play size={15} fill="currentColor" />}{running ? "Planning" : plan ? "Rebuild Roadmap" : scan ? "Generate Roadmap" : "Load Demonstration + Plan"}</button>}
        />

        {error && <div className="error-strip"><TriangleAlert size={15} />{error}</div>}

        <section className="migration-control panel-v2">
          <div className="control-intro"><SlidersHorizontal size={18} /><div><strong>Planning constraints</strong><span>These controls alter target profiles, concurrency and scheduling. They do not create a new assessment record.</span></div></div>
          <div className="mode-switch">
            {(["performance", "balanced", "conservative"] as const).map((mode) => <button key={mode} className={constraints.mode === mode ? "active" : ""} onClick={() => setConstraints((value) => ({ ...value, mode }))}>{mode}</button>)}
          </div>
          <div className="mode-explanation"><strong>{constraints.mode === "performance" ? "Runtime efficiency" : constraints.mode === "conservative" ? "Risk-minimizing" : "Balanced transition"}</strong><span>{constraints.mode === "performance" ? "Favors smaller standardized profiles and lower runtime overhead where context permits." : constraints.mode === "conservative" ? "Favors stronger profiles, additional validation and more cautious sequencing at greater effort." : "Balances standardized security margin, interoperability and implementation cost."}</span></div>
          <label className="micro-slider migration-horizon"><span>QUANTUM PLANNING HORIZON (Z)</span><input type="range" min="8" max="30" value={horizon} onChange={(event) => setHorizon(Number(event.target.value))} /><output>{horizon}y</output><small>Re-evaluates exposure for planning; does not create a new assessment.</small></label>
          <label className="hybrid-toggle"><input type="checkbox" checked={constraints.prefer_hybrid} onChange={(event) => setConstraints((value) => ({ ...value, prefer_hybrid: event.target.checked }))} /><i /><span>Prefer hybrid transition</span></label>
          <label className="micro-slider"><span>PARALLEL ACTIONS</span><input type="range" min="1" max="6" value={constraints.max_parallel_actions} onChange={(event) => setConstraints((value) => ({ ...value, max_parallel_actions: Number(event.target.value) }))} /><output>{constraints.max_parallel_actions}</output></label>
          <label className="micro-slider"><span>CHANGE WINDOW</span><input type="range" min="4" max="32" value={constraints.change_window_weeks} onChange={(event) => setConstraints((value) => ({ ...value, change_window_weeks: Number(event.target.value) }))} /><output>{constraints.change_window_weeks}w</output></label>
          {controlsDiffer && <div className="planning-pending"><RefreshPlanDot /><span><strong>Planning controls changed.</strong> Rebuild the roadmap to apply these values; the metrics and sequence below still represent the last generated plan.</span></div>}
        </section>

        <section className="migration-metrics">
          <PlanMetric icon={<Route size={16} />} label="ACTIONS" value={plan?.summary.total_actions ?? 0} note="evidence-linked changes" />
          <PlanMetric icon={<TimerReset size={16} />} label={dependencyAware ? "WAVE 01" : "STAGE 01"} value={plan?.summary.immediate_actions ?? 0} note={dependencyAware ? "urgent / blocker-first" : "first prioritized work group"} hot />
          <PlanMetric icon={<Cable size={16} />} label="HYBRID" value={plan?.summary.hybrid_actions ?? 0} note="transition actions" />
          <PlanMetric icon={<CircleGauge size={16} />} label="LOWEST READINESS" value={plan?.summary.lowest_agility_score ?? 0} note="higher score means easier transition" danger={(plan?.summary.lowest_agility_score ?? 100) < 50} />
          <PlanMetric icon={<Boxes size={16} />} label="EFFORT" value={plan?.summary.total_effort_points ?? 0} note="relative planning points" />
          <PlanMetric icon={<TimerReset size={16} />} label="CALENDAR" value={plan?.summary.estimated_calendar_weeks ?? 0} note="estimated weeks" />
          <PlanMetric icon={<ShieldCheck size={16} />} label="DEFERRED" value={plan?.summary.deferred_actions ?? 0} note="outside change window" danger={(plan?.summary.deferred_actions ?? 0) > 0} />
        </section>

        {plan && <section className="phase8-plan-brief panel-v2">
          <div className="phase8-plan-brief-copy">
            <span className="kicker">ROADMAP DECISION BRIEF</span>
            <h2>QDeX built a dependency-safe execution plan, driven by your policies, blockers, and timelines.</h2>
            </div>
          <div className="phase8-plan-brief-grid">
            <article><Network size={18} /><div><strong>{servicesAffected}</strong><span>affected service contexts</span></div></article>
            <article><ShieldAlert size={18} /><div><strong>{urgentActions}</strong><span>high-priority actions</span></div></article>
            <article><Clock3 size={18} /><div><strong>{plan.summary.estimated_calendar_weeks} weeks</strong><span>estimated programme envelope</span></div></article>
            <article><CheckCircle2 size={18} /><div><strong>{plan.summary.actions_within_window}/{plan.summary.total_actions}</strong><span>actions start inside change window</span></div></article>
          </div>
          <div className="phase8-critical-path">
            <div><ListChecks size={17} /><strong>{dependencyAware ? "Critical path" : "Dependency status"}</strong><span>{dependencyAware ? (criticalPathLabels.length ? `${criticalPathLabels.length} dependent actions` : "No dependent chain identified") : "Topology not supplied"}</span></div>
            <p>{dependencyAware ? (criticalPathLabels.length ? criticalPathLabels.join("  →  ") : "No multi-action prerequisite chain is visible in the supplied dependency topology.") : "QDeX will not fabricate a dependency critical path. Add enterprise context when the organization is ready to convert these evidence-prioritized stages into dependency-safe migration waves."}</p>
          </div>
        </section>}

        {plan && <section className="plan-explanation panel-v2"><div><span className="kicker">CURRENT PLANNING POLICY</span><h2>{plan.constraints.mode === "performance" ? "Runtime-efficiency strategy" : plan.constraints.mode === "conservative" ? "Risk-minimizing strategy" : "Balanced transition strategy"}</h2><small>Roadmap risk basis: Z = {planHorizon} years</small></div><div>{plan.strategy_explanation.map((item)=><p key={item}>{item}</p>)}</div><div className="strategy-totals"><span><b>{plan.summary.actions_within_window}</b> actions inside {plan.constraints.change_window_weeks}w window</span><span><b>{plan.summary.deferred_actions}</b> deferred</span><span><b>{plan.summary.estimated_calendar_weeks}w</b> estimated program duration</span></div></section>}

        <section className="migration-grid">
          <article className="panel-v2 roadmap-card">
            <div className="panel-topline"><div><span className="kicker">{dependencyAware ? "MIGRATION WAVES" : "EXECUTION STAGES"}</span><h2>{dependencyAware ? "Dependency-aware execution sequence" : "Evidence-prioritized engineering sequence"}</h2></div>{plan && <span className="count-chip">{plan.waves.length} {dependencyAware ? "WAVES" : "STAGES"}</span>}</div>
            {plan ? <RoadmapFlow plan={plan} selected={selected?.id ?? null} onSelect={setSelected} contextLabels={graphLabelById} /> : <MigrationEmpty onGenerate={generate} running={running} />}
            {plan && <div className="standards-ribbon">{plan.standards_snapshot.map((item) => <span key={item}><ShieldCheck size={11} />{item}</span>)}</div>}
          </article>

          <aside className="panel-v2 migration-inspector">
            <div className="panel-topline"><div><span className="kicker">SELECTED ACTION</span><h2>{selected?.label ?? "Select an action"}</h2></div>{selected && <span className={`priority-orb ${selected.priority_score >= 75 ? "critical" : selected.priority_score >= 55 ? "elevated" : "moderate"}`}>{selected.priority_score}</span>}</div>
            {selected ? <div className="migration-inspector-body">
              <div className="migration-action-meta"><span>{executionLabel.toUpperCase()} {String(selected.wave).padStart(2, "0")}</span><span>{selected.effort_points} EFFORT PTS</span><span>{selected.estimated_weeks} EST. WEEKS</span><span>{selected.within_change_window ? "INSIDE CHANGE WINDOW" : "DEFERRED BY WINDOW"}</span></div>
              <div className="target-route">
                <div><small>CURRENT</small><strong>{selectedRecommendation?.current_primitive ?? "Detected primitive"}</strong></div>
                <ArrowRight size={18} />
                <div><small>TARGET</small><strong>{selected.target_profiles[0] ?? "Context review"}</strong></div>
              </div>
              {selectedRecommendation?.target_profiles.map((target) => <article key={target.name} className="target-profile"><div><GitPullRequestArrow size={14} /><strong>{target.name}</strong><span>{target.maturity}</span></div><p>{target.purpose}</p><small>{target.standard}</small></article>)}
              {selected.affected_service_ids.length > 0 && <div className="phase8-affected-services"><span className="kicker">AFFECTED SYSTEM / SOURCE CONTEXTS</span><div>{selected.affected_service_ids.map((service) => <span key={service}>{graphLabelById.get(service) ?? service.replace(/^service:/, "").replace(/^source:/, "").replaceAll("-", " ")}</span>)}</div></div>}
              <Section title="WHY THIS IS PRIORITIZED" items={selected.rationale} />
              <Section title="PREREQUISITES" items={selectedRecommendation?.prerequisites ?? []} muted />
              <Section title="INTEROPERABILITY NOTES" items={selectedRecommendation?.interoperability_notes ?? []} muted />
              {selectedRecommendation && <div className={`recommendation-confidence confidence-${selectedRecommendation.confidence.level}`}>
                <div className="recommendation-confidence-head"><Sparkles size={14}/><span>RECOMMENDATION CONFIDENCE</span><strong>{Math.round(selectedRecommendation.confidence.score * 100)}% · {selectedRecommendation.confidence.level.toUpperCase()}</strong></div>
                <div className="recommendation-confidence-bar" aria-label={`Recommendation confidence ${Math.round(selectedRecommendation.confidence.score * 100)} percent`}><i style={{width:`${Math.round(selectedRecommendation.confidence.score * 100)}%`}}/></div>
                <p>This is confidence in the migration recommendation, not the asset's risk score.</p>
                <div className="recommendation-confidence-reasons"><span className="kicker">WHY THIS CONFIDENCE</span>{selectedRecommendation.confidence.reasons.map((reason) => <div key={reason}><CheckCircle2 size={12}/><span>{reason}</span></div>)}</div>
              </div>}
            </div> : <div className="empty-copy">Generate a roadmap, then select an action node.</div>}
          </aside>
        </section>

        {plan && <section className="wave-ledger panel-v2">
          <div className="panel-topline wave-ledger-top"><div><span className="kicker">PROGRAMME EXECUTION LEDGER</span><h2>Migration actions grouped by execution {executionLabel}</h2><p>Search the programme or expand only the {executionLabel} you need. Large assessments stay compact until you choose a work group.</p></div><span className="count-chip">{actions.length} ACTIONS</span></div>
          <div className="wave-ledger-tools"><label className="search-box"><Search size={14}/><input value={ledgerQuery} onChange={(event) => setLedgerQuery(event.target.value)} placeholder="Search action, target, system or rationale…"/></label><span>{ledgerQuery.trim() ? `${ledgerWaves.reduce((count, wave) => count + wave.actions.length, 0)} matching actions` : `${plan.waves.length} ${dependencyAware ? "waves" : "stages"} · collapsed by default`}</span></div>
          <div className="wave-ledger-table">
            {ledgerWaves.map((wave) => { const open = Boolean(ledgerQuery.trim()) || expandedStages.has(wave.wave); return <div className="wave-ledger-section" key={wave.wave}><button type="button" className="wave-ledger-head" onClick={() => !ledgerQuery.trim() && toggleStage(wave.wave)} aria-expanded={open}><b>{dependencyAware ? "W" : "S"}{String(wave.wave).padStart(2, "0")}</b><strong>{wave.title}</strong><span>weeks {wave.starts_week}–{wave.ends_week} · {wave.estimated_duration_weeks}w · {wave.parallel_slots} parallel · {wave.actions.length} action{wave.actions.length === 1 ? "" : "s"}</span><i>{open ? <ChevronDown size={15}/> : <ChevronRight size={15}/>}</i></button>{open && <div className="wave-ledger-actions">{wave.actions.map((action) => <button key={action.id} className={`${selected?.id === action.id ? "selected" : ""}${!action.within_change_window ? " outside-window" : ""}`} onClick={() => setSelected(action)}><span className="action-dot" /><strong>{action.label}</strong><span>{action.target_profiles.join(" + ") || "resolve context"} · {action.estimated_weeks}w</span><b>{action.priority_score}</b></button>)}</div>}</div>; })}
            {ledgerWaves.length === 0 && <div className="wave-ledger-empty">No migration actions match this search.</div>}
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
  return <div className="migration-empty"><div className="migration-orbit"><i /><i /><i /><Route size={26} /></div><strong>NO MIGRATION ROADMAP AVAILABLE</strong><p>Generate a roadmap from the latest evidence-linked assessment. QDeX will use dependency-aware waves when topology exists, or evidence-prioritized execution stages when it does not.</p><button className="ghost-action" onClick={onGenerate} disabled={running}>Generate Roadmap</button></div>;
}

function RoadmapFlow({ plan, selected, onSelect, contextLabels }: { plan: MigrationRoadmap; selected: string | null; onSelect: (action: MigrationAction) => void; contextLabels: Map<string, string> }) {
  const actions = plan.waves.flatMap((wave) => wave.actions);
  const dense = actions.length > 90;
  const visibleByWave = new Map<number, MigrationAction[]>();
  for (const wave of plan.waves) {
    if (!dense) { visibleByWave.set(wave.wave, wave.actions); continue; }
    const selectedAction = selected ? wave.actions.find((action) => action.id === selected) : undefined;
    const top = [...wave.actions].sort((a, b) => b.priority_score - a.priority_score).slice(0, selectedAction ? 7 : 8);
    if (selectedAction && !top.some((action) => action.id === selectedAction.id)) top.push(selectedAction);
    visibleByWave.set(wave.wave, top);
  }
  const displayActions = plan.waves.flatMap((wave) => visibleByWave.get(wave.wave) ?? []);
  const stageWidth = dense ? 330 : 300;
  const stageStart = 132;
  const width = Math.max(920, plan.waves.length * stageWidth + 190);
  const maxVisible = Math.max(...plan.waves.map((wave) => (visibleByWave.get(wave.wave) ?? []).length), 1);
  const rowHeight = dense ? 94 : 110;
  const height = Math.max(470, maxVisible * rowHeight + (dense ? 190 : 165));
  const positions = new Map<string, { x: number; y: number }>();
  plan.waves.forEach((wave, waveIndex) => (visibleByWave.get(wave.wave) ?? []).forEach((action, actionIndex) => {
    positions.set(action.id, { x: stageStart + waveIndex * stageWidth, y: 126 + actionIndex * rowHeight });
  }));
  const dependencyAware = plan.sequencing_mode !== "evidence_prioritized";
  return <div className={`roadmap-flow-wrap${dense ? " dense-plan" : ""}`}>{dense && <div className="roadmap-density-note"><strong>LARGE PLAN OVERVIEW</strong><span>Showing the highest-priority actions in each {dependencyAware ? "wave" : "stage"}; all {actions.length} actions remain searchable in the execution ledger below.</span></div>}<svg className="roadmap-flow" style={{ width: `${width}px`, minWidth: `${width}px` }} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={dependencyAware ? "Dependency-aware migration roadmap" : "Evidence-prioritized migration execution stages"}>
    <defs><marker id="migration-arrow" viewBox="0 -5 10 10" refX="25" markerWidth="5" markerHeight="5" orient="auto"><path d="M0,-5L10,0L0,5" /></marker><filter id="migration-glow"><feGaussianBlur stdDeviation={dense ? "2" : "4"} result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter></defs>
    {plan.waves.map((wave, index) => { const x = stageStart + index * stageWidth; return <g key={`wave-title-${wave.wave}`}><text x={x} y="42" className="roadmap-wave-no">{dependencyAware ? "WAVE" : "STAGE"} {String(wave.wave).padStart(2, "0")}</text><text x={x} y="64" className="roadmap-wave-title">{wave.title.slice(0, 38)}</text><text x={x} y="84" className="roadmap-wave-count">{wave.actions.length} action{wave.actions.length === 1 ? "" : "s"}</text><line x1={x} x2={x} y1="98" y2={height - 38} className="wave-guide" /></g>; })}
    {!dense && displayActions.flatMap((action) => action.prerequisite_action_ids.map((prereq) => {
      const from = positions.get(prereq); const to = positions.get(action.id); if (!from || !to) return null;
      const mid = (from.x + to.x) / 2;
      return <path key={`${prereq}-${action.id}`} d={`M${from.x + 25},${from.y} C${mid},${from.y} ${mid},${to.y} ${to.x - 25},${to.y}`} className="migration-link" markerEnd="url(#migration-arrow)" />;
    }))}
    {displayActions.map((action) => {
      const pos = positions.get(action.id)!;
      const isSelected = selected === action.id;
      return <g key={action.id} transform={`translate(${pos.x},${pos.y})`} className={`roadmap-node ${isSelected ? "selected" : ""}`} onClick={() => onSelect(action)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(action); } }} role="button" tabIndex={0} aria-label={`${action.label}, priority ${action.priority_score}`}>
        <circle r={dense ? "23" : "28"} className="roadmap-node-halo" />
        <circle r={dense ? "15" : "18"} className="roadmap-node-disc" filter="url(#migration-glow)" />
        <text y="4" textAnchor="middle" className="roadmap-node-score">{action.priority_score}</text>
        <text x="36" y="-7" className="roadmap-node-label">{action.label.slice(0, dense ? 33 : 31)}</text>
        <text x="36" y="12" className="roadmap-node-target">{action.target_profiles[0]?.slice(0, 34) ?? "context review"}</text>
        <text x="36" y="30" className="roadmap-node-context">{action.affected_service_ids.length ? (contextLabels.get(action.affected_service_ids[0]) ?? action.affected_service_ids[0].replace(/^service:/, "").replace(/^source:/, "")).slice(0, 34) : "unowned evidence"}</text>
      </g>;
    })}
  </svg></div>;
}
