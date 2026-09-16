"use client";

import {
  Building2,
  BookOpenCheck,
  FileText,
  Gauge,
  GitBranch,
  Hexagon,
  History,
  Import,
  LayoutDashboard,
  LogOut,
  Menu,
  Pin,
  Route,
  ScanSearch,
  ShieldAlert,
  Sparkles,
  UsersRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, fetchAuthState, fetchLatestScan, logout, switchOrganization } from "@/lib/api";
import type { AuthState, ScanSummary } from "@/lib/types";

type NavItem = { href: string; label: string; description: string; icon: typeof LayoutDashboard; write?: boolean };
type NavSection = { label: string; items: NavItem[] };

const sections: NavSection[] = [
  {
    label: "Overview",
    items: [
      { href: "/dashboard", label: "Executive Overview", description: "Enterprise posture and priority actions", icon: LayoutDashboard },
      { href: "/context-guide", label: "Enterprise Context Guide", description: "Build richer planning context", icon: BookOpenCheck },
    ],
  },
  {
    label: "Assessment",
    items: [
      { href: "/intake", label: "New Assessment", description: "Analyze enterprise artifacts", icon: Import, write: true },
      { href: "/graph", label: "Cryptographic Inventory", description: "Dependency and impact map", icon: GitBranch },
      { href: "/investigate", label: "Asset Investigation", description: "Evidence-to-action trace", icon: ScanSearch },
    ],
  },
  {
    label: "Risk & Planning",
    items: [
      { href: "/risk", label: "Quantum Risk", description: "Scenario and timing analysis", icon: ShieldAlert },
      { href: "/migration", label: "Migration Roadmap", description: "Dependency-aware execution plan", icon: Route },
      { href: "/agility", label: "Migration Readiness", description: "Transition preparedness", icon: Sparkles },
    ],
  },
  {
    label: "Governance",
    items: [
      { href: "/history", label: "Assessment History", description: "Organization-scoped posture snapshots", icon: History },
      { href: "/reports", label: "Reports & Exports", description: "Decision and engineering outputs", icon: FileText },
      { href: "/access", label: "Access & Organization", description: "Members, roles and workspace access", icon: UsersRound },
    ],
  },
];

const allItems = sections.flatMap((section) => section.items);
const PIN_STORAGE_KEY = "ecdat.navigation.pinned";

function assessmentName(summary: ScanSummary | null) {
  if (!summary) return "No assessment loaded";
  if (summary.target.display_name?.trim()) return summary.target.display_name;
  const parts = summary.target.locator.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] || summary.target.kind.replaceAll("_", " ");
}

function statusLabel(status: ScanSummary["status"] | undefined) {
  if (!status) return "Ready";
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "U";
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [logoError, setLogoError] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [railExpanded, setRailExpanded] = useState(false);
  const railCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [pinned, setPinned] = useState(false);
  const [summary, setSummary] = useState<ScanSummary | null>(null);
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [authChecking, setAuthChecking] = useState(true);

  const current = allItems.find((item) => item.href === pathname) ?? allItems[0];
  const currentSection = sections.find((section) => section.items.some((item) => item.href === current.href))?.label ?? "Platform";
  const canWrite = auth?.active_organization.role !== "viewer";
  const sidebarExpanded = pinned || railExpanded || navOpen;

  useEffect(() => {
    try { setPinned(window.localStorage.getItem(PIN_STORAGE_KEY) === "true"); } catch { setPinned(false); }
  }, []);

  useEffect(() => {
    let cancelled = false;
    setAuthChecking(true);
    fetchAuthState()
      .then(async (state) => {
        if (cancelled) return;
        setAuth(state);
        try { setSummary(await fetchLatestScan()); } catch { setSummary(null); }
      })
      .catch((cause) => {
        if (cancelled) return;
        if (cause instanceof ApiError && cause.status === 401) {
          const next = encodeURIComponent(pathname || "/dashboard");
          router.replace(`/auth?next=${next}`);
          return;
        }
        router.replace("/auth");
      })
      .finally(() => { if (!cancelled) setAuthChecking(false); });
    return () => { cancelled = true; };
  }, [pathname, router]);

  useEffect(() => {
    setNavOpen(false);
    if (!pinned) {
      setRailExpanded(false);
    }
  }, [pathname, pinned]);

  useEffect(() => () => {
    if (railCloseTimer.current) clearTimeout(railCloseTimer.current);
  }, []);

  function openRail() {
    if (pinned) return;

    if (railCloseTimer.current) {
      clearTimeout(railCloseTimer.current);
      railCloseTimer.current = null;
    }

    setRailExpanded(true);
  }

  function closeRail() {
    if (pinned) return;

    if (railCloseTimer.current) clearTimeout(railCloseTimer.current);

    railCloseTimer.current = setTimeout(() => {
      setRailExpanded(false);
      railCloseTimer.current = null;
    }, 90);
  }

  function handleBlur(event: React.FocusEvent) {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      closeRail();
    }
  }

  useEffect(() => {
    const clearAssessment = () => setSummary(null);
    window.addEventListener("ecdat:assessment-reset", clearAssessment);
    return () => window.removeEventListener("ecdat:assessment-reset", clearAssessment);
  }, []);

  const coverageText = useMemo(() => {
    if (!summary?.coverage) return summary ? `${summary.findings.length} findings` : "Awaiting assessment";
    return `${summary.coverage.files_observed} files · ${summary.coverage.scanners_completed} scanners`;
  }, [summary]);

  const togglePinned = () => {
    setPinned((prev) => {
      const next = !prev;

      try {
        window.localStorage.setItem(PIN_STORAGE_KEY, String(next));
      } catch {
        /* local persistence is optional */
      }

      // Remove any hover state that existed before pinning/unpinning.
      if (railCloseTimer.current) {
        clearTimeout(railCloseTimer.current);
        railCloseTimer.current = null;
      }

      setRailExpanded(false);

      return next;
    });
  };

  async function changeOrganization(organizationId: string) {
    if (!auth || organizationId === auth.active_organization.id) return;
    const state = await switchOrganization(organizationId);
    setAuth(state);
    setSummary(await fetchLatestScan().catch(() => null));
    window.location.reload();
  }

  async function signOut() {
    await logout().catch(() => undefined);
    router.replace("/auth");
  }

  if (authChecking || !auth) {
    return <main className="secure-gate"><div className="secure-gate-mark"><Hexagon size={28} /><span>QDeX</span></div><p>Verifying secure workspace access…</p></main>;
  }

  return (
    <main className={pinned ? "app-shell sidebar-pinned" : "app-shell"}>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <button className={navOpen ? "nav-backdrop visible" : "nav-backdrop"} aria-label="Close navigation" onClick={() => setNavOpen(false)} />
      
      {/* 
        The pinned ? undefined trick completely detaches the listeners from the DOM, 
        shielding the component from stale mouse events while locked down. 
      */}
      <aside
        className={`side-rail${sidebarExpanded ? " is-expanded" : ""}${navOpen ? " mobile-open" : ""}`}
        onMouseEnter={pinned ? undefined : openRail}
        onMouseLeave={pinned ? undefined : closeRail}
        onFocusCapture={pinned ? undefined : openRail}
        onBlurCapture={pinned ? undefined : handleBlur}
      >
        <div className="rail-brand-row">
          <Link href="/" className="brand-mark" aria-label="ECDAT home" onClick={() => setNavOpen(false)}>
            <div className="brand-badge">
              {logoError ? <><Hexagon size={25} strokeWidth={1.4} /><span>E</span></> : <img src="/icons/icon.png" alt="" onError={() => setLogoError(true)} />}
            </div>
            <div className="brand-copy"><b>QDeX</b><small>Cryptographic Intelligence</small></div>
          </Link>
          <button className={pinned ? "sidebar-pin active" : "sidebar-pin"} type="button" aria-pressed={pinned} aria-label={pinned ? "Unpin navigation" : "Pin navigation"} title={pinned ? "Unpin navigation" : "Pin navigation"} onClick={togglePinned}>
            <Pin size={15} fill={pinned ? "currentColor" : "none"} />
          </button>
          <button className="nav-close" aria-label="Close navigation" onClick={() => setNavOpen(false)}><X size={20} /></button>
        </div>

        <nav className="rail-nav" aria-label="Primary navigation">
          {sections.map((section) => (
            <div className="rail-section" key={section.label}>
              <span className="rail-section-label">{section.label}</span>
              {section.items.filter((item) => !item.write || canWrite).map(({ href, label, description, icon: Icon }) => {
                const active = pathname === href;
                return <Link key={href} href={href} className={active ? "rail-link active" : "rail-link"} aria-current={active ? "page" : undefined} title={label} onClick={() => setNavOpen(false)}>
                  <span className="rail-item-icon" aria-hidden="true"><Icon size={18} strokeWidth={1.65} /></span>
                  <span className="rail-item-copy"><strong>{label}</strong><small>{description}</small></span>
                </Link>;
              })}
            </div>
          ))}
        </nav>

        <div className="rail-account">
          <Link href="/access" className="rail-account-main" title={`${auth.user.display_name} · ${auth.active_organization.name}`}>
            <b>{initials(auth.user.display_name)}</b>
            <span><strong>{auth.user.display_name}</strong><small>{auth.active_organization.role_label}</small></span>
          </Link>
          <button type="button" className="rail-logout" title="Sign out" aria-label="Sign out" onClick={signOut}><LogOut size={16} /></button>
        </div>
      </aside>

      <section className="app-stage">
        <header className="app-topbar">
          <div className="topbar-left">
            <button className="nav-open" aria-label="Open navigation" onClick={() => setNavOpen(true)}><Menu size={20} /></button>
            <div className="topbar-context" aria-label="Current platform location"><span>{currentSection}</span><i aria-hidden="true">/</i><strong>{current.label}</strong></div>
          </div>

          <div className="topbar-assessment" aria-label="Current assessment and workspace status">
            <div className="workspace-context" title={auth.organizations.length > 1 ? "Switch authorized organization workspace" : "Active organization workspace"}>
              <Building2 size={15} />
              <div>
                <span>{auth.organizations.length > 1 ? "Organization workspace" : "Organization"}</span>
                {auth.organizations.length > 1 ? <select value={auth.active_organization.id} onChange={(event) => changeOrganization(event.target.value)} aria-label="Active organization">
                  {auth.organizations.map((organization) => <option key={organization.id} value={organization.id}>{organization.name}</option>)}
                </select> : <strong>{auth.active_organization.name}</strong>}
              </div>
              <small>{auth.active_organization.role_label}</small>
            </div>
            <div className="topbar-assessment-copy"><span>Active assessment</span><strong>{assessmentName(summary)}</strong></div>
            <span className={`topbar-status status-${summary?.status ?? "idle"}`}><i />{statusLabel(summary?.status)}</span>
            <span className="topbar-coverage">{coverageText}</span>
            <Link href="/access" className="topbar-account" title="Account security and organization access" aria-label="Open account and access settings">
              <b>{initials(auth.user.display_name)}</b><span>Account</span>
            </Link>
          </div>
        </header>
        <div id="main-content">{children}</div>
      </section>
    </main>
  );
}

export function PageHeader({ eyebrow, title, subtitle, actions }: { eyebrow: string; title: string; subtitle?: string; actions?: ReactNode }) {
  return <header className="page-header"><div className="page-header-copy"><div className="eyebrow"><Gauge size={13} />{eyebrow}</div><h1>{title}</h1><p>{subtitle}</p></div>{actions && <div className="page-actions">{actions}</div>}</header>;
}