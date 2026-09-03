import Link from "next/link";
import { ArrowRight, FileSearch, GitBranch, ShieldAlert } from "lucide-react";
import { FoundationMesh } from "../components/foundation/FoundationMesh";

const pillars = [
  {
    icon: FileSearch,
    title: "Discover cryptography",
    text: "Scan repositories, configurations, certificates, BOMs, and image archives to build an evidence-backed inventory.",
  },
  {
    icon: ShieldAlert,
    title: "Assess quantum exposure",
    text: "Apply explainable Mosca-style planning assumptions, highlight HNDL exposure, and surface the most urgent risks first.",
  },
  {
    icon: GitBranch,
    title: "Plan migration",
    text: "Trace affected services, identify blockers, and generate a dependency-aware roadmap teams can actually execute.",
  },
];

export default function Home() {
  return (
    <main className="landing-shell">
      <FoundationMesh />
      <div className="landing-noise" aria-hidden="true" />
      <section className="landing-topbar">
        <div className="landing-brand">
          <div className="landing-brand-icon">
            <img src="/icons/icon.png" alt="ECDAT" />
          </div>
          <div>
            <strong>ECDAT</strong>
            <span>Enterprise Cryptographic Discovery & Analysis Tool</span>
          </div>
        </div>
        <div className="landing-topbar-actions">
          <Link href="/dashboard" className="text-link">Open dashboard</Link>
          <Link href="/intake" className="primary-action landing-cta-sm">New assessment</Link>
        </div>
      </section>

      <section className="landing-hero">
        <div className="landing-copy">
          <div className="eyebrow landing-eyebrow">Enterprise </div>
          <h1>One-Stop Solution For Post-Quantum Readiness</h1>
          <p>
            ECDAT turns evidence-backed discovery into a living cryptographic estate, quantum-risk analysis,
            and an actionable migration program for enterprise teams.
          </p>
          <div className="landing-actions">
            <Link href="/dashboard" className="primary-action">
              Open Dashboard <ArrowRight size={15} />
            </Link>
            <Link href="/intake" className="landing-secondary-action">
              Start New Assessment
            </Link>
          </div>
          <div className="landing-signal-row">
            <div className="landing-signal-card">
              <span>What it does</span>
              <strong>Discovery → Risk → Migration</strong>
              <p>One continuous investigation path from evidence to action.</p>
            </div>
            <div className="landing-signal-card">
              <span>Built for</span>
              <strong>Architecture, security, modernization teams</strong>
              <p>Show affected systems, planning assumptions, and the next migration move.</p>
            </div>
          </div>
        </div>

        <div className="landing-choice-grid">
          <Link href="/dashboard" className="landing-choice-card">
            <div className="landing-choice-top">
              <span className="kicker">Command center</span>
              <ArrowRight size={18} />
            </div>
            <h2>Open Dashboard</h2>
            <p>Review portfolio exposure, investigate cryptographic assets, and evaluate current migration priorities.</p>
            <ul>
              <li>Executive posture</li>
              <li>Risk and HNDL scenarios</li>
              <li>Migration readiness</li>
            </ul>
          </Link>

          <Link href="/intake" className="landing-choice-card landing-choice-card-hot">
            <div className="landing-choice-top">
              <span className="kicker">Assessment intake</span>
              <ArrowRight size={18} />
            </div>
            <h2>Start New Assessment</h2>
            <p>Import repositories, archives, BOMs, certificates, or image artifacts and build a new cryptographic assessment.</p>
            <ul>
              <li>ZIP / TAR / image archive intake</li>
              <li>CycloneDX import</li>
              <li>Reference estate for demonstration</li>
            </ul>
          </Link>
        </div>
      </section>

      <section className="landing-pillars">
        {pillars.map(({ icon: Icon, title, text }) => (
          <article key={title} className="landing-pillar-card panel-v2">
            <div className="landing-pillar-icon"><Icon size={18} /></div>
            <h3>{title}</h3>
            <p>{text}</p>
          </article>
        ))}
      </section>
    </main>
  );
}
