"use client";

import {
  Activity, Archive, ArrowRight, BookOpenCheck, CheckCircle2, CloudCog, FileJson2, FolderSearch2, Import,
  KeyRound, Layers3, Network, PackagePlus, Play, ServerCog, ShieldCheck, Trash2, UploadCloud,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useRef, useState, type ChangeEvent } from "react";
import { AppShell, PageHeader } from "@/components/shell/AppShell";
import { runReferenceAssessment, scanMountedPath, uploadMultiSourceAssessment, type AssessmentUploadSource } from "@/lib/api";
import type { ScanSummary } from "@/lib/types";

type Mode = "sources" | "path" | "reference";
type SourceKind = AssessmentUploadSource["kind"];

type QueuedSource = AssessmentUploadSource & { id: string };
type ContextProfile = "evidence_first" | "general_enterprise" | "regulated_long_lived" | "custom";
type ContextLevel = "unknown" | "low" | "medium" | "high" | "critical";
type TriState = "unknown" | "yes" | "no";
type AssessmentForm = {
  display_name: string; environment: string; owner: string; team: string;
  quantum_horizon_years: number; data_lifetime_years: number | null; migration_time_years: number | null;
  data_sensitivity: ContextLevel; business_criticality: ContextLevel;
  public_exposure: TriState; confidentiality_required: TriState;
  context_profile: ContextProfile; assumption_basis: "operator" | "estimated";
};

const defaults: AssessmentForm = {
  display_name: "Enterprise Assessment",
  quantum_horizon_years: 15,
  data_lifetime_years: null,
  migration_time_years: null,
  data_sensitivity: "unknown",
  business_criticality: "unknown",
  environment: "Production",
  owner: "Security Architecture",
  team: "Platform Cryptography",
  public_exposure: "unknown",
  confidentiality_required: "unknown",
  context_profile: "evidence_first",
  assumption_basis: "operator",
};

const contextProfiles: Record<Exclude<ContextProfile, "custom">, Partial<AssessmentForm>> = {
  evidence_first: {
    data_lifetime_years: null, migration_time_years: null, data_sensitivity: "unknown", business_criticality: "unknown",
    public_exposure: "unknown", confidentiality_required: "unknown", assumption_basis: "operator",
  },
  general_enterprise: {
    data_lifetime_years: 5, migration_time_years: 3, data_sensitivity: "medium", business_criticality: "medium",
    public_exposure: "unknown", confidentiality_required: "unknown", assumption_basis: "estimated",
  },
  regulated_long_lived: {
    data_lifetime_years: 12, migration_time_years: 4, data_sensitivity: "high", business_criticality: "high",
    public_exposure: "yes", confidentiality_required: "yes", assumption_basis: "estimated",
  },
};

const sourceOptions: Array<{ kind: SourceKind; title: string; note: string; accept: string; icon: React.ReactNode }> = [
  { kind: "repository", title: "Repository archive", note: "ZIP / TAR / TGZ · source, config, dependencies and binaries", accept: ".zip,.tar,.tgz,.gz", icon: <Archive size={18}/> },
  { kind: "container_image", title: "Container image", note: "Docker save / OCI TAR · inspected offline, never executed", accept: ".tar,.tgz,.gz", icon: <ServerCog size={18}/> },
  { kind: "bom", title: "CycloneDX BOM", note: "Structured software / cryptographic inventory JSON", accept: ".json,application/json", icon: <FileJson2 size={18}/> },
  { kind: "connector", title: "Enterprise connector export", note: "TLS endpoint, cloud KMS or enterprise PKI JSON", accept: ".json,application/json", icon: <Network size={18}/> },
  { kind: "context", title: "QDeX enterprise context", note: "Optional ecdat.context.json · ownership, data lifetime and dependencies", accept: ".json,application/json", icon: <BookOpenCheck size={18}/> },
];

const kindLabel: Record<SourceKind, string> = {
  repository: "Repository",
  container_image: "Container image",
  bom: "CycloneDX BOM",
  connector: "Connector export",
  context: "Enterprise context",
};

function fileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

export function IntakeClient() {
  const [mode, setMode] = useState<Mode>("sources");
  const [sources, setSources] = useState<QueuedSource[]>([]);
  const [sourceKind, setSourceKind] = useState<SourceKind>("repository");
  const [path, setPath] = useState("/workspace/sample/asteria-financial");
  const [form, setForm] = useState(defaults);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScanSummary | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  const q = result?.quantum_summary;
  const summary = useMemo(() => result ? [
    ["Assets", result.findings.length],
    ["Quantum vulnerable", q?.vulnerable_assets ?? 0],
    ["HNDL exposed", q?.hndl_exposed_assets ?? 0],
    ["Migration blockers", q?.migration_blockers ?? 0],
  ] : [], [result, q]);

  const selectedOption = sourceOptions.find((item) => item.kind === sourceKind)!;

  function addFiles(event: ChangeEvent<HTMLInputElement>) {
    const chosen = Array.from(event.target.files ?? []);
    if (!chosen.length) return;
    const queued = chosen.map((file) => ({ id: `${Date.now()}-${Math.random().toString(16).slice(2)}`, file, kind: sourceKind }));
    setSources((current) => sourceKind === "context"
      ? [...current.filter((item) => item.kind !== "context"), queued[0]]
      : [...current, ...queued]);
    event.target.value = "";
  }

  function applyContextProfile(profile: Exclude<ContextProfile, "custom">) {
    setForm((current) => ({ ...current, ...contextProfiles[profile], context_profile: profile }));
  }

  function updateContext(patch: Partial<AssessmentForm>) {
    setForm((current) => ({ ...current, ...patch, context_profile: "custom", assumption_basis: "operator" }));
  }

  function riskContext() {
    return {
      quantum_horizon_years: form.quantum_horizon_years,
      data_lifetime_years: form.data_lifetime_years,
      migration_time_years: form.migration_time_years,
      data_sensitivity: form.data_sensitivity === "unknown" ? null : form.data_sensitivity,
      business_criticality: form.business_criticality === "unknown" ? null : form.business_criticality,
      public_exposure: form.public_exposure === "unknown" ? null : form.public_exposure === "yes",
      confidentiality_required: form.confidentiality_required === "unknown" ? null : form.confidentiality_required === "yes",
      context_profile: form.context_profile,
      assumption_basis: form.assumption_basis,
    };
  }

  async function run() {
    setRunning(true); setError(null); setResult(null);
    try {
      let next: ScanSummary;
      const context = riskContext();
      if (mode === "reference") {
        const { quantum_horizon_years: horizon, ...referenceContext } = context;
        next = await runReferenceAssessment(horizon, {
          display_name: form.display_name, environment: form.environment, owner: form.owner, team: form.team,
          ...referenceContext,
        });
      } else if (mode === "path") next = await scanMountedPath({ path, display_name: form.display_name, environment: form.environment, owner: form.owner, team: form.team, ...context });
      else {
        if (!sources.some((source) => source.kind !== "context")) throw new Error("Add at least one evidence source. Enterprise context is optional and cannot be assessed by itself.");
        next = await uploadMultiSourceAssessment(sources.map(({ file, kind }) => ({ file, kind })), {
          display_name: form.display_name, environment: form.environment, owner: form.owner, team: form.team, ...context,
        });
      }
      setResult(next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Intake failed");
    } finally { setRunning(false); }
  }

  return <AppShell><div className="page-wrap intake-page phase81-intake">
    <PageHeader eyebrow="ASSESSMENT / ENTERPRISE INPUT" title="NEW ASSESSMENT" />

    <section className="intake-layout phase81-intake-layout">
      <article className="panel-v2 intake-source-panel phase81-source-panel">
        <div className="panel-topline"><div><span className="kicker">STEP 1 / ASSESSMENT SCOPE</span></div><Import size={20} /></div>
        <div className="source-tabs phase81-mode-tabs">
          <SourceButton active={mode === "sources"} onClick={() => setMode("sources")} icon={<Layers3 size={17}/>} title="Supplied sources" note="Combine evidence sources and optional enterprise context" />
          <SourceButton active={mode === "path"} onClick={() => setMode("path")} icon={<FolderSearch2 size={17}/>} title="Mounted workspace" note="Analyze an authorized local path" />
          <SourceButton active={mode === "reference"} onClick={() => { setMode("reference"); applyContextProfile("regulated_long_lived"); }} icon={<Play size={17}/>} title="Demonstration environment" note="Included fictional enterprise showcase" />
        </div>

        {mode === "sources" && <div className="phase81-source-builder">
          <div className="phase81-source-picker">
            <div className="phase81-source-kind-grid">
              {sourceOptions.map((option) => <button key={option.kind} type="button" className={sourceKind === option.kind ? "active" : ""} onClick={() => setSourceKind(option.kind)}>
                {option.icon}<span><strong>{option.title}</strong><small>{option.note}</small></span>
              </button>)}
            </div>
            <input ref={fileInput} className="visually-hidden-file" type="file" multiple={sourceKind !== "context"} accept={selectedOption.accept} onChange={addFiles}/>
            <button className="phase81-add-source" type="button" onClick={() => fileInput.current?.click()}><PackagePlus size={18}/><span><strong>Add {selectedOption.title}</strong><small>{sourceKind === "context" ? "Add at most one validated ecdat.context.json file. It enriches planning context but never creates cryptographic findings." : "You can add several files of this type, then switch type and add more."}</small></span></button>
          </div>

          <div className="phase81-source-queue">
            <div className="phase81-source-queue-head"><div><span className="kicker">SOURCE QUEUE</span><h3>{sources.length ? `${sources.length} supplied item${sources.length === 1 ? "" : "s"}` : "No sources added yet"}</h3></div>{sources.length > 0 && <button type="button" onClick={() => setSources([])}>Clear queue</button>}</div>
            {sources.length ? <div className="phase81-source-list">{sources.map((source, index) => <div key={source.id} className="phase81-source-row">
              <b>{String(index + 1).padStart(2, "0")}</b><div><strong>{source.file.name}</strong><small>{kindLabel[source.kind]} · {fileSize(source.file.size)}</small></div><span>{kindLabel[source.kind]}</span><button type="button" aria-label={`Remove ${source.file.name}`} onClick={() => setSources((current) => current.filter((item) => item.id !== source.id))}><Trash2 size={16}/></button>
            </div>)}</div> : <div className="phase81-source-empty"><UploadCloud size={30}/></div>}
          </div>

          <div className="phase81-connector-explainer">
            <div><Network size={19}/><span><strong>TLS endpoint inventory</strong><small>Observed/configured TLS versions, key exchange and endpoint certificate metadata.</small></span></div>
            <div><CloudCog size={19}/><span><strong>Cloud KMS inventory</strong><small>Managed keys, algorithms, rotation state, provider and region.</small></span></div>
            <div><KeyRound size={19}/><span><strong>Enterprise PKI inventory</strong><small>Certificate algorithms, issuer/profile, expiry and owning service identifiers when supplied.</small></span></div>
            <p>OPERATIONAL EXPORTS - NOT FULL RUNTIME INSTRUMENTATION. ONCE SUPPLIED, THEY ENTER THE SAME PIPELINE FOR NORMALIZATION, GRAPHING, RISK, AND MIGRATION.</p>
          </div>
          <div className="phase85-context-intake-note"><BookOpenCheck size={18}/><div><strong>ENTERPRISE CONTEXT?</strong><p>Upload an <code>ecdat.context.json</code> alongside these sources to include ownership, criticalities, dependencies and business topology. Learn more in the <strong>Enterprise Context Guide</strong>.</p></div><Link href="/context-guide" className="ghost-action">OPEN CONTEXT GUIDE <ArrowRight size={13}/></Link></div>
        </div>}

        {mode === "path" && <label className="field-block phase81-mounted"><span>Mounted workspace path</span><input value={path} onChange={(e: ChangeEvent<HTMLInputElement>) => setPath(e.target.value)} /><small>Only paths inside configured scan roots are accepted. QDeX never deletes the original mounted directory during an assessment reset.</small></label>}
        {mode === "reference" && <div className="reference-disclosure"><ShieldCheck size={22} /><div><strong>DEMONSTRATION ENVIRONMENT</strong><p>This analyzes the bundled fictional Asteria Financial Services environment. It is demonstration input only; findings, relationships, risk and migration outputs still pass through the same analysis pipeline used for user-supplied assessments.</p></div></div>}
      </article>

      <article className="panel-v2 intake-context-panel phase9-context-panel">
        <div className="panel-topline"><div><span className="kicker">STEP 2 / RISK CONTEXT</span></div><ShieldCheck size={20} /></div>
        
        <div className="phase9-context-profiles" aria-label="Risk context starting profile">
          <button type="button" className={form.context_profile === "evidence_first" ? "active" : ""} onClick={() => applyContextProfile("evidence_first")}><strong>Evidence first</strong><small>No business assumptions beyond the quantum planning horizon.</small></button>
          <button type="button" className={form.context_profile === "general_enterprise" ? "active" : ""} onClick={() => applyContextProfile("general_enterprise")}><strong>General enterprise</strong><small>Estimated starter values; review before relying on prioritization.</small></button>
          <button type="button" className={form.context_profile === "regulated_long_lived" ? "active" : ""} onClick={() => applyContextProfile("regulated_long_lived")}><strong>Regulated / long-lived</strong><small>Estimated high-confidentiality planning profile.</small></button>
        </div>
        <div className="phase9-context-status"><span>{form.context_profile === "custom" ? "CUSTOM OPERATOR CONTEXT" : form.assumption_basis === "estimated" ? "ESTIMATED STARTING PROFILE" : "EVIDENCE-FIRST CONTEXT"}</span><p>Profiles are planning inputs, not discovered evidence. A supplied <code>ecdat.context.json</code> can later override these defaults at service/data-class scope.</p></div>

        <section className="phase91-context-group">
          <div className="phase91-context-group-head"><span>Assessment identity</span></div>
          <div className="intake-fields phase91-context-grid">
            <label><span>Assessment name</span><input value={form.display_name} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, display_name: e.target.value })} /></label>
            <label><span>Environment</span><input value={form.environment} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, environment: e.target.value })} /></label>
            <label><span>Owner</span><input value={form.owner} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, owner: e.target.value })} /></label>
            <label><span>Team</span><input value={form.team} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, team: e.target.value })} /></label>
          </div>
        </section>

        <section className="phase91-context-group planning">
          <div className="phase91-context-group-head"><span>Planning assumptions</span><p>QDeX never assumes Quantum arrival or Business criticalities themselves.</p></div>
          <div className="intake-fields phase91-context-grid">
            <label><span>Quantum planning horizon (Z)</span><div className="number-field"><input type="number" min="1" max="50" value={form.quantum_horizon_years} onChange={(e: ChangeEvent<HTMLInputElement>) => updateContext({ quantum_horizon_years: Number(e.target.value) || 15 })} /><b>years</b></div></label>
            <label><span>Data lifetime (X)</span><div className="number-field"><input type="number" min="0" max="100" placeholder="Unknown" value={form.data_lifetime_years ?? ""} onChange={(e: ChangeEvent<HTMLInputElement>) => updateContext({ data_lifetime_years: e.target.value === "" ? null : Number(e.target.value) })} /><b>years</b></div></label>
            <label><span>Migration lead time (Y)</span><div className="number-field"><input type="number" min="0" max="50" placeholder="Unknown" value={form.migration_time_years ?? ""} onChange={(e: ChangeEvent<HTMLInputElement>) => updateContext({ migration_time_years: e.target.value === "" ? null : Number(e.target.value) })} /><b>years</b></div></label>
            <label><span>Data sensitivity</span><select value={form.data_sensitivity} onChange={(e: ChangeEvent<HTMLSelectElement>) => updateContext({ data_sensitivity: e.target.value as ContextLevel })}><option value="unknown">Unknown</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label>
            <label><span>Business criticality</span><select value={form.business_criticality} onChange={(e: ChangeEvent<HTMLSelectElement>) => updateContext({ business_criticality: e.target.value as ContextLevel })}><option value="unknown">Unknown</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label>
            <label><span>Public exposure</span><select value={form.public_exposure} onChange={(e: ChangeEvent<HTMLSelectElement>) => updateContext({ public_exposure: e.target.value as TriState })}><option value="unknown">Unknown</option><option value="yes">Yes</option><option value="no">No</option></select></label>
            <label><span>Long-term confidentiality</span><select value={form.confidentiality_required} onChange={(e: ChangeEvent<HTMLSelectElement>) => updateContext({ confidentiality_required: e.target.value as TriState })}><option value="unknown">Unknown</option><option value="yes">Required</option><option value="no">Not required</option></select></label>
          </div>
        </section>
        <button className="primary-action intake-run" onClick={run} disabled={running || (mode === "sources" && !sources.some((source) => source.kind !== "context"))}>{running ? <Activity className="spin" size={17} /> : <Play size={16} fill="currentColor" />}{running ? "CORRELATING SUPPLIED EVIDENCE" : mode === "sources" ? `START ASSESSMENT · ${sources.filter((source) => source.kind !== "context").length} EVIDENCE SOURCE${sources.filter((source) => source.kind !== "context").length === 1 ? "" : "S"}` : "START ENTERPRISE ASSESSMENT"}</button>
        {error && <div className="inline-error">{error}</div>}
      </article>
    </section>

    {result && <section className="panel-v2 intake-result">
      <div className="result-mark"><CheckCircle2 size={25} /><div><span>ASSESSMENT COMPLETE</span><strong>{result.target.display_name}</strong><small>Scan {result.scan_id.slice(0, 8)} · {result.context_manifest_loaded ? "enterprise context linked" : "artifact / operator context only"}</small></div></div>
      <div className="result-metrics">{summary.map(([label, value]) => <div key={String(label)}><strong>{value}</strong><span>{label}</span></div>)}</div>
      {result.coverage && <div className={`intake-coverage${result.findings.length === 0 ? " zero" : ""}`}><strong>{result.findings.length === 0 ? "ZERO FINDINGS REQUIRES INTERPRETATION" : "ANALYSIS COVERAGE"}</strong><p>{result.findings.length === 0 ? `No supported cryptographic evidence was detected after inspecting ${result.coverage.files_observed} files with ${result.coverage.scanners_completed} analyzers. This does not prove the estate contains no cryptography.` : `${result.coverage.files_observed} files inspected · ${result.coverage.evidence_records} evidence records · ${Math.round((result.coverage.confidence_average ?? 0)*100)}% average evidence confidence.`}</p>{result.coverage.limitations.slice(0,3).map((item)=><span key={item}>{item}</span>)}</div>}
      <div className="result-actions"><Link href="/dashboard" className="ghost-action">OPEN EXECUTIVE OVERVIEW <ArrowRight size={13} /></Link><Link href="/investigate" className="ghost-action">INVESTIGATE ASSETS <ArrowRight size={13} /></Link><Link href="/migration" className="ghost-action">BUILD MIGRATION ROADMAP <ArrowRight size={13} /></Link></div>
    </section>}
  </div></AppShell>;
}

function SourceButton({ active, onClick, icon, title, note }: { active: boolean; onClick: () => void; icon: React.ReactNode; title: string; note: string }) {
  return <button className={active ? "active" : ""} onClick={onClick}>{icon}<span><strong>{title}</strong><small>{note}</small></span><ArrowRight size={13} /></button>;
}
