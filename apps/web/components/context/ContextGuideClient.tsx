"use client";

import { ArrowRight, BookOpenCheck, Boxes, Building2, CheckCircle2, Database, Download, FileJson2, GitBranch, Info, Network, Plus, ScanSearch, ShieldCheck, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { AppShell, PageHeader } from "@/components/shell/AppShell";
import { fetchLatestScan } from "@/lib/api";
import type { ScanSummary } from "@/lib/types";

type DataClassDraft = { id: string; name: string; sensitivity: string; lifetime: string };
type ServiceDraft = { id: string; name: string; prefixes: string; criticality: string; publicExposure: boolean; confidentiality: boolean; migration: string; protects: string };
type RelationshipDraft = { source: string; target: string; type: string };

const slug = (value: string) => value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const splitList = (value: string) => value.split(",").map((item) => item.trim()).filter(Boolean);

export function ContextGuideClient() {
  const [scan, setScan] = useState<ScanSummary | null>(null);
  const [dataClasses, setDataClasses] = useState<DataClassDraft[]>([]);
  const [services, setServices] = useState<ServiceDraft[]>([]);
  const [relationships, setRelationships] = useState<RelationshipDraft[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => { fetchLatestScan().then(setScan).catch(() => undefined); }, []);

  const manifest = useMemo(() => ({
    schema: "ecdat.context.v1",
    data_classes: dataClasses.filter((item) => item.id.trim() && item.name.trim()).map((item) => ({
      id: item.id.trim(), name: item.name.trim(), sensitivity: item.sensitivity, lifetime_years: Math.max(0, Number(item.lifetime) || 0),
    })),
    services: services.filter((item) => item.id.trim() && item.name.trim()).map((item) => ({
      id: item.id.trim(), name: item.name.trim(), path_prefixes: splitList(item.prefixes), business_criticality: item.criticality,
      public_exposure: item.publicExposure, confidentiality_required: item.confidentiality, migration_time_years: Math.max(0, Number(item.migration) || 0), protects: splitList(item.protects),
    })),
    relationships: relationships.filter((item) => item.source && item.target && item.source !== item.target).map((item) => ({ source: item.source, target: item.target, type: item.type })),
  }), [dataClasses, services, relationships]);

  const json = useMemo(() => JSON.stringify(manifest, null, 2), [manifest]);

  function addDataClass() {
    const index = dataClasses.length + 1;
    setDataClasses((items) => [...items, { id: `data-class-${index}`, name: "", sensitivity: "high", lifetime: "10" }]);
  }

  function addService() {
    const index = services.length + 1;
    setServices((items) => [...items, { id: `service-${index}`, name: "", prefixes: "", criticality: "high", publicExposure: false, confidentiality: true, migration: "2", protects: "" }]);
  }

  function addRelationship() {
    setRelationships((items) => [...items, { source: services[0]?.id ?? "", target: services[1]?.id ?? services[0]?.id ?? "", type: "depends_on" }]);
  }

  function seedFromAssessment() {
    if (!scan) return;
    const sourceNodes = scan.graph_nodes.filter((node) => node.properties?.provenance === "supplied_source");
    if (!sourceNodes.length) {
      setMessage("The latest assessment has no supplied-source graph contexts to seed. Add services manually instead.");
      return;
    }
    const used = new Set<string>();
    const seeded: ServiceDraft[] = sourceNodes.map((node, index) => {
      const base = slug(node.label) || `service-${index + 1}`;
      let id = base;
      let suffix = 2;
      while (used.has(id)) id = `${base}-${suffix++}`;
      used.add(id);
      return {
        id,
        name: node.label,
        prefixes: String(node.properties?.path_prefix ?? ""),
        criticality: "medium",
        publicExposure: false,
        confidentiality: true,
        migration: "2",
        protects: "",
      };
    });
    setServices(seeded);
    setRelationships([]);
    setMessage(`Seeded ${seeded.length} source context${seeded.length === 1 ? "" : "s"}. Review every business field before using the file; ECDAT has not inferred criticality, exposure or dependencies.`);
  }

  function download() {
    const blob = new Blob([json + "\n"], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "ecdat.context.json";
    anchor.click();
    URL.revokeObjectURL(url);
    setMessage("Context file generated. In New Assessment, add it as “ECDAT enterprise context” alongside your evidence sources, or place it at the root of a mounted/single-repository workspace before scanning.");
  }

  return <AppShell><div className="page-wrap context-guide-page">
    <PageHeader eyebrow="ASSESSMENT / ENTERPRISE CONTEXT" title="Enterprise Context Guide" subtitle="ECDAT can discover cryptography without this file. Enterprise context makes the next layer stronger: business-sensitive priority, long-term confidentiality analysis, service impact, readiness and dependency-safe migration sequencing." />

    <section className="context-guide-hero panel-v2">
      <div className="context-guide-hero-copy"><span className="kicker">WHY PROVIDE CONTEXT?</span><h2>Discovery tells ECDAT what exists. Context tells it what that cryptography means to your organization.</h2><p>The file does not declare cryptographic findings and it does not replace scanning. It supplies business/system facts that source code usually cannot prove: service ownership, protected data lifetime, criticality, exposure and explicit service relationships.</p><div className="context-guide-trust"><ShieldCheck size={17}/><span>Keep unknown fields unknown. Do not invent topology just to obtain a richer roadmap.</span></div></div>
      <ContextFlowGraphic />
    </section>

    <section className="context-guide-comparison">
      <article className="panel-v2"><ScanSearch size={21}/><span className="kicker">WITHOUT CONTEXT</span><h3>Strong technical evidence</h3><ul><li>Algorithms, certificates, binaries, BOMs and connector evidence</li><li>Source/repository ownership and exact evidence locations</li><li>Quantum posture and evidence-prioritized migration stages</li><li>Technical-evidence readiness estimates</li></ul></article>
      <article className="panel-v2 context-guide-plus"><Sparkles size={21}/><span className="kicker">WITH ENTERPRISE CONTEXT</span><h3>Business-aware planning</h3><ul><li>Which service owns each path and cryptographic asset</li><li>Data lifetime, sensitivity and confidentiality requirements</li><li>Business criticality and public exposure</li><li>Dependency-aware migration waves, blockers and organization-specific readiness</li></ul></article>
    </section>

    <section className="context-guide-workflow panel-v2">
      <div className="panel-topline"><div><span className="kicker">RECOMMENDED REAL-WORLD WORKFLOW</span><h2>Start with evidence. Add context only after ECDAT shows you the boundaries it observed.</h2><p className="panel-description">This two-pass approach avoids asking teams to invent an ECDAT-specific model before they have seen what the platform discovered.</p></div></div>
      <div className="context-workflow-track">
        <article><b>01</b><ScanSearch size={18}/><strong>Run an evidence-only assessment</strong><span>Upload the selected repositories, images, BOMs and operational exports. No context file is required.</span></article>
        <ArrowRight className="context-workflow-arrow" size={18}/>
        <article><b>02</b><Boxes size={18}/><strong>Seed observed source boundaries</strong><span>Use “Seed from latest assessment” so repository/container paths come from ECDAT rather than manual transcription.</span></article>
        <ArrowRight className="context-workflow-arrow" size={18}/>
        <article><b>03</b><Building2 size={18}/><strong>Confirm business facts</strong><span>Service owners, data governance and architecture teams add only criticality, data lifetime, exposure and relationships they can defend.</span></article>
        <ArrowRight className="context-workflow-arrow" size={18}/>
        <article><b>04</b><GitBranch size={18}/><strong>Re-run with enterprise context</strong><span>Add the generated context file alongside the same evidence sources to unlock business-aware readiness and dependency-safe waves.</span></article>
      </div>
    </section>

    <section className="context-guide-steps panel-v2">
      <div className="panel-topline"><div><span className="kicker">WHO KNOWS THESE FACTS?</span><h2>Build it from existing enterprise knowledge</h2><p className="panel-description">No single team needs to know everything. The context file can be assembled from information the organization already maintains.</p></div></div>
      <div className="context-source-grid">
        <article><Building2 size={18}/><strong>Service owners</strong><span>Service names, source-path ownership and rough migration lead time.</span></article>
        <article><Database size={18}/><strong>Data governance</strong><span>Data classes, sensitivity and required confidentiality lifetime.</span></article>
        <article><Network size={18}/><strong>Architecture / platform</strong><span>Explicit service dependencies and externally exposed systems.</span></article>
        <article><ShieldCheck size={18}/><strong>Security leadership</strong><span>Business criticality and which facts are approved enough to use for planning.</span></article>
      </div>
    </section>

    <section className="context-builder-grid">
      <article className="panel-v2 context-builder">
        <div className="panel-topline"><div><span className="kicker">GUIDED CONTEXT BUILDER</span><h2>Create ecdat.context.json</h2><p className="panel-description">Use only facts your organization can defend. You can start from the latest assessment's supplied source boundaries, then enrich them with business context.</p></div><FileJson2 size={21}/></div>
        <div className="context-builder-actions"><button className="ghost-action" type="button" onClick={seedFromAssessment} disabled={!scan}><Boxes size={15}/>Seed from latest assessment</button><button className="primary-action" type="button" onClick={download} disabled={!manifest.services.length}><Download size={15}/>Download context file</button></div>
        {message && <div className="context-builder-message"><Info size={16}/><span>{message}</span></div>}

        <BuilderSection number="01" title="Data classes" note="Describe information whose confidentiality matters over time. These IDs are referenced by services through protects[]." action="Add data class" onAdd={addDataClass}>
          {dataClasses.map((item, index) => <div className="context-form-row data" key={`${item.id}-${index}`}>
            <label><span>ID</span><input value={item.id} onChange={(event) => setDataClasses((rows) => rows.map((row, i) => i === index ? {...row, id:event.target.value} : row))}/></label>
            <label><span>Name</span><input value={item.name} placeholder="Customer messages" onChange={(event) => setDataClasses((rows) => rows.map((row, i) => i === index ? {...row, name:event.target.value} : row))}/></label>
            <label><span>Sensitivity</span><select value={item.sensitivity} onChange={(event) => setDataClasses((rows) => rows.map((row, i) => i === index ? {...row, sensitivity:event.target.value} : row))}><option>low</option><option>medium</option><option>high</option><option>restricted</option></select></label>
            <label><span>Lifetime (years)</span><input type="number" min="0" value={item.lifetime} onChange={(event) => setDataClasses((rows) => rows.map((row, i) => i === index ? {...row, lifetime:event.target.value} : row))}/></label>
            <button className="context-remove" type="button" onClick={() => setDataClasses((rows) => rows.filter((_, i) => i !== index))} aria-label="Remove data class"><Trash2 size={15}/></button>
          </div>)}
        </BuilderSection>

        <BuilderSection number="02" title="Services and path ownership" note="Path prefixes link discovered evidence to real services. Criticality, exposure and migration time should come from owners or approved architecture records." action="Add service" onAdd={addService}>
          {services.map((item, index) => <div className="context-service-card" key={`${item.id}-${index}`}>
            <div className="context-service-head"><strong>{item.name || `Service ${index + 1}`}</strong><button className="context-remove" type="button" onClick={() => setServices((rows) => rows.filter((_, i) => i !== index))}><Trash2 size={15}/></button></div>
            <div className="context-service-fields">
              <label><span>ID</span><input value={item.id} onChange={(event) => setServices((rows) => rows.map((row, i) => i === index ? {...row, id:event.target.value} : row))}/></label>
              <label><span>Service name</span><input value={item.name} placeholder="Messaging Gateway" onChange={(event) => setServices((rows) => rows.map((row, i) => i === index ? {...row, name:event.target.value} : row))}/></label>
              <label className="wide"><span>Owned path prefixes · comma separated</span><input value={item.prefixes} placeholder="services/gateway/, integrations/tls-endpoints.json" onChange={(event) => setServices((rows) => rows.map((row, i) => i === index ? {...row, prefixes:event.target.value} : row))}/></label>
              <label><span>Business criticality</span><select value={item.criticality} onChange={(event) => setServices((rows) => rows.map((row, i) => i === index ? {...row, criticality:event.target.value} : row))}><option>low</option><option>medium</option><option>high</option><option>critical</option></select></label>
              <label><span>Migration estimate (years)</span><input type="number" min="0" step="0.5" value={item.migration} onChange={(event) => setServices((rows) => rows.map((row, i) => i === index ? {...row, migration:event.target.value} : row))}/></label>
              <label className="wide"><span>Protected data class IDs · comma separated</span><input value={item.protects} placeholder="customer-messages, identity-claims" onChange={(event) => setServices((rows) => rows.map((row, i) => i === index ? {...row, protects:event.target.value} : row))}/></label>
              <label className="context-check"><input type="checkbox" checked={item.publicExposure} onChange={(event) => setServices((rows) => rows.map((row, i) => i === index ? {...row, publicExposure:event.target.checked} : row))}/><span>Publicly exposed</span></label>
              <label className="context-check"><input type="checkbox" checked={item.confidentiality} onChange={(event) => setServices((rows) => rows.map((row, i) => i === index ? {...row, confidentiality:event.target.checked} : row))}/><span>Confidentiality required</span></label>
            </div>
          </div>)}
        </BuilderSection>

        <BuilderSection number="03" title="Explicit service relationships" note="Only add relationships the organization can defend. depends_on is useful for migration sequencing; connects_to records known communication without automatically claiming a migration prerequisite." action="Add relationship" onAdd={addRelationship} disabled={services.length < 2}>
          {relationships.map((item, index) => <div className="context-form-row relationship" key={index}>
            <label><span>Source</span><select value={item.source} onChange={(event) => setRelationships((rows) => rows.map((row, i) => i === index ? {...row, source:event.target.value} : row))}>{services.map((service) => <option key={service.id} value={service.id}>{service.name || service.id}</option>)}</select></label>
            <label><span>Relationship</span><select value={item.type} onChange={(event) => setRelationships((rows) => rows.map((row, i) => i === index ? {...row, type:event.target.value} : row))}><option value="depends_on">depends on</option><option value="connects_to">connects to</option></select></label>
            <label><span>Target</span><select value={item.target} onChange={(event) => setRelationships((rows) => rows.map((row, i) => i === index ? {...row, target:event.target.value} : row))}>{services.map((service) => <option key={service.id} value={service.id}>{service.name || service.id}</option>)}</select></label>
            <button className="context-remove" type="button" onClick={() => setRelationships((rows) => rows.filter((_, i) => i !== index))}><Trash2 size={15}/></button>
          </div>)}
        </BuilderSection>
      </article>

      <aside className="panel-v2 context-preview">
        <div className="panel-topline"><div><span className="kicker">LIVE MANIFEST</span><h2>What ECDAT will receive</h2></div><BookOpenCheck size={20}/></div>
        <div className="context-preview-status"><CheckCircle2 size={16}/><span><strong>{manifest.services.length}</strong> services · <strong>{manifest.data_classes.length}</strong> data classes · <strong>{manifest.relationships.length}</strong> relationships</span></div>
        <pre>{json}</pre>
        <div className="context-preview-note"><Info size={15}/><p>In <strong>New Assessment</strong>, add this file as “ECDAT enterprise context” alongside your supplied evidence sources. Mounted/single-repository workspaces may instead place it at the workspace root as <strong>ecdat.context.json</strong>. ECDAT still derives cryptographic findings from scanners; the manifest enriches ownership and planning context only.</p></div>
      </aside>
    </section>

    <section className="context-guide-finish panel-v2"><GitBranch size={24}/><div><span className="kicker">WHAT CHANGES AFTER YOU ADD IT?</span><h2>Same evidence. Better organizational interpretation.</h2><p>Re-run the assessment with the manifest present. ECDAT can then map cryptographic evidence to service ownership, use declared data lifetime and business context in risk, calculate readiness with enterprise factors, and produce dependency-aware migration waves where explicit dependencies exist.</p></div><ArrowRight size={22}/></section>
  </div></AppShell>;
}

function BuilderSection({number,title,note,action,onAdd,disabled,children}:{number:string;title:string;note:string;action:string;onAdd:()=>void;disabled?:boolean;children:ReactNode}) {
  return <section className="context-builder-section"><div className="context-builder-section-head"><b>{number}</b><div><strong>{title}</strong><span>{note}</span></div><button type="button" onClick={onAdd} disabled={disabled}><Plus size={14}/>{action}</button></div><div className="context-builder-rows">{children}</div></section>;
}

function ContextFlowGraphic() {
  return <div className="context-flow-graphic" aria-label="Evidence plus enterprise context improves planning">
    <div className="context-flow-node evidence"><ScanSearch size={22}/><strong>Verified evidence</strong><span>source · binaries · BOMs · TLS/KMS/PKI</span></div>
    
    <svg viewBox="0 0 180 60" aria-hidden="true">
      <path d="M4 30 C54 30 56 12 90 12 C124 12 126 30 176 30"/>
      <path d="M4 30 C54 30 56 48 90 48 C124 48 126 30 176 30"/>
    </svg>
    
    <div className="context-flow-node context"><Building2 size={22}/><strong>Enterprise context</strong><span>ownership · data · criticality · dependencies</span></div>
    
    {/* Replaces the glitchy <ArrowRight /> */}
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="context-flow-arrow">
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" style={{ strokeDasharray: "none" }} />
    </svg>
    
    <div className="context-flow-node outcome"><Sparkles size={22}/><strong>Decision-grade planning</strong><span>risk · readiness · blockers · migration waves</span></div>
  </div>;
}
