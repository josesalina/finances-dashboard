import sys
import logging
import tempfile
import shutil
import concurrent.futures
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from django.conf import settings

logger = logging.getLogger(__name__)

MONTH_MAP = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4,
    "MAY": 5, "JUNE": 6, "JULY": 7, "AUGUST": 8,
    "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
}

TZ_ARG = ZoneInfo("America/Argentina/Buenos_Aires")
TZ_ET  = ZoneInfo("America/New_York")


def _run_with_timeout(fn, *args):
    """Run fn(*args) in a thread with YFINANCE_TIMEOUT seconds. Preserves original traceback on failure."""
    timeout = getattr(settings, "YFINANCE_TIMEOUT", 60)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn, *args)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(
                f"yfinance call timed out after {timeout}s — the yfinance service may be slow or unavailable."
            )


def _ensure_scripts_in_path():
    scripts_dir = settings.SCRIPTS_DIR
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)


def _import_parsear_pdf():
    _ensure_scripts_in_path()
    from parse_alpaca_pdf import parsear_pdf
    return parsear_pdf


def period_to_date(period: str) -> date:
    """'FEBRUARY - 2026' → date(2026, 2, 1)"""
    parts = period.strip().split(" - ")
    month = MONTH_MAP.get(parts[0].strip().upper(), 1)
    year = int(parts[1].strip())
    return date(year, month, 1)


def run_parse_pdf(pdf_path: str) -> dict:
    """
    Calls parsear_pdf() from the existing script using a temp working dir
    so it doesn't write files to arbitrary locations.
    Returns the alpaca_data dict.
    """
    parsear_pdf = _import_parsear_pdf()

    tmp = tempfile.mkdtemp()
    try:
        dest = Path(tmp) / Path(pdf_path).name
        shutil.copy2(pdf_path, dest)
        data = parsear_pdf(str(dest))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return data


def run_markowitz(alpaca_data: dict) -> dict:
    """Run Markowitz portfolio optimization. Returns the markowitz_output dict."""
    import numpy as np

    _ensure_scripts_in_path()
    from rebalanceo_markowitz import (
        construir_portfolio_dict, download_data, optimize_portfolio,
        risk_analysis, generate_orders, LOOKBACK,
    )

    now_arg = datetime.now(TZ_ARG)

    portfolio = construir_portfolio_dict(alpaca_data)
    symbols   = alpaca_data["symbols"]
    cash      = alpaca_data["cash"]
    total_val = alpaca_data["total_value"]
    current_w = {s: alpaca_data["holdings"][s]["weight"] for s in symbols}

    # yfinance uses dash instead of dot for class-B tickers (BRK.B → BRK-B)
    yf_symbols = [s.replace(".", "-") for s in symbols]
    yf_to_orig = {yf: orig for orig, yf in zip(symbols, yf_symbols)}
    logger.debug("run_markowitz: downloading prices for %s", yf_symbols)
    prices    = _run_with_timeout(download_data, yf_symbols, LOOKBACK, "")
    prices    = prices.rename(columns=yf_to_orig)
    available = [s for s in symbols if s in prices.columns]
    if not available:
        raise ValueError("yfinance no devolvió precios para ningún símbolo del portafolio.")
    prices    = prices[available]
    # Drop columns where yfinance returned all NaN (e.g. ticker lookup failures)
    prices    = prices.dropna(axis=1, how="all")
    available = prices.columns.tolist()
    if prices.empty:
        raise ValueError("No hay datos de precios históricos para los símbolos del portafolio.")
    log_ret   = np.log(prices / prices.shift(1)).dropna()
    if log_ret.empty:
        raise ValueError(
            "No hay suficientes datos históricos para calcular retornos. "
            "Verificá que los tickers del portafolio tengan datos en yfinance."
        )
    last_p    = prices.iloc[-1].to_dict()

    risk_df         = risk_analysis(log_ret, portfolio)
    optimal, _, _   = optimize_portfolio(log_ret, available)

    if not optimal:
        raise ValueError(
            "La optimización de Markowitz no convergió para ninguna estrategia. "
            "Intentá de nuevo — puede ser un problema transitorio con los datos de yfinance."
        )

    PRIMARY = "Conservador (max 12%)"
    if PRIMARY not in optimal:
        PRIMARY = list(optimal.keys())[0]

    orders_df, buy, sell, net = generate_orders(optimal, last_p, portfolio, cash, PRIMARY)

    sector_map = getattr(settings, "SECTOR_MAP", {})
    energy = sum(optimal[PRIMARY]["weights"].get(s, 0) for s in sector_map.get("energy", ["CVX", "XOM"])) * 100
    tech   = sum(optimal[PRIMARY]["weights"].get(s, 0) for s in sector_map.get("tech", ["AAPL", "MSFT", "NVDA", "ADBE", "GOOG", "MU"])) * 100

    return {
        "generated_at":     now_arg.isoformat(),
        "period":           alpaca_data["header"].get("period"),
        "total_value":      total_val,
        "cash":             cash,
        "primary_strategy": PRIMARY,
        "optimal_portfolios": {
            k: {
                "label":   v["label"],
                "return":  round(v["return"] * 100, 2),
                "vol":     round(v["vol"] * 100, 2),
                "sharpe":  round(v["sharpe"], 4),
                "weights": {s: round(w * 100, 2) for s, w in v["weights"].items()},
            }
            for k, v in optimal.items()
        },
        "orders":               orders_df.reset_index().to_dict(orient="records"),
        "cash_flow":            {"sell": round(sell, 2), "buy": round(buy, 2), "net": round(net, 2)},
        "sector_concentration": {"energy_pct": round(energy, 1), "tech_pct": round(tech, 1)},
        "risk_individual":      risk_df.reset_index().to_dict(orient="records"),
        "current_weights":      current_w,
    }


def run_semaforo(alpaca_data: dict, markowitz_data: dict) -> dict:
    """Run market semaphore analysis. Returns the semaforo_output dict."""
    _ensure_scripts_in_path()
    from semaforo_mercado import (
        extraer_ordenes, get_market_data, analizar_vix, analizar_mercado,
        analizar_energia, analizar_refugios, analizar_credito, analizar_sectores,
        analizar_tasas, analizar_emergentes, semaforo_principal, ajustar_ordenes,
    )

    now_arg = datetime.now(TZ_ARG)
    now_et  = datetime.now(TZ_ET)

    ordenes = extraer_ordenes(markowitz_data)
    symbols = alpaca_data["symbols"]
    cash    = alpaca_data["cash"]

    logger.debug("run_semaforo: downloading market data for %s", symbols)
    prices               = _run_with_timeout(get_market_data, symbols)
    vix                  = analizar_vix(prices)
    mercado              = analizar_mercado(prices)
    energia              = analizar_energia(prices)
    refugios, risk_off   = analizar_refugios(prices)
    credito              = analizar_credito(prices)
    sectores             = analizar_sectores(prices)
    tasas                = analizar_tasas(prices)
    emergentes           = analizar_emergentes(prices)

    decision, consejo, code, razones, puntos, detalle = semaforo_principal(
        vix, mercado, risk_off,
        credito=credito, sectores=sectores, tasas=tasas, emergentes=emergentes,
    )
    ajustadas, alertas = ajustar_ordenes(
        ordenes, mercado, energia, vix, risk_off, code,
        credito=credito, sectores=sectores,
    )

    ventas_adj  = {k: v for k, v in ajustadas.items() if v["accion"] == "VENDER" and v["delta_ajustado"] != 0}
    compras_adj = {k: v for k, v in ajustadas.items() if v["accion"] == "COMPRAR" and v["delta_ajustado"] != 0}
    tv = sum(abs(o["delta_ajustado"]) for o in ventas_adj.values())
    tc = sum(o["delta_ajustado"] for o in compras_adj.values())

    return {
        "generated_at": now_arg.isoformat(),
        "hora_arg":     now_arg.strftime("%A %d/%m/%Y %H:%M"),
        "hora_ny":      now_et.strftime("%A %d/%m/%Y %H:%M ET"),
        "semaforo": {
            "decision": decision, "code": code, "consejo": consejo,
            "puntos": puntos, "razones": razones,
        },
        "vix":               vix,
        "mercado":           mercado,
        "energia":           energia,
        "refugios":          refugios,
        "risk_off":          risk_off,
        "credito":           credito,
        "sectores":          sectores,
        "tasas":             tasas,
        "emergentes":        emergentes,
        "score_detalle":     detalle,
        "alertas":           alertas,
        "ordenes_ajustadas": ajustadas,
        "cash_flow": {
            "cash_inicial":  cash,
            "total_venta":   round(tv, 2),
            "total_compra":  round(tc, 2),
            "cash_final":    round(cash + tv - tc, 2),
        },
    }


def run_asesor(alpaca_data: dict, markowitz_data: dict, semaforo_data: dict) -> str:
    """Generate the advisor markdown report. Returns the report string."""
    _ensure_scripts_in_path()
    from asesor_financiero import generar_reporte
    return generar_reporte(alpaca_data, markowitz_data, semaforo_data)


def run_stock_analyzer(symbol: str) -> dict:
    """Run stock/ETF analysis for a single ticker. Returns structured data dict."""
    _ensure_scripts_in_path()
    from stock_analyzer import analyze_to_dict
    return analyze_to_dict(symbol.upper().replace(".", "-"))


def run_current_prices(symbols: list) -> dict:
    """
    Fetch the latest available price for each symbol via yfinance.
    Returns {symbol: price_or_None}.
    """
    import yfinance as yf

    yf_symbols = [s.replace(".", "-") for s in symbols]
    yf_to_orig = {yf_s: orig for orig, yf_s in zip(symbols, yf_symbols)}

    def _fetch():
        return yf.download(
            yf_symbols, period="5d", interval="1d",
            auto_adjust=True, progress=False,
        )

    data = _run_with_timeout(_fetch)
    result = {}

    if data.empty:
        return {orig: None for orig in symbols}

    closes = data["Close"]

    for yf_sym, orig_sym in yf_to_orig.items():
        try:
            col = closes if len(yf_symbols) == 1 else closes[yf_sym]
            result[orig_sym] = round(float(col.dropna().iloc[-1]), 4)
        except Exception:
            result[orig_sym] = None

    return result
