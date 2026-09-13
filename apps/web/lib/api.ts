import type {
  AuthState,
  AuthSession,
  ExecutiveReport,
  InvitationResponse,
  MemberSummary,
  MigrationConstraints,
  MigrationRoadmap,
  OrganizationRole,
  RiskScenarioResult,
  ScanComparison,
  ScanHistoryItem,
  ScanSummary,
} from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_ECDAT_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function fail(response: Response, label: string): Promise<never> {
  let detail = "";
  try {
    const payload = await response.clone().json() as { detail?: string | { message?: string } };
    if (typeof payload.detail === "string") detail = payload.detail;
    else if (payload.detail && typeof payload.detail.message === "string") detail = payload.detail.message;
  } catch {
    detail = (await response.text()).trim();
  }
  throw new ApiError(response.status, detail ? `${label}: ${detail}` : `${label} (${response.status})`);
}

function request(input: string, init: RequestInit = {}) {
  return fetch(input, { ...init, credentials: "include" });
}

export type ReferenceAssessmentOptions = {
  display_name?: string; environment?: string; owner?: string; team?: string;
  data_lifetime_years?: number; migration_time_years?: number; data_sensitivity?: string; business_criticality?: string;
  public_exposure?: boolean; confidentiality_required?: boolean;
};

export async function fetchBootstrapStatus(): Promise<{ setup_required: boolean }> {
  const response = await request(`${API_BASE}/v1/auth/bootstrap-status`, { cache: "no-store" });
  if (!response.ok) return fail(response, "Unable to check platform setup");
  return response.json();
}

export async function bootstrapPlatform(payload: { organization_name: string; display_name: string; email: string; password: string }): Promise<AuthState> {
  const response = await request(`${API_BASE}/v1/auth/bootstrap`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (!response.ok) return fail(response, "Platform setup failed");
  return response.json();
}

export async function fetchLoginOrganizations(payload: { email: string; password: string }): Promise<import("./types").AuthOrganization[]> {
  const response = await request(`${API_BASE}/v1/auth/login-options`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (!response.ok) return fail(response, "Sign in verification failed");
  const value = await response.json() as { organizations: import("./types").AuthOrganization[] };
  return value.organizations;
}

export async function login(payload: { email: string; password: string; organization_id?: string }): Promise<AuthState> {
  const response = await request(`${API_BASE}/v1/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (!response.ok) return fail(response, "Sign in failed");
  return response.json();
}

export async function logout(): Promise<void> {
  const response = await request(`${API_BASE}/v1/auth/logout`, { method: "POST" });
  if (!response.ok && response.status !== 401) return fail(response, "Sign out failed");
}

export async function changePassword(payload: { current_password: string; new_password: string; confirm_password: string }): Promise<void> {
  const response = await request(`${API_BASE}/v1/auth/change-password`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (!response.ok) return fail(response, "Password change failed");
}

export async function fetchSessions(): Promise<AuthSession[]> {
  const response = await request(`${API_BASE}/v1/auth/sessions`, { cache: "no-store" });
  if (!response.ok) return fail(response, "Unable to load account sessions");
  return response.json();
}

export async function revokeOtherSessions(): Promise<{ revoked: number }> {
  const response = await request(`${API_BASE}/v1/auth/sessions/revoke-others`, { method: "POST" });
  if (!response.ok) return fail(response, "Unable to sign out other sessions");
  return response.json();
}

export type AssessmentResetResult = {
  scans_deleted: number;
  migration_plans_deleted: number;
  graph_nodes_deleted: number;
  graph_edges_deleted: number;
  intake_workspaces_deleted: number;
  graph_cleanup_warning?: string | null;
};

export async function resetOrganizationAssessmentData(payload: { current_password: string; confirmation: string }): Promise<AssessmentResetResult> {
  const response = await request(`${API_BASE}/v1/auth/organization/reset-assessment-data`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (!response.ok) return fail(response, "Assessment data reset failed");
  return response.json();
}

export async function fetchAuthState(): Promise<AuthState> {
  const response = await request(`${API_BASE}/v1/auth/me`, { cache: "no-store" });
  if (!response.ok) return fail(response, "Authentication required");
  return response.json();
}

export async function switchOrganization(organization_id: string): Promise<AuthState> {
  const response = await request(`${API_BASE}/v1/auth/switch-organization`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ organization_id }) });
  if (!response.ok) return fail(response, "Unable to switch workspace");
  return response.json();
}

export async function createOrganization(name: string): Promise<import("./types").AuthOrganization> {
  const response = await request(`${API_BASE}/v1/auth/organizations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
  if (!response.ok) return fail(response, "Unable to create organization workspace");
  return response.json();
}

export async function createInvitation(email: string, role: OrganizationRole): Promise<InvitationResponse> {
  const response = await request(`${API_BASE}/v1/auth/invitations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, role }) });
  if (!response.ok) return fail(response, "Unable to create invitation");
  return response.json();
}

export async function acceptInvitation(payload: { token: string; display_name: string; password: string }): Promise<AuthState> {
  const response = await request(`${API_BASE}/v1/auth/invitations/accept`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (!response.ok) return fail(response, "Invitation acceptance failed");
  return response.json();
}

export async function fetchMembers(): Promise<MemberSummary[]> {
  const response = await request(`${API_BASE}/v1/auth/members`, { cache: "no-store" });
  if (!response.ok) return fail(response, "Unable to load organization members");
  return response.json();
}

export async function updateMember(membershipId: string, payload: { role?: OrganizationRole; status?: "active" | "suspended" }): Promise<MemberSummary> {
  const response = await request(`${API_BASE}/v1/auth/members/${membershipId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (!response.ok) return fail(response, "Unable to update organization member");
  return response.json();
}

export async function runReferenceAssessment(quantumHorizonYears = 15, options: ReferenceAssessmentOptions = {}): Promise<ScanSummary> {
  const query = new URLSearchParams({ quantum_horizon_years: String(quantumHorizonYears) });
  for (const [key, value] of Object.entries(options)) if (value !== undefined) query.set(key, String(value));
  const response = await request(`${API_BASE}/v1/scans/reference?${query}`, { method: "POST" });
  if (!response.ok) return fail(response, "Reference assessment failed");
  return response.json() as Promise<ScanSummary>;
}

export async function scanMountedPath(payload: { path: string; display_name: string; environment: string; owner: string; team: string; quantum_horizon_years: number; data_lifetime_years: number; migration_time_years: number; data_sensitivity: string; business_criticality: string; public_exposure: boolean; confidentiality_required: boolean }): Promise<ScanSummary> {
  const response = await request(`${API_BASE}/v1/scans/directory`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: payload.path, display_name: payload.display_name, environment: payload.environment, owner: payload.owner, team: payload.team, source_name: "Mounted workspace", risk_context: { data_lifetime_years: payload.data_lifetime_years, migration_time_years: payload.migration_time_years, quantum_horizon_years: payload.quantum_horizon_years, data_sensitivity: payload.data_sensitivity, business_criticality: payload.business_criticality, public_exposure: payload.public_exposure, confidentiality_required: payload.confidentiality_required } }) });
  if (!response.ok) return fail(response, "Directory assessment failed");
  return response.json() as Promise<ScanSummary>;
}

export type AssessmentUploadSource = { file: File; kind: "repository" | "container_image" | "bom" | "connector" | "context" };

export async function uploadMultiSourceAssessment(sources: AssessmentUploadSource[], options: Record<string, string | number | boolean>): Promise<ScanSummary> {
  const form = new FormData();
  sources.forEach((source) => form.append("files", source.file));
  form.append("source_kinds", JSON.stringify(sources.map((source) => source.kind)));
  Object.entries(options).forEach(([key, value]) => form.append(key, String(value)));
  const response = await request(`${API_BASE}/v1/intake/assessment`, { method: "POST", body: form });
  if (!response.ok) return fail(response, "Assessment intake failed");
  return response.json() as Promise<ScanSummary>;
}

export async function uploadEnterpriseArchive(file: File, options: Record<string, string | number | boolean>): Promise<ScanSummary> {
  const form = new FormData(); form.append("file", file); Object.entries(options).forEach(([key, value]) => form.append(key, String(value)));
  const response = await request(`${API_BASE}/v1/intake/archive`, { method: "POST", body: form });
  if (!response.ok) return fail(response, "Archive intake failed"); return response.json() as Promise<ScanSummary>;
}
export async function uploadContainerArchive(file: File, options: Record<string, string | number | boolean>): Promise<ScanSummary> {
  const form = new FormData(); form.append("file", file); Object.entries(options).forEach(([key, value]) => form.append(key, String(value)));
  const response = await request(`${API_BASE}/v1/intake/container`, { method: "POST", body: form });
  if (!response.ok) return fail(response, "Container image intake failed"); return response.json() as Promise<ScanSummary>;
}
export async function uploadCycloneDx(file: File, options: Record<string, string | number | boolean>): Promise<ScanSummary> {
  const form = new FormData(); form.append("file", file); Object.entries(options).forEach(([key, value]) => form.append(key, String(value)));
  const response = await request(`${API_BASE}/v1/intake/bom`, { method: "POST", body: form });
  if (!response.ok) return fail(response, "CBOM intake failed"); return response.json() as Promise<ScanSummary>;
}
export async function fetchLatestScan(): Promise<ScanSummary | null> {
  const response = await request(`${API_BASE}/v1/scans/latest`, { cache: "no-store" });
  if (response.status === 404) return null; if (!response.ok) return fail(response, "Unable to load latest assessment"); return response.json() as Promise<ScanSummary>;
}
export async function fetchScan(scanId: string): Promise<ScanSummary> {
  const response = await request(`${API_BASE}/v1/scans/${scanId}`, { cache: "no-store" }); if (!response.ok) return fail(response, "Unable to load assessment"); return response.json() as Promise<ScanSummary>;
}
export async function fetchScanHistory(limit = 30): Promise<ScanHistoryItem[]> {
  const response = await request(`${API_BASE}/v1/scans?limit=${limit}`, { cache: "no-store" }); if (!response.ok) return fail(response, "Unable to load assessment history"); return response.json() as Promise<ScanHistoryItem[]>;
}
export async function compareScans(baseId: string, targetId: string): Promise<ScanComparison> {
  const query = new URLSearchParams({ base_id: baseId, target_id: targetId }); const response = await request(`${API_BASE}/v1/scans/compare?${query}`, { cache: "no-store" }); if (!response.ok) return fail(response, "Unable to compare assessments"); return response.json() as Promise<ScanComparison>;
}
export async function evaluateRiskScenario(scanId: string, horizon: number): Promise<RiskScenarioResult> {
  const response = await request(`${API_BASE}/v1/risk/scenarios`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scan_id: scanId, quantum_horizon_years: horizon }) }); if (!response.ok) return fail(response, "Scenario analysis failed"); return response.json() as Promise<RiskScenarioResult>;
}
export async function buildMigrationPlan(constraints: MigrationConstraints, scanId?: string, quantumHorizonYears?: number): Promise<MigrationRoadmap> {
  const response = await request(`${API_BASE}/v1/migration/plans`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scan_id: scanId ?? null, quantum_horizon_years: quantumHorizonYears ?? null, constraints }) }); if (!response.ok) return fail(response, "Migration plan failed"); return response.json() as Promise<MigrationRoadmap>;
}
export async function fetchLatestMigrationPlan(): Promise<MigrationRoadmap | null> {
  const response = await request(`${API_BASE}/v1/migration/plans/latest`, { cache: "no-store" }); if (response.status === 404) return null; if (!response.ok) return fail(response, "Unable to load latest migration plan"); return response.json() as Promise<MigrationRoadmap>;
}
export async function fetchExecutiveReport(scanId: string): Promise<ExecutiveReport> {
  const response = await request(`${API_BASE}/v1/reports/scans/${scanId}/executive`, { cache: "no-store" }); if (!response.ok) return fail(response, "Unable to generate executive report"); return response.json() as Promise<ExecutiveReport>;
}
