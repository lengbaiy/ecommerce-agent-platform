export type SchemaVersion = "1.0";
export type DecimalValue = string;
export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export type MarketOverviewStageStatus = "pending" | "running" | "completed" | "partial" | "failed";

export interface MarketDatasetOverview {
  dataset_id: string;
  platform: string;
  market: string;
  category: string;
  display_name: string;
  keyword: string;
  aliases: string[];
  product_count: number;
  review_count: number;
  available_metric_count: number;
  partial_metric_count: number;
  unavailable_metric_count: number;
  profit_input_available: boolean;
  source_timestamp: string;
}

export interface MarketAssessmentOverview {
  task_id: string;
  report_id: string;
  report_status: string;
  decision: EntryDecision;
  summary: string;
  generated_at: string;
}

export interface MarketTaskOverview {
  task_id: string;
  status: TaskStatus;
  query: string;
  current_step: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface MarketPipelineStage {
  code: string;
  label: string;
  description: string;
  nodes: string[];
  status: MarketOverviewStageStatus;
}

export interface MarketOverview {
  schema_version: "1.0";
  market: string;
  generated_at: string;
  monitored_category_count: number;
  fixed_dataset_count: number;
  connected_official_platform_count: number;
  approved_market_metric_batch_count: number;
  available_market_metric_count: number;
  available_metric_count: number;
  partial_metric_count: number;
  profit_ready_dataset_count: number;
  datasets: MarketDatasetOverview[];
  latest_assessment: MarketAssessmentOverview | null;
  latest_task: MarketTaskOverview | null;
  recent_tasks: MarketTaskOverview[];
  pipeline: MarketPipelineStage[];
}

export type TaskStatus =
  | "PENDING"
  | "PLANNING"
  | "RUNNING"
  | "WAITING_APPROVAL"
  | "RETRYING"
  | "DEGRADED"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export type TaskPriority = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
export type ApprovalStatus = "NOT_REQUIRED" | "WAITING_APPROVAL" | "APPROVED" | "REJECTED";
export type DataSourceMode = "fixed_dataset" | "official_api";
export type ProductSort = "default" | "sales_desc" | "price_asc" | "price_desc";
export type MetricStatus = "available" | "unavailable" | "partial" | "stale" | "conflict";
export type ReportStatus = "COMPLETED" | "DEGRADED" | "FAILED";
export type LimitationStatus = "unavailable" | "partial" | "stale" | "conflict";
export type ProfitStatus = "available" | "unavailable";
export type EntryDecision = "GO" | "CONDITIONAL_GO" | "NO_GO" | "INSUFFICIENT_DATA";
export type SalesValueType = "exact" | "lower_bound" | "range" | "unknown";
export type DataLevel = "A" | "B" | "C" | "D";
export type EvidenceType =
  | "product"
  | "review"
  | "market_metric"
  | "profit_input"
  | "dataset"
  | "api_response";

export interface ProfitCalculatorParameters {
  schema_version: SchemaVersion;
  price: DecimalValue;
  product_cost: DecimalValue;
  platform_fee: DecimalValue;
  logistics_cost: DecimalValue;
  advertising_cost: DecimalValue;
  minimum_margin: DecimalValue;
  currency: string;
}

export interface CollectionOptions {
  product_limit: number;
  review_limit_per_product: number | null;
  sort_by: ProductSort;
}

export interface MarketIntelligenceRequest {
  schema_version: SchemaVersion;
  market: string;
  category: string;
  keyword: string;
  platforms: string[];
  data_source_mode: DataSourceMode;
  market_metric_batch_id: string | null;
  market_metric_product_match: MarketMetricProductMatch | null;
  collection: CollectionOptions;
  profit_constraints: ProfitCalculatorParameters | null;
}

export interface MarketIntelligenceBusinessContext {
  schema_version: SchemaVersion;
  market_intelligence_request: MarketIntelligenceRequest;
}

export interface TaskPreviewRequest {
  schema_version: SchemaVersion;
  user_query: string;
  intent: string;
}

export interface DatasetMatch {
  dataset_id: string;
  supported: boolean;
  score: number;
  platform: string;
  market: string;
  category: string;
  canonical_keyword: string;
  matched_aliases: string[];
  reason_code: string | null;
}

export interface DataSourceOption {
  platform: string;
  market: string;
  data_source_mode: DataSourceMode;
  label: string;
  available: boolean;
  supports_products: boolean;
  supports_reviews: boolean;
  supports_market_metrics: boolean;
  unavailable_reason: string | null;
}

export interface PreviewWarning {
  code: string;
  message: string;
  severity: "info" | "warning";
  field: string | null;
}

export interface TaskPreviewResponse {
  schema_version: SchemaVersion;
  intent: string;
  confidence: number;
  normalized_input: MarketIntelligenceRequest | null;
  missing_fields: string[];
  ambiguities: string[];
  dataset_matches: DatasetMatch[];
  data_source_options: DataSourceOption[];
  warnings: PreviewWarning[];
}

export type TaskEventType =
  | "task.planning"
  | "task.running"
  | "task.waiting_approval"
  | "task.degraded"
  | "task.completed"
  | "task.failed"
  | "task.cancelled"
  | "task.cancel_requested"
  | "node.started"
  | "node.completed"
  | "node.retrying"
  | "tool.started"
  | "tool.progress"
  | "tool.completed"
  | "tool.failed"
  | "approval.approved"
  | "approval.rejected";

export interface TaskEvent {
  schema_version: SchemaVersion;
  event_id: string;
  task_id: string;
  trace_id: string;
  event_type: TaskEventType;
  state_version: number;
  step: string | null;
  status: TaskStatus;
  timestamp: string;
  summary: string;
}

export interface TaskError {
  schema_version: SchemaVersion;
  code: string;
  message: string;
  retryable: boolean;
  step: string | null;
  details: Record<string, JsonValue>;
}

export interface AnalysisScope {
  market: string;
  platforms: string[];
  category: string;
  keyword: string;
  start_time: string | null;
  end_time: string | null;
  requested_product_count: number;
  actual_product_count: number;
  actual_review_count: number;
  data_source_mode: DataSourceMode;
}

export interface Statement {
  statement_id: string;
  text: string;
  confidence: number;
  critical: boolean;
  evidence_ids: string[];
  affected_by_limitations: string[];
}

export interface DataLimitation {
  limitation_id: string;
  field: string;
  status: LimitationStatus;
  reason_code: string;
  message: string;
  affected_conclusions: string[];
  evidence_ids: string[];
}

export interface MarketMetric {
  metric_code: string;
  value: JsonValue;
  unit: string | null;
  status: MetricStatus;
  reason_code: string | null;
  scope: AnalysisScope;
  methodology: string;
  evidence_ids: string[];
  source_timestamp: string | null;
}

export interface MarketSnapshot {
  status: MetricStatus;
  scope: AnalysisScope;
  metrics: MarketMetric[];
  evidence_ids: string[];
}

export interface CompetitorItem {
  rank: number;
  platform: string;
  market: string;
  product_id: string;
  title: string;
  brand: string | null;
  price: DecimalValue;
  currency: string;
  sales_display: string | null;
  sales_value: number | null;
  sales_value_type: SalesValueType;
  rating: DecimalValue | null;
  review_count: number | null;
  shop_name: string | null;
  source_ref: string;
  evidence_ids: string[];
}

export interface ReviewTheme {
  theme: string;
  mention_count: number;
  mention_ratio: DecimalValue;
  summary: string;
  representative_review_ids: string[];
  evidence_ids: string[];
}

export interface ReviewInsight {
  status: MetricStatus;
  sample_scope: AnalysisScope;
  sentiment_distribution: Record<string, DecimalValue | number>;
  themes: ReviewTheme[];
  pain_points: ReviewTheme[];
  unmet_needs: ReviewTheme[];
  representative_review_ids: string[];
  evidence_ids: string[];
}

export interface ProfitAnalysis {
  status: ProfitStatus;
  selling_price: DecimalValue | null;
  total_cost: DecimalValue | null;
  profit: DecimalValue | null;
  margin: DecimalValue | null;
  minimum_margin: DecimalValue | null;
  meets_minimum_margin: boolean | null;
  breakdown: Record<string, DecimalValue>;
  currency: string | null;
  calculation_version: string;
  evidence_ids: string[];
}

export interface EntryAssessment {
  decision: EntryDecision;
  summary: string;
  evidence_ids: string[];
  limitation_ids: string[];
}

export interface EvidenceReference {
  evidence_id: string;
  evidence_type: EvidenceType;
  data_level: DataLevel;
  data_source: string;
  platform: string;
  product_id: string | null;
  review_id: string | null;
  query_range: Record<string, JsonValue>;
  source_timestamp: string;
  ingest_timestamp: string;
  tool_call_id: string;
  collection_run_id: string;
  snapshot_ref: string;
  sha256: string;
  data_version: string;
  sample_scope: AnalysisScope;
}

export interface MarketIntelligenceReport {
  schema_version: SchemaVersion;
  report_id: string;
  task_id: string;
  status: ReportStatus;
  scope: AnalysisScope;
  market_snapshot: MarketSnapshot;
  competitor_matrix: CompetitorItem[];
  review_insights: ReviewInsight;
  profit_analysis: ProfitAnalysis;
  entry_assessment: EntryAssessment;
  facts: Statement[];
  inferences: Statement[];
  opportunity_signals: Statement[];
  risk_signals: Statement[];
  suggested_actions: Statement[];
  data_limitations: DataLimitation[];
  evidence_refs: EvidenceReference[];
  generated_at: string;
}

export interface AgentEvidenceRef {
  id: string;
  grade: DataLevel;
  source: string;
  summary: string;
}

export interface MarketIntelligenceResultPayload {
  schema_version: SchemaVersion;
  market_intelligence_report: MarketIntelligenceReport;
}

export interface AgentResult {
  result_type: string;
  summary: string;
  facts: string[];
  inferences: string[];
  actions: string[];
  evidence_refs: AgentEvidenceRef[];
  confidence: number;
  requires_approval: boolean;
  payload: Record<string, JsonValue> | MarketIntelligenceResultPayload;
}

export interface TaskCreate {
  tenant_id?: string | null;
  user_id?: string | null;
  user_query: string;
  intent: string;
  business_context: MarketIntelligenceBusinessContext | Record<string, JsonValue>;
  constraints: Record<string, JsonValue>;
  priority: TaskPriority;
}

export interface AgentTask {
  id: string;
  trace_id: string;
  created_at: string;
  updated_at: string;
  status: TaskStatus;
  current_step: string | null;
  retry_count: number;
  state_version: number;
  request: TaskCreate;
  result: AgentResult | null;
  approval_status: ApprovalStatus;
  approval_hash: string | null;
  approver_id: string | null;
  events: TaskEvent[];
  error: TaskError | null;
}

export interface AgentTaskList {
  items: AgentTask[];
  total: number;
}

export type MarketMetricBatchStatus =
  | "pending_review"
  | "approved"
  | "rejected"
  | "disabled";
export type MarketMetricSourceType =
  | "official_api"
  | "official_report"
  | "licensed_provider"
  | "authorized_export"
  | "manual_import";
export type MarketMetricValueKind = "direct" | "derived";
export type MarketMetricProductDecision = "same_product" | "different_product" | "uncertain";
export type MarketMetricProductMatchMethod =
  | "deterministic_alias"
  | "deterministic_exact"
  | "llm"
  | "unavailable";

export interface MarketMetricProductMatch {
  batch_id: string;
  decision: MarketMetricProductDecision;
  confidence: number;
  requested_product: string;
  batch_product: string;
  requested_normalized_name: string;
  batch_normalized_name: string;
  reason: string;
  method: MarketMetricProductMatchMethod;
  provider: string | null;
  model: string | null;
  prompt_version: string;
}

export interface MarketMetricBatchCreate {
  platform: string;
  market: string;
  category: string;
  keyword: string;
  period_start: string;
  period_end: string;
  source_name: string;
  source_type: MarketMetricSourceType;
  source_description: string | null;
  source_timestamp: string;
  methodology: string;
  license_or_authorization: string;
  data_version: string;
}

export interface MarketMetricBatch extends MarketMetricBatchCreate {
  id: string;
  tenant_id: string;
  trace_id: string;
  created_at: string;
  updated_at: string;
  original_file_ref: string | null;
  original_file_sha256: string | null;
  status: MarketMetricBatchStatus;
  uploaded_by: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  review_codes: string[];
}

export interface MarketMetricObservation {
  id: string;
  tenant_id: string;
  trace_id: string;
  created_at: string;
  batch_id: string;
  metric_code: string;
  value_kind: MarketMetricValueKind;
  value: string | number | null;
  unit: string | null;
  currency: string | null;
  status: MetricStatus;
  reason_code: string | null;
  methodology: string;
  source_timestamp: string;
  growth_type: "yoy" | "qoq" | "mom" | "cagr" | null;
  comparison_period_start: string | null;
  comparison_period_end: string | null;
  formula_code: string | null;
  formula_version: string | null;
  source_observation_ids: string[];
  calculated_at: string | null;
}

export interface MarketMetricUploadResult {
  schema_version: SchemaVersion;
  batch_id: string;
  status: MarketMetricBatchStatus;
  direct_metric_count: number;
  derived_metric_count: number;
  created_at: string;
  approval_codes: string[];
  reviewed_by: string | null;
}

export interface MarketMetricBatchList {
  items: MarketMetricBatch[];
  total: number;
  limit: number;
  offset: number;
}

export interface MarketMetricBatchCandidate {
  batch: MarketMetricBatch;
  product_match: MarketMetricProductMatch;
}

export interface MarketMetricBatchCandidateList {
  items: MarketMetricBatchCandidate[];
}

export interface MarketMetricBatchDetail {
  batch: MarketMetricBatch;
  direct_observations: MarketMetricObservation[];
  derived_observations: MarketMetricObservation[];
}
