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
