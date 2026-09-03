export type Confidence = { level: "low" | "medium" | "high"; score: number; reasons: string[] };
export type Evidence = {
  id: string; detector: string; detector_version: string; method: string;
  location: { uri: string; path?: string | null; line_start?: number | null; line_end?: number | null; symbol?: string | null };
  fingerprint: string; summary: string; attributes: Record<string, unknown>;
};
export type Finding = {
  id: string; scanner_id: string; title: string;
  asset: { id: string; asset_type: string; canonical_name: string; version?: string | null; algorithm_family?: string | null; key_size_bits?: number | null; mode?: string | null; properties: Record<string, unknown> };
  evidence: Evidence[]; confidence: Confidence; tags: string[];
};
export type ScannerExecution = { scanner_id: string; status: string; finding_count: number; duration_ms: number; error?: string | null };
export type GraphNode = { id: string; node_type: string; label: string; properties: Record<string, unknown> };
export type GraphEdge = { id: string; source_id: string; target_id: string; edge_type: string; properties: Record<string, unknown> };
export type RiskFactor = { code: string; label: string; contribution: number; rationale: string };
export type RiskAssessment = {
  asset_id: string; priority: "unknown" | "low" | "moderate" | "elevated" | "critical"; model_version: string;
  rationale: string[]; assumptions: Record<string, unknown>; score?: number | null;
  quantum_posture: "vulnerable" | "reduced_margin" | "resistant" | "contextual" | "unknown";
  hndl_exposure: boolean; mosca_margin_years?: number | null; factors: RiskFactor[];
};
export type GraphInsight = { node_id: string; degree: number; inbound: number; outbound: number; blast_radius: number; centrality: number; migration_blocker: boolean; reasons: string[] };
export type QuantumSummary = { vulnerable_assets: number; hndl_exposed_assets: number; critical_assets: number; elevated_assets: number; migration_blockers: number };
export type ScanCoverage = {
  files_observed: number; source_files: number; config_files: number; dependency_manifests: number; certificate_files: number; binary_files: number; container_definitions: number;
  scanners_completed: number; scanners_failed: number; evidence_records: number; confidence_average?: number | null; observations: string[]; limitations: string[];
};
export type ScanSummary = {
  scan_id: string; status: "queued" | "running" | "completed" | "partial" | "failed";
  target: { kind: string; locator: string; display_name?: string | null; metadata: Record<string, unknown> };
  findings: Finding[]; graph_nodes: GraphNode[]; graph_edges: GraphEdge[]; risk_assessments: RiskAssessment[];
  scanner_executions: ScannerExecution[]; graph_insights: GraphInsight[]; quantum_summary?: QuantumSummary | null; context_manifest_loaded: boolean; coverage?: ScanCoverage | null;
};

export type ScenarioAssetDelta = {
  asset_id: string; asset_name: string; before_score: number; after_score: number; score_delta: number;
  before_priority: RiskAssessment["priority"]; after_priority: RiskAssessment["priority"];
  before_hndl: boolean; after_hndl: boolean; before_mosca_margin_years?: number | null; after_mosca_margin_years?: number | null;
};
export type RiskScenarioResult = {
  scan_id: string; generated_at: string; baseline_horizon_years?: number | null; scenario_horizon_years: number;
  assessments: RiskAssessment[]; quantum_summary: QuantumSummary; deltas: ScenarioAssetDelta[]; changed_assets: number;
  priority_increases: number; priority_decreases: number; hndl_added: number; hndl_removed: number;
  narrative: { headline: string; interpretation: string; material_changes: string[]; unchanged_explanation?: string | null };
};

export type MigrationConstraints = { mode: "balanced" | "conservative" | "performance"; prefer_hybrid: boolean; max_parallel_actions: number; change_window_weeks: number };
export type TargetProfile = { name: string; category: "kem" | "signature" | "hybrid_tls" | "classical" | "retain" | "review"; standard: string; maturity: "standardized" | "transitional" | "review"; purpose: string; operational_notes: string[] };
export type MigrationRecommendation = {
  asset_id: string; current_primitive: string; strategy: "hybrid_transition" | "pqc_transition" | "classical_remediation" | "retain_monitor" | "context_review";
  priority_score: number; target_profiles: TargetProfile[]; rationale: string[]; prerequisites: string[]; interoperability_notes: string[]; performance_notes: string[];
  effort_points: number; confidence: Confidence; standards_basis: string[]; recommendation_version: string;
};
export type AgilityFactor = { code: string; label: string; impact: number; rationale: string };
export type CryptoAgilityScore = { node_id: string; label: string; score: number; difficulty: "low" | "moderate" | "high" | "critical"; coverage: "partial" | "good"; factors: AgilityFactor[] };
export type MigrationAction = {
  id: string; wave: number; node_id: string; label: string; action_type: string; asset_ids: string[]; priority_score: number; effort_points: number; estimated_weeks: number;
  within_change_window: boolean; prerequisite_action_ids: string[]; affected_service_ids: string[]; target_profiles: string[]; rationale: string[];
};
export type MigrationWave = {
  wave: number; title: string; actions: MigrationAction[]; estimated_effort_points: number; parallel_slots: number; estimated_duration_weeks: number;
  starts_week: number; ends_week: number; within_change_window: boolean;
};
export type MigrationRoadmap = {
  plan_id: string; scan_id: string; generated_at: string; risk_scenario_horizon_years?: number | null; constraints: MigrationConstraints; recommendations: MigrationRecommendation[]; agility_scores: CryptoAgilityScore[];
  waves: MigrationWave[]; critical_path: string[]; strategy_explanation: string[];
  summary: { total_actions: number; immediate_actions: number; hybrid_actions: number; pqc_actions: number; classical_remediations: number; total_effort_points: number; lowest_agility_score?: number | null; estimated_calendar_weeks: number; actions_within_window: number; deferred_actions: number };
  standards_snapshot: string[];
};

export type ScanHistoryItem = {
  scan_id: string; created_at: string; status: string; target_kind: string; display_name: string; locator: string; source: string; environment: string; owner: string; team: string;
  assets: number; vulnerable: number; hndl: number; blockers: number; critical: number; evidence_count: number; average_confidence?: number | null; files_observed: number; context_manifest_loaded: boolean;
};
export type AssetDelta = { identity: string; name: string; asset_type: string; version?: string | null };
export type ScanComparison = { base_scan_id: string; target_scan_id: string; new_assets: AssetDelta[]; resolved_assets: AssetDelta[]; unchanged_assets: number; asset_delta: number; vulnerable_delta: number; hndl_delta: number; blocker_delta: number; critical_delta: number };

export type ExecutiveReport = {
  scan_id: string; title: string; posture: string; headline: string; scope: Record<string, unknown>; metrics: Record<string, number>; coverage: Record<string, unknown>;
  priority_findings: Array<{ asset_id: string; asset: string; type: string; priority: string; score?: number | null; quantum_posture: string; hndl: boolean; evidence: number; evidence_locations: string[]; affected_services: string[]; reason: string; recommended_action: string; target_profiles: string[] }>;
  management_summary: string[]; technical_observations: string[];
  migration: { waves: number; actions: number; effort_points: number; lowest_readiness?: number | null; estimated_calendar_weeks: number; actions_within_window: number; deferred_actions: number; critical_path: string[]; strategy_explanation: string[]; standards_basis: string[]; risk_scenario_horizon_years?: number | null };
  assumptions: Record<string, unknown>; limitations: string[];
};
