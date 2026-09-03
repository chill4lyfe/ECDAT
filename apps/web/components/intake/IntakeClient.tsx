"use client";

import { Activity, Archive, ArrowRight, CheckCircle2, FileJson2, FolderSearch2, Import, Play, ShieldCheck, UploadCloud } from "lucide-react";
import Link from "next/link";
import { useMemo, useState, type ChangeEvent } from "react";
import { AppShell, PageHeader } from "@/components/shell/AppShell";
import { runReferenceAssessment, scanMountedPath, uploadContainerArchive, uploadCycloneDx, uploadEnterpriseArchive } from "@/lib/api";
import type { ScanSummary } from "@/lib/types";

type Mode = "archive" | "container" | "path" | "bom" | "reference";

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

export function IntakeClient() {
  const [mode, setMode] = useState<Mode>("archive");
  const [file, setFile] = useState<File | null>(null);
  const [path, setPath] = useState("/workspace/sample/asteria-financial");
  const [form, setForm] = useState(defaults);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScanSummary | null>(null);

  const q = result?.quantum_summary;
  const summary = useMemo(() => result ? [
    ["Assets", result.findings.length],
    ["Quantum vulnerable", q?.vulnerable_assets ?? 0],
    ["HNDL exposed", q?.hndl_exposed_assets ?? 0],
    ["Migration blockers", q?.migration_blockers ?? 0],
  ] : [], [result, q]);

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
      else if (mode === "container") {
        if (!file) throw new Error("Choose a Docker/OCI image TAR first.");
        next = await uploadContainerArchive(file, form);
      } else if (mode === "bom") {
        if (!file) throw new Error("Choose a CycloneDX JSON file first.");
        next = await uploadCycloneDx(file, form);
      } else {
        if (!file) throw new Error("Choose a ZIP/TAR archive first.");
        next = await uploadEnterpriseArchive(file, form);
      }
      setResult(next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Intake failed");
    } finally { setRunning(false); }
  }

  return <AppShell><div className="page-wrap intake-page">
    <PageHeader eyebrow="ENTERPRISE INTAKE / NEW ASSESSMENT" title="New Assessment" subtitle="Upload a repository archive, offline Docker/OCI image TAR or CycloneDX BOM, scan a mounted workspace, or load the bundled reference estate. ECDAT derives findings from supplied artifacts; the graph and migration plan are not pre-scripted." />

    <section className="intake-layout">
      <article className="panel-v2 intake-source-panel">
        <div className="panel-topline"><div><span className="kicker">01 / SOURCE</span><h2>Choose enterprise input</h2></div><Import size={17} /></div>
        <div className="source-tabs">
          <SourceButton active={mode === "archive"} onClick={() => { setMode("archive"); setFile(null); }} icon={<Archive size={16} />} title="Repository archive" note="ZIP / TAR / TGZ" />
          <SourceButton active={mode === "container"} onClick={() => { setMode("container"); setFile(null); }} icon={<Archive size={16} />} title="Container image" note="docker save / OCI TAR" />
          <SourceButton active={mode === "bom"} onClick={() => { setMode("bom"); setFile(null); }} icon={<FileJson2 size={16} />} title="CycloneDX BOM" note="Machine-readable inventory" />
          <SourceButton active={mode === "path"} onClick={() => setMode("path")} icon={<FolderSearch2 size={16} />} title="Mounted path" note="Advanced / local workspace" />
          <SourceButton active={mode === "reference"} onClick={() => setMode("reference")} icon={<Play size={16} />} title="Reference estate" note="Fictional showcase enterprise" />
        </div>

        {(mode === "archive" || mode === "container" || mode === "bom") && <label className={`drop-zone ${file ? "loaded" : ""}`}>
          <input type="file" accept={mode === "bom" ? ".json,application/json" : mode === "container" ? ".tar,.tgz,.gz" : ".zip,.tar,.tgz,.gz"} onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0] ?? null)} />
          {file ? <><CheckCircle2 size={28} /><strong>{file.name}</strong><span>{(file.size / 1024 / 1024).toFixed(2)} MB · ready for secure intake</span></> : <><UploadCloud size={30} /><strong>SELECT {mode === "bom" ? "CYCLONEDX JSON" : mode === "container" ? "CONTAINER IMAGE TAR" : "ENTERPRISE ARCHIVE"}</strong><span>Archive extraction rejects path traversal, symbolic links and oversized payloads.</span></>}
        </label>}

        {mode === "path" && <label className="field-block"><span>MOUNTED WORKSPACE PATH</span><input value={path} onChange={(e: ChangeEvent<HTMLInputElement>) => setPath(e.target.value)} /><small>Only paths inside configured scan roots are accepted.</small></label>}
        {mode === "reference" && <div className="reference-disclosure"><ShieldCheck size={20} /><div><strong>REFERENCE ENTERPRISE INPUT</strong><p>This scans the bundled fictional Asteria Financial Services estate. Its source artifacts are sample input; findings, graph relationships, risk and migration output are derived by the same analysis pipeline used for uploaded estates.</p></div></div>}
      </article>

      <article className="panel-v2 intake-context-panel">
        <div className="panel-topline"><div><span className="kicker">02 / CONTEXT</span><h2>Risk assumptions</h2></div><ShieldCheck size={17} /></div>
        <div className="intake-fields">
          <label><span>Assessment name</span><input value={form.display_name} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, display_name: e.target.value })} /></label>
          <label><span>Environment</span><input value={form.environment} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, environment: e.target.value })} /></label>
          <label><span>Owner</span><input value={form.owner} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, owner: e.target.value })} /></label>
          <label><span>Team</span><input value={form.team} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, team: e.target.value })} /></label>
          <label><span>Quantum horizon</span><div className="number-field"><input type="number" min="1" max="50" value={form.quantum_horizon_years} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, quantum_horizon_years: Number(e.target.value) })} /><b>years</b></div></label>
          <label><span>Data lifetime</span><div className="number-field"><input type="number" min="0" max="100" value={form.data_lifetime_years} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, data_lifetime_years: Number(e.target.value) })} /><b>years</b></div></label>
          <label><span>Migration lead time</span><div className="number-field"><input type="number" min="0" max="50" value={form.migration_time_years} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, migration_time_years: Number(e.target.value) })} /><b>years</b></div></label>
          <label><span>Data sensitivity</span><select value={form.data_sensitivity} onChange={(e: ChangeEvent<HTMLSelectElement>) => setForm({ ...form, data_sensitivity: e.target.value })}><option>low</option><option>medium</option><option>high</option><option>critical</option></select></label>
          <label><span>Business criticality</span><select value={form.business_criticality} onChange={(e: ChangeEvent<HTMLSelectElement>) => setForm({ ...form, business_criticality: e.target.value })}><option>low</option><option>medium</option><option>high</option><option>critical</option></select></label>
        </div>
        <div className="binary-context">
          <label><input type="checkbox" checked={form.public_exposure} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, public_exposure: e.target.checked })} /><span>Publicly exposed workload</span></label>
          <label><input type="checkbox" checked={form.confidentiality_required} onChange={(e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, confidentiality_required: e.target.checked })} /><span>Long-term confidentiality required</span></label>
        </div>
        <button className="primary-action intake-run" onClick={run} disabled={running}>{running ? <Activity className="spin" size={16} /> : <Play size={15} fill="currentColor" />}{running ? "ANALYZING SUPPLIED ARTIFACTS" : "START ENTERPRISE ASSESSMENT"}</button>
        {error && <div className="inline-error">{error}</div>}
      </article>
    </section>

    {result && <section className="panel-v2 intake-result">
      <div className="result-mark"><CheckCircle2 size={25} /><div><span>ASSESSMENT COMPLETE</span><strong>{result.target.display_name}</strong><small>Scan {result.scan_id.slice(0, 8)} · {result.context_manifest_loaded ? "enterprise context linked" : "artifact-only context"}</small></div></div>
      <div className="result-metrics">{summary.map(([label, value]) => <div key={String(label)}><strong>{value}</strong><span>{label}</span></div>)}</div>
      {result.coverage && <div className={`intake-coverage${result.findings.length === 0 ? " zero" : ""}`}><strong>{result.findings.length === 0 ? "ZERO FINDINGS REQUIRES INTERPRETATION" : "ANALYSIS COVERAGE"}</strong><p>{result.findings.length === 0 ? `No supported cryptographic evidence was detected after inspecting ${result.coverage.files_observed} files with ${result.coverage.scanners_completed} analyzers. This does not prove the estate contains no cryptography.` : `${result.coverage.files_observed} files inspected · ${result.coverage.evidence_records} evidence records · ${Math.round((result.coverage.confidence_average ?? 0)*100)}% average evidence confidence.`}</p>{result.coverage.limitations.slice(0,3).map((item)=><span key={item}>{item}</span>)}</div>}
      <div className="result-actions"><Link href="/dashboard" className="ghost-action">OPEN EXECUTIVE OVERVIEW <ArrowRight size={13} /></Link><Link href="/investigate" className="ghost-action">INVESTIGATE ASSETS <ArrowRight size={13} /></Link><Link href="/migration" className="ghost-action">BUILD MIGRATION ROADMAP <ArrowRight size={13} /></Link></div>
    </section>}
  </div></AppShell>;
}

function SourceButton({ active, onClick, icon, title, note }: { active: boolean; onClick: () => void; icon: React.ReactNode; title: string; note: string }) {
  return <button className={active ? "active" : ""} onClick={onClick}>{icon}<span><strong>{title}</strong><small>{note}</small></span><ArrowRight size={13} /></button>;
}
