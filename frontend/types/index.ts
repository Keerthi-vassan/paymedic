export interface FailedPayment {
  transaction_id: string;
  customer_id: string;
  /** Paise (smallest currency subunit) -- convert via formatCurrency, never display raw. */
  amount: number;
  currency: string;
  payment_method: string;
  payment_instrument_id: string;
  issuer_bank: string;
  ip_address: string;
  error_code: string;
  error_source: string;
  error_step: string;
  error_reason: string | null;
  failed_at: string;
  network_type: string;
  latency_ms: number;
  risk_score: number;
  /** "unknown" for webhook-ingested rows -- a real event carries no label,
   * so those rows are excluded from every accuracy and false-action figure. */
  true_root_cause: string;
  /** "synthetic" | "razorpay_webhook" -- where this row entered the system. */
  ingest_source: string;
  status: string;
  final_action: string | null;
  total_attempts: number;
  /** Paise. */
  recovered_amount: number;
  resolved_at: string | null;
  /** Marks this row as one of the small, fixed-count subset attempted
   * against a real Razorpay test-mode transaction. See real_execution_verified
   * for whether that attempt actually completed against the real gateway. */
  is_real: boolean;
  /** True only once a real gateway response was actually obtained -- a
   * real candidate whose attempt fell back to simulated stays is_real=true,
   * real_execution_verified=false, and must be treated as simulated in the UI. */
  real_execution_verified: boolean;
  gateway_order_id: string | null;
  gateway_payment_id: string | null;
}

export interface PaymentsListResponse {
  total: number;
  page: number;
  page_size: number;
  items: FailedPayment[];
}

export interface GenerateBatchResponse {
  count: number;
  seed: number;
}

export interface PipelineRunResponse {
  processed: number;
  recovered: number;
  escalated: number;
  blocked: number;
  /** Paise. */
  total_recovered_amount: number;
}

export interface AuditLogEntry {
  id: number;
  transaction_id: string;
  event_type: string;
  source: string;
  root_cause: string | null;
  confidence: number | null;
  action_taken: string | null;
  reasoning: string;
  outcome: string | null;
  attempt_number: number | null;
  scheduled_at: string | null;
  created_at: string;
  /** "real_razorpay" | "simulated" | null -- only populated on action_execution events. */
  execution_source: string | null;
  gateway_order_id: string | null;
  gateway_payment_id: string | null;
  gateway_status: string | null;
  /** Only populated on "notification" events: the exact customer-facing copy
   * a send_reminder action put out. */
  notification_body: string | null;
}

export interface AuditListResponse {
  total: number;
  page: number;
  page_size: number;
  items: AuditLogEntry[];
}

export interface MetricsSummary {
  total_transactions: number;
  /** Paise. */
  total_at_risk_amount: number;
  /** Paise. */
  total_recovered_amount: number;
  recovery_rate: number;
  escalation_rate: number;
  blocked_rate: number;
  /** Actions ground truth says should never have been taken -- a retry against
   * a true fraud case or a true hard decline. Graded against true_root_cause,
   * so a miss counts whether or not the safety monitor caught it. */
  false_action_rate: number;
  false_action_count: number;
  /** How much of what was actioned the safety monitor later retracted. This
   * measures the monitor's catch volume, NOT the system's error rate. */
  safety_override_rate: number;
  fraud_block_rate: number;
  avg_time_to_recovery_minutes: number | null;
  median_time_to_recovery_minutes: number | null;
  /** How many of this batch's small real-candidate subset actually completed
   * against a genuine Razorpay test-mode transaction (verified <= candidate). */
  real_candidate_count: number;
  real_execution_verified_count: number;
}

export interface RootCauseBreakdownRow {
  root_cause: string;
  total: number;
  recovered: number;
  escalated: number;
  blocked: number;
  open: number;
  recovery_rate: number;
}

export interface TimelinePoint {
  resolved_at: string;
  /** Paise. */
  cumulative_recovered_amount: number;
}

export interface ConfigRules {
  root_cause_actions: Record<string, string[]>;
  decline_type: Record<string, "hard" | "soft">;
  confidence_threshold: number;
  fraud_risk_score_threshold: number;
  network_retry_ceiling: number;
  velocity_window_minutes: number;
  velocity_threshold_count: number;
  ip_velocity_threshold_count: number;
  quiet_hours_start: number;
  quiet_hours_end: number;
  payday_lookahead_days: number;
  llm_provider: string;
  razorpay_execution_enabled: boolean;
  webhook_ingestion_enabled: boolean;
}

export interface ClassifierPathRow {
  /** "rule_engine" | "llm" | "llm_error" */
  path: string;
  total: number;
  correct: number;
  accuracy: number;
}

export interface ConfusionRow {
  true_root_cause: string;
  total: number;
  /** Predicted label -> count. Only non-zero entries are present. */
  predicted: Record<string, number>;
}

export interface CalibrationBucket {
  label: string;
  lower: number;
  upper: number;
  total: number;
  correct: number;
  accuracy: number;
  mean_confidence: number;
}

export interface ClassifierMetrics {
  total_classified: number;
  /** Rows with usable ground truth; webhook rows have none and are excluded. */
  graded: number;
  ungraded: number;
  overall_accuracy: number;
  paths: ClassifierPathRow[];
  confusion: ConfusionRow[];
  calibration: CalibrationBucket[];
  confidence_threshold: number;
  above_threshold_total: number;
  above_threshold_accuracy: number;
  below_threshold_total: number;
  below_threshold_accuracy: number;
}
