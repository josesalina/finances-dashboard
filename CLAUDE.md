# CLAUDE.md — finances-dashboard

## Stack
- **Backend:** Django 4.x + Django REST Framework — `backend/`
- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS + Recharts — `frontend/`
- **Database:** PostgreSQL 16 on port 5433
- **Python finance scripts:** `../finances/` (path configured via `SCRIPTS_DIR` setting)

## Dev setup

```bash
# Start database
docker-compose up -d db

# Backend (from backend/)
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 8000

# Frontend (from frontend/)
npm install
npm run dev        # → http://localhost:5173
```

## Pages

| Route | File | Description |
|-------|------|-------------|
| `/dashboard` | `pages/Dashboard.tsx` | Portfolio overview: metric cards, evolution chart, holdings table, historial mensual. Header has a "🔍 Buscar ticker" button that opens the `StockSearchPanel` slide-over. |
| `/pipeline` | `pages/Pipeline.tsx` | 4-step workflow UI: upload PDF → Markowitz → Semáforo → Asesor. Each step calls its endpoint and shows logs. After the asesor runs, shows the full markdown report rendered inline. |
| `/months/:id` | `pages/MonthReport.tsx` | Full snapshot detail: summary cards, Markowitz weights chart (actual vs objetivo), rebalance orders table, semaphore panel (VIX, mercado ret_1d), holdings table, advisor report markdown. |
| `/dividends` | `pages/Dividends.tsx` | Dividend calendar: real historical dividends + projected future payments (from DividendConfig) through end of year. Summary cards with totals per symbol and month. |
| `/semaforos` | `pages/Semaforos.tsx` | History of all SemaphoreRun records. Shows semaphore code/decision per run, linked to its snapshot. |
| `/dividend-config` | `pages/DividendConfig.tsx` | CRUD UI for DividendConfig — configure dividend amount/share, frequency (monthly/quarterly/etc), start/end date, tax exemption per symbol. Used to project future dividend income. |

## Shared components

| File | Description |
|------|-------------|
| `components/layout/Layout.tsx` | Sidebar nav (Dashboard, Pipeline) + `<Outlet>` |
| `components/AdvisorReport.tsx` | Renders `advisor_report` markdown with `react-markdown` + `remark-gfm`. Used in Pipeline and MonthReport. Has a "↓ Descargar .md" button. |
| `components/StockSearchPanel.tsx` | Slide-over panel (fixed right, backdrop) for stock/ETF analysis. Accepts `tickers` prop to populate quick-pick buttons — Dashboard passes current holdings sorted by weight. Falls back to hardcoded list if no tickers provided. |

## API endpoints

Base: `http://localhost:8000/api/`

| Method | URL | Purpose |
|--------|-----|---------|
| GET | `snapshots/` | List all snapshots (includes computed `semaphore_code`) |
| GET | `snapshots/{id}/` | Snapshot detail with holdings, dividends, transactions, `semaphore_code` |
| GET | `snapshots/current/` | Latest snapshot detail |
| GET | `snapshots/evolution/` | `[{period_date, period, total_value, cash, dividend_income}]` for charts |
| GET | `snapshots/holdings-history/?symbols=AAPL,SPY` | Historical weight/value/pnl per symbol |
| POST | `snapshots/upload-pdf/` | Upload Alpaca PDF → parse → upsert snapshot. Returns `{id, period, total_value, holdings_count, created}` |
| POST | `snapshots/{id}/run-markowitz/` | Runs Markowitz optimization → saves `markowitz_raw` + updates `Holding.target_weight` and `Holding.sharpe` |
| POST | `snapshots/{id}/run-semaforo/` | Runs market semaphore → saves `semaforo_raw`. Requires markowitz first. |
| POST | `snapshots/{id}/run-advisor/` | Generates markdown report → saves `advisor_report`. Requires semaforo first. |
| GET | `snapshots/{id}/dividends-calendar/` | Projects dividend income per symbol through end of current year, merging real Dividend records with DividendConfig projections. |
| GET | `analyze/?ticker=AAPL` | Full stock/ETF analysis via `stock_analyzer.py`. Returns fundamentals, technical, supports/resistances, summary. |
| GET/POST/PUT/DELETE | `dividend-configs/` | CRUD for DividendConfig records. |
| GET | `semaphore-runs/?snapshot_id=X` | List SemaphoreRun records, optionally filtered by snapshot. |
| POST | `semaphore-runs/run/` | Run semaphore standalone (body: `{snapshot_id}`). Saves result to `snapshot.semaforo_raw` and creates a `SemaphoreRun` record. |

**Pipeline order is enforced:** `upload-pdf` → `run-markowitz` → `run-semaforo` → `run-advisor`. Each step returns 400 if the previous hasn't run.

## Data models (`backend/portfolio/models.py`)

- **MonthlySnapshot** — one record per `(account_no, period_date)`. Key fields: `total_value`, `cash`, `dividend_income`, `realized_pnl_net`. JSON blobs: `alpaca_raw`, `markowitz_raw`, `semaforo_raw`. Text: `advisor_report` (markdown). `semaphore_code` is a computed field on both serializers (reads from `semaforo_raw.semaforo.code`).
- **Holding** — per-symbol position. `target_weight` and `sharpe` are `null` until `run-markowitz` runs.
- **Dividend** — dividend/income events from the PDF.
- **Transaction** — buy/sell events from the PDF.
- **SemaphoreRun** — records each semaphore execution. FK to MonthlySnapshot, stores `semaforo_raw` JSON and `ran_at` timestamp. Enables history of semaphore runs per snapshot.
- **DividendConfig** — per-symbol dividend schedule config. Fields: `symbol`, `amount_per_share`, `interval_months` (1/2/3/6/12), `start_date`, `end_date` (null = ongoing), `tax_exempt`, `notes`. Used by `dividends-calendar/` to project future income.

## Script integration (`backend/portfolio/script_runner.py`)

Imports directly from `../finances/` at call time (lazy, via `sys.path`). Never calls `main()` — calls internal functions only to avoid side effects (no file writes, no plots, no CSV output).

| Function | Source script | What it calls |
|----------|--------------|---------------|
| `run_parse_pdf(pdf_path)` | `parse_alpaca_pdf.py` | `parsear_pdf()` in a temp dir |
| `run_markowitz(alpaca_data)` | `rebalanceo_markowitz.py` | `construir_portfolio_dict`, `download_data`, `optimize_portfolio`, `risk_analysis`, `generate_orders` |
| `run_semaforo(alpaca_data, markowitz_data)` | `semaforo_mercado.py` | `extraer_ordenes`, `get_market_data`, analysis chain, `semaforo_principal`, `ajustar_ordenes` |
| `run_asesor(alpaca_data, markowitz_data, semaforo_data)` | `asesor_financiero.py` | `generar_reporte()` — returns markdown string |
| `run_stock_analyzer(symbol)` | `stock_analyzer.py` | `analyze_to_dict()` — returns structured dict |

`SCRIPTS_DIR` env var overrides the default path (`../../finances` relative to backend).

**Ticker normalization:** yfinance requires dashes instead of dots for class-B shares (`BRK.B` → `BRK-B`). `run_markowitz` and `run_stock_analyzer` in `script_runner.py` apply `.replace(".", "-")` before calling yfinance, then rename columns back to the original dot format so they match the portfolio data.

## Key JSON structures (from `semaforo_raw`)

The semaphore panel in MonthReport reads:
- `semaforo_raw.semaforo.code` → `"GO"` / `"PARTIAL"` / `"WAIT"` / `"ABORT"`
- `semaforo_raw.semaforo.decision` → display string e.g. `"🟡 EJECUTAR PARCIAL"`
- `semaforo_raw.semaforo.consejo` → advice text
- `semaforo_raw.mercado.{SPY,QQQ,...}.ret_1d` → daily return per ticker
- `semaforo_raw.vix.valor` + `.nivel` → VIX value and level label

Markowitz orders table reads from `markowitz_raw.orders` (array). Field names use Spanish with special chars: `"Símbolo"`, `"Acción"`, `"Δ Dólares ($)"`.

## Frontend dependencies added

- `react-markdown` + `remark-gfm` — markdown rendering with GFM table support (required — without `remark-gfm`, tables render as plain text)
- `@tailwindcss/typography` — `prose` classes for markdown styling (registered in `tailwind.config.js`)

## Key env vars

```
SECRET_KEY=...
DB_NAME=finances
DB_USER=finances
DB_PASSWORD=finances123
DB_HOST=localhost
DB_PORT=5433
SCRIPTS_DIR=/path/to/finances   # optional, defaults to ../../finances
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

## What does NOT exist (to avoid re-implementing)

- No authentication — `AllowAny` on all endpoints by design.
- No Celery / async tasks — pipeline steps are synchronous (yfinance calls can take 10–30s).
- No migration for existing `semaphore_code` column — it's a computed `SerializerMethodField`, not a DB column.
- No separate "orders" model — rebalance orders live in `markowitz_raw.orders` JSON, not a table.
- `stock_analyzer.py` `analyze()` CLI function still works — only `tabulate`/`colorama` imports were moved inside it so `analyze_to_dict()` can be imported without those deps installed in the Django env.
- `pages/StockSearch.tsx` exists but is NOT wired to any route in `App.tsx` — the stock search UI lives in `StockSearchPanel.tsx` (slide-over on Dashboard).
