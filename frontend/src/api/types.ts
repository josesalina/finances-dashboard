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

export interface EvolutionPoint {
  id: number;
  period_date: string;
  period: string;
  total_value: number;
  cash: number;
  dividend_income: number;
}
