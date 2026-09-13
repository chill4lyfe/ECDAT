"use client";

import { Building2, CheckCircle2, KeyRound, LockKeyhole, ShieldCheck, UserRound } from "lucide-react";
import { PasswordField } from "@/components/forms/PasswordField";
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { acceptInvitation, bootstrapPlatform, fetchAuthState, fetchBootstrapStatus, fetchLoginOrganizations, login } from "@/lib/api";
import type { AuthOrganization } from "@/lib/types";

type Mode = "checking" | "setup" | "login" | "invite";

function safeNext(value: string | null) {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/dashboard";
}

export function AuthClient() {
  const [mode, setMode] = useState<Mode>("checking");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [organizationName, setOrganizationName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [inviteToken, setInviteToken] = useState("");
  const [workspaceChoices, setWorkspaceChoices] = useState<AuthOrganization[]>([]);
  const [selectedWorkspace, setSelectedWorkspace] = useState<string>("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const invite = hash.get("invite") ?? params.get("invite") ?? "";
    if (invite) {
      setInviteToken(invite);
      setMode("invite");
      return;
    }
    fetchAuthState()
      .then(() => { window.location.replace(safeNext(params.get("next"))); })
      .catch(async () => {
        try {
          const status = await fetchBootstrapStatus();
          setMode(status.setup_required ? "setup" : "login");
        } catch (cause) {
          setError(cause instanceof Error ? cause.message : "Unable to reach the identity service.");
          setMode("login");
        }
      });
  }, []);

  function resetWorkspaceChoice() {
    if (workspaceChoices.length) {
      setWorkspaceChoices([]);
      setSelectedWorkspace("");
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "setup") {
        await bootstrapPlatform({ organization_name: organizationName, display_name: displayName, email, password });
      } else if (mode === "invite") {
        await acceptInvitation({ token: inviteToken, display_name: displayName, password });
      } else {
        if (!workspaceChoices.length) {
          // Workspace membership is disclosed only after credentials are verified. This avoids
          // turning the login screen into an organization-membership enumeration endpoint.
          const choices = await fetchLoginOrganizations({ email, password });
          if (choices.length > 1) {
            setWorkspaceChoices(choices);
            setSelectedWorkspace(choices[0]?.id ?? "");
            return;
          }
          await login({ email, password, organization_id: choices[0]?.id });
        } else {
          if (!selectedWorkspace) throw new Error("Choose an authorized workspace to continue.");
          await login({ email, password, organization_id: selectedWorkspace });
        }
      }
      const params = new URLSearchParams(window.location.search);
      window.location.replace(safeNext(params.get("next")));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Authentication failed.");
    } finally {
      setBusy(false);
    }
  }

  return <main className="auth-page">
    <div className="auth-brand"><div className="auth-brand-mark"><ShieldCheck size={28} /></div><div><b>ECDAT</b><span>Enterprise Cryptographic Intelligence</span></div></div>
    <section className="auth-shell">
      <div className="auth-context">
        <span className="kicker">LOCAL-FIRST ACCESS CONTROL</span>
        <h1>{mode === "setup" ? "Establish your organization workspace" : mode === "invite" ? "Accept organization access" : "Sign in to ECDAT"}</h1>
        <p>{mode === "setup" ? "Create the first organization administrator for this self-hosted installation. Existing local assessments are assigned to this organization during first-time setup." : mode === "invite" ? "Access is invitation-only. Your membership and role are verified by the local ECDAT server before any assessment data is returned." : "Use your individual account. If your email is authorized in more than one organization, ECDAT verifies your credentials first and then asks which isolated workspace you want to enter."}</p>
        <div className="auth-assurance">
          <div><LockKeyhole size={17} /><span><strong>Local credentials</strong><small>Passwords and sessions remain inside the company-hosted deployment.</small></span></div>
          <div><Building2 size={17} /><span><strong>Organization isolation</strong><small>Assessment history and plans are scoped to the active authorized workspace.</small></span></div>
          <div><UserRound size={17} /><span><strong>Role-based authorization</strong><small>Administrators, analysts and viewers receive different server-side permissions.</small></span></div>
        </div>
      </div>

      <form className="auth-card" onSubmit={submit}>
        <div className="auth-card-head"><KeyRound size={18} /><div><strong>{mode === "setup" ? "Initial secure setup" : mode === "invite" ? "Professional enrollment" : workspaceChoices.length ? "Choose authorized workspace" : "Organization sign in"}</strong><span>{mode === "setup" ? "One-time installation bootstrap" : mode === "invite" ? "Company-issued invitation required" : workspaceChoices.length ? "Credentials verified · workspace selection required" : "Authorized personnel only"}</span></div></div>
        {mode === "checking" ? <div className="auth-loading">Checking platform identity state…</div> : <>
          {mode === "setup" && <label><span>Organization name</span><input autoComplete="organization" value={organizationName} onChange={(e) => setOrganizationName(e.target.value)} placeholder="Example: National Payments Corporation" required /></label>}
          {(mode === "setup" || mode === "invite") && <label><span>Full name</span><input autoComplete="name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Authorized professional" required /></label>}
          {mode !== "invite" && <label><span>Work email</span><input type="email" autoComplete="email" value={email} onChange={(e) => { setEmail(e.target.value); resetWorkspaceChoice(); }} placeholder="name@company.example" required disabled={workspaceChoices.length > 0} /></label>}
          {mode === "invite" && <label><span>Invitation code</span><input value={inviteToken} onChange={(e) => setInviteToken(e.target.value)} required /></label>}
          <label><span>{mode === "invite" ? "Account password" : "Password"}</span><PasswordField ariaLabel={mode === "invite" ? "Account password" : "Password"} autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(value) => { setPassword(value); resetWorkspaceChoice(); }} minLength={mode === "login" ? 1 : 12} disabled={workspaceChoices.length > 0} /><small>{mode === "login" ? workspaceChoices.length ? "Credentials verified. Choose one of the workspaces authorized for this account." : "Workspace memberships are revealed only after your password is verified." : "Minimum 12 characters and at least three character groups."}</small></label>

          {mode === "login" && workspaceChoices.length > 1 && <div className="auth-workspace-chooser" role="radiogroup" aria-label="Authorized organization workspace">
            <div className="auth-workspace-chooser-head"><Building2 size={16}/><div><strong>Authorized workspaces</strong><span>Your role can differ between organizations.</span></div></div>
            <div className="auth-workspace-options">{workspaceChoices.map((organization) => <button type="button" key={organization.id} role="radio" aria-checked={selectedWorkspace === organization.id} className={selectedWorkspace === organization.id ? "selected" : ""} onClick={() => setSelectedWorkspace(organization.id)}>
              <span className="auth-workspace-radio"><i /></span><span><strong>{organization.name}</strong><small>{organization.role_label}</small></span><ShieldCheck size={16}/>
            </button>)}</div>
            <button type="button" className="auth-edit-credentials" onClick={() => { setWorkspaceChoices([]); setSelectedWorkspace(""); }}>Use a different account</button>
          </div>}

          {error && <div className="auth-error">{error}</div>}
          <button className="auth-submit" disabled={busy}>{busy ? "VERIFYING…" : mode === "setup" ? "CREATE ORGANIZATION & ADMIN" : mode === "invite" ? "ACCEPT INVITATION" : workspaceChoices.length ? "ENTER SELECTED WORKSPACE" : "CONTINUE SECURE SIGN IN"}</button>
          {mode === "login" && !workspaceChoices.length && <div className="auth-footnote"><CheckCircle2 size={14} />New users cannot self-register. An Organization Administrator must issue an invitation.</div>}
        </>}
      </form>
    </section>
    <footer className="auth-footer"><Link href="/">Back to platform overview</Link><span>ECDAT local-first deployment</span></footer>
  </main>;
}
