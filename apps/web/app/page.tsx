import Link from "next/link";
import {
  ArrowRight,
  Boxes,
  FileSearch,
  GitBranch,
  Landmark,
  Route,
  ShieldCheck,
  ShieldAlert,
} from "lucide-react";
import { FoundationMesh } from "../components/foundation/FoundationMesh";

const journey = [
  {
    no: "01",
    icon: FileSearch,
    title: "Discover",
    heading: "Find cryptography across enterprise systems",
    text: "Analyze repositories, configurations, certificates, dependencies, container images and CycloneDX BOMs while retaining exact evidence locations.",
  },
  {
    no: "02",
    icon: Boxes,
    title: "Inventory",
    heading: "Build a traceable cryptographic inventory",
    text: "Normalize related findings into canonical assets without losing the provenance that explains where each cryptographic signal came from.",
  },
  {
    no: "03",
    icon: ShieldAlert,
    title: "Assess",
    heading: "Understand quantum and long-term exposure",
    text: "Apply explicit planning assumptions and explainable risk factors instead of hiding decisions behind a black-box score.",
  },
  {
    no: "04",
    icon: GitBranch,
    title: "Understand impact",
    heading: "See dependencies before changing production",
    text: "Map affected services, shared cryptography, blockers and potentially affected systems before migration work is sequenced.",
  },
  {
    no: "05",
    icon: Route,
    title: "Plan & report",
    heading: "Turn findings into an executable transition plan",
    text: "Generate standards-based recommendations, readiness analysis, migration waves and decision-ready outputs for engineering and management.",
  },
];

export default function Home() {
  return (
    <main className="landing-shell phase7-landing">
      <FoundationMesh />
      <div className="landing-noise" aria-hidden="true" />

      <header className="landing-topbar">
        <Link href="/" className="landing-brand" aria-label="ECDAT home">
          <div className="landing-brand-icon"><img src="/icons/icon.png" alt="" /></div>
          <div><strong>QDeX</strong><span>Enterprise Cryptographic Discovery & Analysis Tool</span></div>
        </Link>
        <nav className="landing-topbar-actions" aria-label="Landing navigation">
          <Link href="/dashboard" className="text-link">VIEW PLATFORM</Link>
          <Link href="/intake" className="primary-action landing-cta-sm">START AN ASSESSMENT</Link>
        </nav>
      </header>

      <section className="landing-hero phase7-hero">
        <div className="landing-copy">
          <h1>PREPARE ENTERPRISES FOR THE POST-QUANTUM SHIFT</h1>
          <p>
            QDeX discovers where cryptography is used, explains which systems need attention, traces enterprise dependencies,
            and builds an evidence-backed migration roadmap from the same verified assessment data.
          </p>
          <div className="landing-actions">
            <Link href="/intake" className="primary-action">Start an Assessment <ArrowRight size={16} /></Link>
            <Link href="/dashboard" className="landing-secondary-action">View Platform Overview</Link>
          </div>
          <div className="landing-assurance-row" aria-label="Platform principles">
            <span><ShieldCheck size={15} /> Evidence-backed discovery</span>
            <span><ShieldCheck size={15} /> Explainable risk</span>
            <span><ShieldCheck size={15} /> Dependency-aware migration</span>
          </div>
        </div>

        <aside className="landing-brief panel-v2" aria-label="Platform overview">
          <span className="kicker">From evidence to action</span>
          <h2>A single decision path for cryptographic modernization</h2>
          <p>Technical findings stay connected to business context, system impact, planning assumptions and migration decisions.</p>
          <div className="landing-brief-flow">
            <div><b>01</b><span>Enterprise inputs</span></div>
            <i />
            <div><b>02</b><span>Verified findings</span></div>
            <i />
            <div><b>03</b><span>Risk & impact</span></div>
            <i />
            <div><b>04</b><span>Migration plan</span></div>
          </div>
          <div className="landing-brief-note"><ShieldCheck size={17} /><p>Uncertainty and incomplete coverage are shown explicitly rather than converted into false certainty.</p></div>
        </aside>
      </section>

      <section className="landing-section-intro">
        <span className="kicker">How QDeX works</span>
        <h2>Clear enough for decision-makers. Detailed enough for security engineers.</h2>
        <p>The platform keeps technical depth available while presenting each stage in plain language and preserving a traceable evidence chain.</p>
      </section>

      <section className="landing-journey">
        {journey.map(({ no, icon: Icon, title, heading, text }) => (
          <article key={no} className="landing-journey-card panel-v2">
            <div className="landing-journey-top"><span>{no}</span><Icon size={20} /></div>
            <small>{title}</small>
            <h3>{heading}</h3>
            <p>{text}</p>
          </article>
        ))}
      </section>

      <section className="landing-audience panel-v2">
        <div>
          <span className="kicker">Designed for enterprise decisions</span>
          <h2>One platform, different levels of detail.</h2>
        </div>
        <div className="landing-audience-grid">
          <article><strong>Security & cryptography teams</strong><p>Exact evidence, algorithms, dependencies, confidence, risk factors and migration targets.</p></article>
          <article><strong>Platform & application teams</strong><p>Affected services, prerequisites, blockers, sequencing and operational constraints.</p></article>
          <article><strong>Leadership & evaluators</strong><p>Clear posture, priority actions, assumptions, limitations, programme scope and decision-ready reports.</p></article>
        </div>
      </section>

      <section className="landing-final-cta">
        <div><span className="kicker">Begin with evidence</span><h2>Assess the cryptography already present in your environment.</h2></div>
        <Link href="/intake" className="primary-action">Start New Assessment <ArrowRight size={16} /></Link>
      </section>
    </main>
  );
}
