"use client";

import { Activity, FileText, Gauge, GitBranch, Hexagon, History, Import, LayoutDashboard, Route, ScanSearch, ShieldAlert, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

const items = [
  { href: "/dashboard", label: "Executive Overview", short: "Overview", icon: LayoutDashboard },
  { href: "/intake", label: "New Assessment", short: "Assess", icon: Import },
  { href: "/graph", label: "Cryptographic Estate", short: "Estate", icon: GitBranch },
  { href: "/investigate", label: "Asset Investigation", short: "Investigate", icon: ScanSearch },
  { href: "/risk", label: "Quantum Exposure", short: "Exposure", icon: ShieldAlert },
  { href: "/migration", label: "Migration Roadmap", short: "Roadmap", icon: Route },
  { href: "/agility", label: "Migration Readiness", short: "Readiness", icon: Sparkles },
  { href: "/history", label: "Assessment History", short: "Assessments", icon: History },
  { href: "/reports", label: "Decision Reports", short: "Reports", icon: FileText },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [logoError, setLogoError] = useState(false);

  return (
    <main className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className="side-rail">
        <Link href="/" className="brand-mark" aria-label="ECDAT home">
          <div className="brand-badge">
            {logoError ? (
              <>
                <Hexagon size={26} strokeWidth={1.4} />
                <span>E</span>
              </>
            ) : (
              <img src="/icons/icon.png" alt="ECDAT" onError={() => setLogoError(true)} />
            )}
          </div>
          <div className="brand-copy">
            <b>ECDAT</b>
            <small>Cryptographic Intelligence</small>
          </div>
        </Link>
        <nav className="rail-nav" aria-label="Primary navigation">
          {items.map(({ href, label, short, icon: Icon }) => {
            const active = pathname === href;
            return <Link key={href} href={href} className={active ? "rail-link active" : "rail-link"} aria-current={active ? "page" : undefined}>
              <Icon size={18} strokeWidth={1.55} /><span><strong>{short}</strong><small>{label}</small></span>
            </Link>;
          })}
        </nav>
        <div className="rail-status"><Activity size={14} /><span>ANALYSIS ONLINE</span></div>
      </aside>
      <section className="app-stage" id="main-content">{children}</section>
    </main>
  );
}

export function PageHeader({ eyebrow, title, subtitle, actions }: { eyebrow: string; title: string; subtitle: string; actions?: ReactNode }) {
  return <header className="page-header"><div><div className="eyebrow"><Gauge size={12} />{eyebrow}</div><h1>{title}</h1><p>{subtitle}</p></div>{actions && <div className="page-actions">{actions}</div>}</header>;
}
