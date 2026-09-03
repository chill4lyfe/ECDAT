# Authentication and organization isolation — implementation contract

This directory is intentionally reserved for the identity implementation. The current application operates as one local workspace so the security-analysis product can be exercised without pretending that tenant isolation already exists.

## Required product behavior

Implement authentication and authorization without changing the evidence, graph, risk or migration domain contracts.

1. Every authenticated user belongs to one or more organizations/workspaces.
2. Every persisted assessment (`ScanRecord`) must be owned by an `organization_id`; record the initiating `user_id` separately.
3. Every migration-plan revision must inherit the organization scope of its source assessment. A client-supplied organization ID must never be trusted without server-side membership verification.
4. Assessment history, reports, exports, comparisons and latest-assessment queries must be filtered by the active organization and the user's permissions.
5. A new assessment creates a history entry. Risk-scenario evaluation and migration-plan rebuilds are revisions against that assessment and must not create additional assessment records.
6. The current `/history` UI is a single-workspace placeholder. Replace or adapt it so organization switching and permission-aware history are explicit.

## Expected roles

At minimum support:
- Organization Admin — membership, workspace settings, all assessments.
- Security Architect / Analyst — create assessments, scenarios, migration plans and reports.
- Viewer / Executive — read assessment/report surfaces without scan or configuration writes.

Use role checks on the API; hiding frontend controls is not authorization.

## Required backend changes

- Add user, organization, membership/session models and migrations.
- Add `organization_id` and `created_by_user_id` to `scans`.
- Add `organization_id` to `migration_plans` or enforce it through the referenced assessment with an indexed relationship.
- Resolve the active organization from the authenticated session/token on the server.
- Scope `catalog.latest`, `catalog.list`, `catalog.get`, comparisons, reports and exports.
- Reject cross-organization scan IDs with a non-disclosing authorization response.
- Preserve the current scan JSON/domain schemas; tenancy is persistence/access context, not cryptographic evidence.

## Frontend integration points

- Collapsed navigation may add an account/workspace control at the bottom of the rail.
- `/history` becomes organization-scoped assessment history.
- `/intake` should display the active organization and default owner/team fields from profile/workspace settings where available.
- `/reports` and `/investigate` must never load an assessment outside the active workspace.

## Acceptance criteria

- Two test organizations cannot retrieve, compare, export or plan against each other's assessment IDs.
- A scenario/plan revision does not inflate assessment-history count.
- Switching organizations changes latest assessment, history and reports deterministically.
- API authorization tests exist for every scan/report/export/migration read path.
- No auth secret, token, password or session material is written into ECDAT evidence records or logs.
