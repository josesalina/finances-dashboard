export interface SnapshotSummary {
  id: number;
  period: string;
  period_date: string;
  total_value: number;
  cash: number;
  dividend_income: number;
  realized_pnl_net: number;
  semaphore_code: string | null;
  created_at: string;
}

export interface Holding {
  id: number;
  symbol: string;
  description: string;
  qty: number;
  market_price: number;
  market_value: number;
  cost_price: number;
  cost_basis: number;
  unrealized_pnl: number;
  pnl_pct: number;
  weight: number;
  target_weight: number | null;
  sharpe: number | null;
}

export interface Dividend {
  id: number;
  date: string;
  symbol: string;
  event_type: string;
  description: string;
  amount: number;
}

export interface Transaction {
  id: number;
  date: string;
  symbol: string;
  side: string;
  event_type: string;
  qty: number;
  price: number;
  amount: number;
}

export interface SnapshotDetail extends SnapshotSummary {
  account_no: string;
  source_pdf_name: string;
  parsed_at: string;
  markowitz_raw: Record<string, unknown> | null;
  semaforo_raw: Record<string, unknown> | null;
  advisor_report: string;
  holdings: Holding[];
  dividends: Dividend[];
  transactions: Transaction[];
}

export interface DividendMonthCell {
  gross: number;
  withheld: number;
  net: number;
  projected: boolean;
}

export interface DividendCalendarRow {
  symbol: string;
  total_real_gross: number;
  total_real_withheld: number;
  total_real_net: number;
  total_proj_gross: number;
  total_proj_withheld: number;
  total_proj_net: number;
  months: Record<string, DividendMonthCell>;
}

export interface DividendCalendarMonth {
  period_date: string;
  period: string;
  label: string;
  projected: boolean;
}

export interface DividendScheduleEntry {
  symbol: string;
  frequency: string;
  interval_months: number;
  last_pay_date: string | null;
  last_record_date: string | null;
  last_ex_date: string | null;
  last_div_per_share: number | null;
  next_pay_date: string | null;
  next_ex_date: string | null;
}

export interface DividendCalendarResponse {
  months: DividendCalendarMonth[];
  rows: DividendCalendarRow[];
  totals: {
    real_gross: number;
    real_withheld: number;
    real_net: number;
    proj_gross: number;
    proj_withheld: number;
    proj_net: number;
    by_month: Record<string, DividendMonthCell & { projected: boolean }>;
  };
  schedule: DividendScheduleEntry[];
}

export interface DividendConfig {
  id: number;
  symbol: string;
  amount_per_share: number;
  interval_months: number;
  start_date: string;
  end_date: string | null;
  tax_exempt: boolean;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface EvolutionPoint {
  id: number;
  period_date: string;
  period: string;
  total_value: number;
  cash: number;
  dividend_income: number;
  invested_capital: number;
}

export interface SemaphoreRun {
  id: number;
  snapshot_id: number;
  period: string;
  period_date: string;
  ran_at: string;
  semaphore_code: string | null;
  semaforo_raw: Record<string, unknown>;
}
