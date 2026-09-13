"use client";

import {
  AlertTriangle, BookOpenCheck, Building2, Check, Clipboard, KeyRound, Laptop2, LockKeyhole, Route,
  ScanSearch, ShieldCheck, Trash2, UserPlus, UsersRound,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  changePassword,
  createInvitation,
  createOrganization,
  fetchAuthState,
  fetchMembers,
  fetchSessions,
  resetOrganizationAssessmentData,
  revokeOtherSessions,
  updateMember,
  type AssessmentResetResult,
} from "@/lib/api";
import type { AuthSession, AuthState, InvitationResponse, MemberSummary, OrganizationRole } from "@/lib/types";
import { PasswordField } from "@/components/forms/PasswordField";
import { AppShell, PageHeader } from "@/components/shell/AppShell";

const roles: Array<{ value: OrganizationRole; label: string; note: string }> = [
  { value: "organization_admin", label: "Organization Administrator", note: "Members, workspace governance and all assessment actions" },
  { value: "security_analyst", label: "Security Architect / Analyst", note: "Create assessments, scenarios, migration plans and engineering reports" },
  { value: "viewer", label: "Viewer / Executive", note: "Read-only access to authorized assessment and reporting surfaces" },
];

const roleCapabilities: Record<OrganizationRole, string[]> = {
  organization_admin: ["Run and reset organization assessments", "Manage members, roles and invitations", "Build risk scenarios and migration plans", "Access reports, exports and organization governance"],
  security_analyst: ["Run multi-source assessments", "Investigate evidence and CryptoGraph relationships", "Build risk scenarios and migration plans", "Generate engineering and executive outputs"],
  viewer: ["Review executive posture and reports", "Inspect approved findings and evidence", "View migration roadmap and readiness", "No assessment, plan or membership mutations"],
};

function message(cause: unknown, fallback: string) {
  return cause instanceof Error ? cause.message : fallback;
}

function relativeTime(value: string) {
  const date = new Date(value);
  const minutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
  if (minutes < 2) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  return date.toLocaleDateString();
}

export function AccessClient() {
  const [auth, setAuth] = useState<AuthState | null>(null);
  const [members, setMembers] = useState<MemberSummary[]>([]);
  const [sessions, setSessions] = useState<AuthSession[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<OrganizationRole>("security_analyst");
  const [workspaceName, setWorkspaceName] = useState("");
  const [invite, setInvite] = useState<InvitationResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [memberError, setMemberError] = useState<string | null>(null);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);

  const [resetPassword, setResetPassword] = useState("");
  const [resetConfirmation, setResetConfirmation] = useState("");
  const [resetBusy, setResetBusy] = useState(false);
  const [resetResult, setResetResult] = useState<AssessmentResetResult | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);

  useEffect(() => {
    fetchAuthState().then(async (state) => {
      setAuth(state);
      setSessions(await fetchSessions().catch(() => []));
      if (state.active_organization.role === "organization_admin") setMembers(await fetchMembers());
    }).catch((cause) => setPageError(message(cause, "Unable to load access state.")));
  }, []);

  async function createWorkspace(event: FormEvent) {
    event.preventDefault(); setBusy(true); setWorkspaceError(null);
    try { await createOrganization(workspaceName); setWorkspaceName(""); window.location.reload(); }
    catch (cause) { setWorkspaceError(message(cause, "Unable to create workspace.")); }
    finally { setBusy(false); }
  }

  async function inviteMember(event: FormEvent) {
    event.preventDefault(); setBusy(true); setInviteError(null); setInvite(null);
    try { const created = await createInvitation(email, role); setInvite(created); setEmail(""); }
    catch (cause) { setInviteError(message(cause, "Unable to create invitation.")); }
    finally { setBusy(false); }
  }

  async function changeMember(member: MemberSummary, nextRole?: OrganizationRole, nextStatus?: "active" | "suspended") {
    setMemberError(null);
    try {
      const updated = await updateMember(member.membership_id, { role: nextRole, status: nextStatus });
      setMembers((current) => current.map((item) => item.membership_id === updated.membership_id ? updated : item));
    } catch (cause) { setMemberError(message(cause, "Unable to update member.")); }
  }

  async function copyInvite() {
    if (!invite) return;
    const url = `${window.location.origin}/auth#invite=${encodeURIComponent(invite.invite_token)}`;
    await navigator.clipboard.writeText(url); setCopied(true); window.setTimeout(() => setCopied(false), 1800);
  }

  async function submitPasswordChange(event: FormEvent) {
    event.preventDefault(); setPasswordBusy(true); setPasswordMessage(null); setPasswordError(null);
    try {
      await changePassword({ current_password: currentPassword, new_password: newPassword, confirm_password: confirmPassword });
      setCurrentPassword(""); setNewPassword(""); setConfirmPassword("");
      setPasswordMessage("Password updated. Other active sessions for this account were signed out.");
      setSessions(await fetchSessions().catch(() => sessions.filter((item) => item.current)));
    } catch (cause) { setPasswordError(message(cause, "Unable to change password.")); }
    finally { setPasswordBusy(false); }
  }

  async function signOutOtherSessions() {
    setSessionMessage(null);
    try {
      const result = await revokeOtherSessions();
      setSessions((current) => current.filter((item) => item.current));
      setSessionMessage(result.revoked ? `${result.revoked} other session${result.revoked === 1 ? "" : "s"} revoked.` : "No other active sessions were found.");
    } catch (cause) { setSessionMessage(message(cause, "Unable to revoke other sessions.")); }
  }

  async function submitAssessmentReset(event: FormEvent) {
    event.preventDefault(); setResetBusy(true); setResetResult(null); setResetError(null);
    try {
      const result = await resetOrganizationAssessmentData({ current_password: resetPassword, confirmation: resetConfirmation });
      setResetResult(result); setResetPassword(""); setResetConfirmation("");
      window.dispatchEvent(new Event("ecdat:assessment-reset"));
    } catch (cause) { setResetError(message(cause, "Unable to reset organization assessment data.")); }
    finally { setResetBusy(false); }
  }

  const activeRole = auth?.active_organization.role ?? "viewer";
  const isAdmin = activeRole === "organization_admin";
  const canOperate = activeRole !== "viewer";
  const capabilities = useMemo(() => roleCapabilities[activeRole], [activeRole]);

  return <AppShell><div className="page-wrap access-page phase81-access">
    <PageHeader eyebrow="GOVERNANCE / ACCESS" title="Access & Organization" subtitle="Manage account security, role-scoped platform access and organization data. ECDAT enforces permissions server-side; sensitive assessment evidence never becomes accessible merely because a browser control is visible." />

    {auth && <section className="access-summary-grid">
      <article className="panel-v2 access-summary"><Building2 size={22} /><div><span>ACTIVE ORGANIZATION</span><strong>{auth.active_organization.name}</strong><small>{auth.organizations.length > 1 ? `${auth.organizations.length} authorized workspaces` : "Single authorized workspace"}</small></div></article>
      <article className="panel-v2 access-summary"><ShieldCheck size={22} /><div><span>YOUR ACCESS</span><strong>{auth.active_organization.role_label}</strong><small>{auth.user.email}</small></div></article>
      <article className="panel-v2 access-summary"><UsersRound size={22} /><div><span>AUTHORIZED MEMBERS</span><strong>{isAdmin ? members.filter((item) => item.status === "active").length : "Role scoped"}</strong><small>{isAdmin ? "Active organization memberships" : "Membership administration is restricted"}</small></div></article>
    </section>}

    {pageError && <div className="form-alert form-alert-error access-page-alert"><AlertTriangle size={18} /><div><strong>Access state unavailable</strong><span>{pageError}</span></div></div>}

    <section className="phase81-role-scope panel-v2">
      <div><span className="kicker">ROLE SCOPE</span><h2>{auth?.active_organization.role_label ?? "Authorized user"}</h2><p>Your role determines which operations the API will accept in this organization.</p></div>
      <ul>{capabilities.map((item) => <li key={item}><Check size={15}/>{item}</li>)}</ul>
      <div className="phase81-role-actions">{canOperate && <Link href="/intake"><ScanSearch size={16}/>New assessment</Link>}<Link href="/context-guide"><BookOpenCheck size={16}/>Context guide</Link><Link href="/migration"><Route size={16}/>Migration roadmap</Link></div>
    </section>

    <section className="access-security-grid phase81-security-grid">
      <article className="panel-v2 account-security-panel">
        <div className="panel-topline"><div><span className="kicker">ACCOUNT SECURITY</span><h2>Change password</h2></div><KeyRound size={20} /></div>
        <p className="access-panel-copy">Verify your current password before replacing it. A successful change revokes the account's other active sessions.</p>
        <form className="security-form" onSubmit={submitPasswordChange}>
          <label><span>Current password</span><PasswordField ariaLabel="Current password" autoComplete="current-password" value={currentPassword} onChange={setCurrentPassword} /></label>
          <div className="security-form-row">
            <label><span>New password</span><PasswordField ariaLabel="New password" autoComplete="new-password" minLength={12} value={newPassword} onChange={setNewPassword} /></label>
            <label><span>Confirm new password</span><PasswordField ariaLabel="Confirm new password" autoComplete="new-password" minLength={12} value={confirmPassword} onChange={setConfirmPassword} /></label>
          </div>
          <small>Use at least 12 characters and at least three of: uppercase, lowercase, numbers and symbols.</small>
          {passwordError && <div className="form-alert form-alert-error compact"><AlertTriangle size={16} /><div><strong>Password not changed</strong><span>{passwordError}</span></div></div>}
          <button className="primary-action" disabled={passwordBusy || !currentPassword || !newPassword || newPassword !== confirmPassword}>{passwordBusy ? "UPDATING…" : "UPDATE PASSWORD"}</button>
        </form>
        {passwordMessage && <div className="inline-success"><Check size={16} />{passwordMessage}</div>}
      </article>

      <article className="panel-v2 phase81-session-panel">
        <div className="panel-topline"><div><span className="kicker">ACTIVE SESSIONS</span><h2>Signed-in account sessions</h2></div><Laptop2 size={20}/></div>
        <p className="access-panel-copy">Review session activity for this account. ECDAT stores session tokens as hashes and lets you invalidate other sessions immediately.</p>
        <div className="phase81-session-list">{sessions.map((session) => <div key={session.id}><span className={session.current ? "current" : ""}><LockKeyhole size={16}/></span><div><strong>{session.current ? "Current session" : "Authorized session"}</strong><small>Last active {relativeTime(session.last_seen_at)} · expires {new Date(session.expires_at).toLocaleString()}</small></div>{session.current && <b>CURRENT</b>}</div>)}</div>
        <button className="ghost-action phase81-session-revoke" type="button" onClick={signOutOtherSessions}>SIGN OUT OTHER SESSIONS</button>
        {sessionMessage && <div className="inline-success"><Check size={15}/>{sessionMessage}</div>}
      </article>
    </section>

    {isAdmin && <section className="panel-v2 reset-data-panel phase81-reset-panel">
      <div className="panel-topline"><div><span className="kicker">ORGANIZATION MAINTENANCE</span><h2>Reset assessment data</h2></div><Trash2 size={20} /></div>
      <div className="danger-note"><AlertTriangle size={18} /><p><strong>Irreversible for this organization.</strong> Deletes assessment history, migration-plan revisions, organization-owned graph state and ECDAT-managed uploaded assessment workspaces. Organization identity, users, memberships and roles remain intact. External mounted directories are never deleted.</p></div>
      <form className="security-form phase81-reset-form" onSubmit={submitAssessmentReset}>
        <label><span>Administrator password</span><PasswordField ariaLabel="Administrator password" autoComplete="current-password" value={resetPassword} onChange={setResetPassword} /></label>
        <label><span>Type RESET to confirm</span><input value={resetConfirmation} onChange={(event) => setResetConfirmation(event.target.value)} placeholder="RESET" required /></label>
        {resetError && <div className="form-alert form-alert-error compact"><AlertTriangle size={16} /><div><strong>Reset not completed</strong><span>{resetError}</span></div></div>}
        <button className="danger-action" disabled={resetBusy || resetConfirmation.trim().toUpperCase() !== "RESET" || !resetPassword}>{resetBusy ? "RESETTING…" : "RESET ORGANIZATION ASSESSMENT DATA"}</button>
      </form>
      {resetResult && <div className="reset-result"><Check size={16} /><div><strong>Assessment data cleared</strong><span>{resetResult.scans_deleted} assessments · {resetResult.migration_plans_deleted} plans · {resetResult.intake_workspaces_deleted} managed intake workspaces removed.</span>{resetResult.graph_cleanup_warning && <small>{resetResult.graph_cleanup_warning}</small>}</div></div>}
    </section>}

    {!isAdmin ? <section className="panel-v2 access-readonly"><ShieldCheck size={24} /><div><h2>Membership administration is restricted</h2><p>{canOperate ? "Your Security Architect / Analyst role can operate assessments, risk scenarios and migration planning, while membership and destructive organization controls remain Administrator-only." : "Your Viewer / Executive role is read-only. You can review authorized evidence, risk, readiness, migration and reports without changing organization state."}</p></div></section> : <div className="access-grid">
      <section className="panel-v2 access-members">
        <div className="panel-topline"><div><span className="kicker">AUTHORIZED PERSONNEL</span><h2>Organization members</h2></div><UsersRound size={20} /></div>
        {memberError && <div className="form-alert form-alert-error member-alert"><AlertTriangle size={16} /><div><strong>Member update failed</strong><span>{memberError}</span></div></div>}
        <div className="member-table">{members.map((member) => <div className="member-row" key={member.membership_id}>
          <div className="member-identity"><b>{member.display_name.split(/\s+/).slice(0,2).map((part)=>part[0]).join("").toUpperCase()}</b><span><strong>{member.display_name}</strong><small>{member.email}</small></span></div>
          <select value={member.role} disabled={member.user_id === auth?.user.id} onChange={(event) => changeMember(member, event.target.value as OrganizationRole)} aria-label={`Role for ${member.display_name}`}>{roles.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}</select>
          <span className={`member-status ${member.status}`}>{member.status}</span>
          <button className={member.status === "active" ? "member-action suspend" : "member-action restore"} type="button" disabled={member.user_id === auth?.user.id} onClick={() => changeMember(member, undefined, member.status === "active" ? "suspended" : "active")}>{member.status === "active" ? "Suspend" : "Restore"}</button>
        </div>)}</div>
      </section>

      <section className="panel-v2 invite-panel">
        <div className="panel-topline"><div><span className="kicker">INVITATION-ONLY ENROLLMENT</span><h2>Authorize a professional</h2></div><UserPlus size={20} /></div>
        <form onSubmit={inviteMember} className="invite-form">
          <label><span>Professional work email</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="analyst@company.example" required /></label>
          <label><span>Organization role</span><select value={role} onChange={(event) => setRole(event.target.value as OrganizationRole)}>{roles.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}</select></label>
          <div className="role-explanation">{roles.find((item) => item.value === role)?.note}</div>
          <button className="primary-action" disabled={busy}>{busy ? "CREATING INVITATION…" : "CREATE SECURE INVITATION"}</button>
        </form>
        {inviteError && <div className="form-alert form-alert-error invite-alert"><AlertTriangle size={17} /><div><strong>Invitation not created</strong><span>{inviteError}</span></div></div>}
        {invite && <div className="invite-result"><div><Check size={18} /><span><strong>Invitation created</strong><small>Expires {new Date(invite.expires_at).toLocaleString()}</small></span></div><code>{invite.invite_token}</code><button type="button" onClick={copyInvite}>{copied ? <Check size={15} /> : <Clipboard size={15} />}{copied ? "Copied invite link" : "Copy invite link"}</button><p>ECDAT does not email credentials. Deliver this one-time invitation link through an approved company communication channel.</p></div>}
        <details className="workspace-create"><summary>Create another isolated workspace</summary><form onSubmit={createWorkspace}><label><span>Workspace / organization name</span><input value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} placeholder="Subsidiary or business unit" required /></label><button type="submit" disabled={busy}>CREATE WORKSPACE</button></form>{workspaceError && <div className="form-alert form-alert-error compact"><AlertTriangle size={15} /><div><span>{workspaceError}</span></div></div>}<p>Use separate workspaces when assessment history and access membership must remain isolated. You become the first administrator of the new workspace.</p></details>
      </section>
    </div>}
  </div></AppShell>;
}
