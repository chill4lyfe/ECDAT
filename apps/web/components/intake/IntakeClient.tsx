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

const defaults = {
  display_name: "Enterprise Assessment",
  quantum_horizon_years: 15,
  data_lifetime_years: 12,
  migration_time_years: 4,
  data_sensitivity: "high",
  business_criticality: "high",
  environment: "Production",
  owner: "Security Architecture",
  team: "Platform Cryptography",
  public_exposure: true,
  confidentiality_required: true,
};

const sourceOptions: Array<{ kind: SourceKind; title: string; note: string; accept: string; icon: React.ReactNode }> = [
  { kind: "repository", title: "Repository archive", note: "ZIP / TAR / TGZ · source, config, dependencies and binaries", accept: ".zip,.tar,.tgz,.gz", icon: <Archive size={18}/> },
  { kind: "container_image", title: "Container image", note: "Docker save / OCI TAR · inspected offline, never executed", accept: ".tar,.tgz,.gz", icon: <ServerCog size={18}/> },
  { kind: "bom", title: "CycloneDX BOM", note: "Structured software / cryptographic inventory JSON", accept: ".json,application/json", icon: <FileJson2 size={18}/> },
  { kind: "connector", title: "Enterprise connector export", note: "TLS endpoint, cloud KMS or enterprise PKI JSON", accept: ".json,application/json", icon: <Network size={18}/> },
  { kind: "context", title: "ECDAT enterprise context", note: "Optional ecdat.context.json · ownership, data lifetime and dependencies", accept: ".json,application/json", icon: <BookOpenCheck size={18}/> },
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

  async function run() {
    setRunning(true); setError(null); setResult(null);
    try {
      let next: ScanSummary;
      if (mode === "reference") next = await runReferenceAssessment(form.quantum_horizon_years, {
        display_name: form.display_name, environment: form.environment, owner: form.owner, team: form.team,
        data_lifetime_years: form.data_lifetime_years, migration_time_years: form.migration_time_years,
        data_sensitivity: form.data_sensitivity, business_criticality: form.business_criticality,
        public_exposure: form.public_exposure, confidentiality_required: form.confidentiality_required,
      });
      else if (mode === "path") next = await scanMountedPath({ path, ...form });
      else {
        if (!sources.some((source) => source.kind !== "context")) throw new Error("Add at least one evidence source. Enterprise context is optional and cannot be assessed by itself.");
        next = await uploadMultiSourceAssessment(sources.map(({ file, kind }) => ({ file, kind })), form);
      }
      setResult(next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Intake failed");
    } finally { setRunning(false); }
  }

  return <AppShell><div className="page-wrap intake-page phase81-intake">
    <PageHeader eyebrow="ASSESSMENT / ENTERPRISE INPUT" title="New Assessment" subtitle="Build one assessment from the exact systems you are authorized to review. ECDAT correlates evidence across repositories, container images, CycloneDX inventories and operational exports; optional enterprise context can add ownership and dependency knowledge without becoming cryptographic evidence." />

    <section className="intake-layout phase81-intake-layout">
      <article className="panel-v2 intake-source-panel phase81-source-panel">
        <div className="panel-topline"><div><span className="kicker">STEP 1 / ASSESSMENT SCOPE</span><h2>Choose the evidence ECDAT should combine</h2></div><Import size={19} /></div>
        <div className="source-tabs phase81-mode-tabs">
          <SourceButton active={mode === "sources"} onClick={() => setMode("sources")} icon={<Layers3 size={17}/>} title="Supplied sources" note="Combine evidence sources and optional enterprise context" />
          <SourceButton active={mode === "path"} onClick={() => setMode("path")} icon={<FolderSearch2 size={17}/>} title="Mounted workspace" note="Analyze an authorized local path" />
          <SourceButton active={mode === "reference"} onClick={() => setMode("reference")} icon={<Play size={17}/>} title="Demonstration environment" note="Included fictional enterprise showcase" />
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
            </div>)}</div> : <div className="phase81-source-empty"><UploadCloud size={25}/><p>Add only the systems needed for this assessment—for example two security-team repositories, two BOMs and one container image. ECDAT treats them as one evidence set and retains which source produced each finding.</p></div>}
          </div>

          <div className="phase81-connector-explainer">
            <div><Network size={19}/><span><strong>TLS endpoint inventory</strong><small>Observed/configured TLS versions, key exchange and endpoint certificate metadata.</small></span></div>
            <div><CloudCog size={19}/><span><strong>Cloud KMS inventory</strong><small>Managed keys, algorithms, rotation state, provider and region.</small></span></div>
            <div><KeyRound size={19}/><span><strong>Enterprise PKI inventory</strong><small>Certificate algorithms, issuer/profile, expiry and owning service identifiers when supplied.</small></span></div>
            <p>These are operational/control-plane exports—not a claim of full runtime instrumentation. When supplied, they become traceable evidence in the same normalization, graph, risk and migration pipeline as repository findings.</p>
          </div>
          <div className="phase85-context-intake-note"><BookOpenCheck size={18}/><div><strong>Enterprise context is optional</strong><p>Upload one <code>ecdat.context.json</code> alongside these sources when your organization can provide service ownership, protected-data lifetime or explicit dependencies. It changes interpretation and sequencing—not the underlying scanner evidence.</p></div><Link href="/context-guide" className="ghost-action">OPEN CONTEXT GUIDE <ArrowRight size={13}/></Link></div>
        </div>}

        {mode === "path" && <label className="field-block phase81-mounted"><span>Mounted workspace path</span><input value={path} onChange={(e: ChangeEvent<HTMLInputElement>) => setPath(e.target.value)} /><small>Only paths inside configured scan roots are accepted. ECDAT never deletes the original mounted directory during an assessment reset.</small></label>}
        {mode === "reference" && <div className="reference-disclosure"><ShieldCheck size={22} /><div><strong>DEMONSTRATION ENVIRONMENT</strong><p>This analyzes the bundled fictional Asteria Financial Services environment. It is demonstration input only; findings, relationships, risk and migration outputs still pass through the same analysis pipeline used for user-supplied assessments.</p></div></div>}
      </article>

      <article className="panel-v2 intake-context-panel">
        <div className="panel-topline"><div><span className="kicker">STEP 2 / PLANNING CONTEXT</span><h2>Assessment-wide planning assumptions</h2></div><ShieldCheck size={19} /></div>
        <p className="phase81-context-note">These values are explicit operator inputs used where richer enterprise context is unavailable. ECDAT does not infer business criticality or data lifetime from folder names.</p>
        <div className="intake-fields">
          <label><span>Assessment name</span><input value={form.display_name} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, display_name: e.target.value })} /></label>
          <label><span>Environment</span><input value={form.environment} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, environment: e.target.value })} /></label>
          <label><span>Owner</span><input value={form.owner} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, owner: e.target.value })} /></label>
          <label><span>Team</span><input value={form.team} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, team: e.target.value })} /></label>
          <label><span>Quantum planning horizon</span><div className="number-field"><input type="number" min="1" max="50" value={form.quantum_horizon_years} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, quantum_horizon_years: Number(e.target.value) })} /><b>years</b></div></label>
          <label><span>Data lifetime</span><div className="number-field"><input type="number" min="0" max="100" value={form.data_lifetime_years} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, data_lifetime_years: Number(e.target.value) })} /><b>years</b></div></label>
          <label><span>Migration lead time</span><div className="number-field"><input type="number" min="0" max="50" value={form.migration_time_years} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, migration_time_years: Number(e.target.value) })} /><b>years</b></div></label>
          <label><span>Data sensitivity</span><select value={form.data_sensitivity} onChange={(e: ChangeEvent<HTMLSelectElement>) => setForm({ ...form, data_sensitivity: e.target.value })}><option>low</option><option>medium</option><option>high</option><option>critical</option></select></label>
          <label><span>Business criticality</span><select value={form.business_criticality} onChange={(e: ChangeEvent<HTMLSelectElement>) => setForm({ ...form, business_criticality: e.target.value })}><option>low</option><option>medium</option><option>high</option><option>critical</option></select></label>
        </div>
        <div className="binary-context">
          <label><input type="checkbox" checked={form.public_exposure} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, public_exposure: e.target.checked })} /><span>Publicly exposed workload</span></label>
          <label><input type="checkbox" checked={form.confidentiality_required} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, confidentiality_required: e.target.checked })} /><span>Long-term confidentiality required</span></label>
        </div>
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
