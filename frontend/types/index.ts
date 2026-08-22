export interface FailedPayment {
  transaction_id: string;
  customer_id: string;
  amount: number;
  currency: string;
  payment_method: string;
  payment_instrument_id: string;
  issuer_bank: string;
  error_code: string | null;
  error_description: string;
  failed_at: string;
  network_type: string;
  latency_ms: number;
  risk_score: number;
  true_root_cause: string;
  status: string;
  final_action: string | null;
  total_attempts: number;
  recovered_amount: number;
  resolved_at: string | null;
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
  created_at: string;
}

export interface AuditListResponse {
  total: number;
  page: number;
  page_size: number;
  items: AuditLogEntry[];
}

export interface MetricsSummary {
  total_transactions: number;
  total_at_risk_amount: number;
  total_recovered_amount: number;
  recovery_rate: number;
  escalation_rate: number;
  blocked_rate: number;
  false_action_rate: number;
  fraud_block_rate: number;
  avg_time_to_recovery_minutes: number | null;
  median_time_to_recovery_minutes: number | null;
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
  cumulative_recovered_amount: number;
}

export interface ConfigRules {
  root_cause_actions: Record<string, string[]>;
  confidence_threshold: number;
  fraud_risk_score_threshold: number;
  velocity_window_minutes: number;
  velocity_threshold_count: number;
  llm_provider: string;
}
