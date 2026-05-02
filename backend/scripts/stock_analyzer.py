"""
📊 Stock / ETF Analyzer
Uso: python stock_analyzer.py MSFT
      python stock_analyzer.py SPY
      python stock_analyzer.py BMA

Instalar dependencias:
    pip install yfinance pandas numpy scipy colorama tabulate
"""

import sys
import warnings
warnings.filterwarnings("ignore")

import yfinance as yf
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _fmt_plain(val, prefix="", suffix="", decimals=2):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    if isinstance(val, float):
        return f"{prefix}{val:,.{decimals}f}{suffix}"
    return f"{prefix}{val}{suffix}"


def safe(d, key, default=None):
    v = d.get(key, default)
    return v if v not in (None, "N/A", "", 0) else default


# ─────────────────────────────────────────────
# FUNDAMENTAL VALUATION
# ─────────────────────────────────────────────

def evaluate_fundamentals(info, is_etf=False):
    """
    Devuelve un score de -10 (muy caro) a +10 (muy barato)
    y una lista de señales.
    """
    score = 0
    signals = []

    if is_etf:
        # Para ETFs miramos básicamente precio vs NAV y momentum
        signals.append(("Tipo", "ETF — análisis fundamental limitado", "ℹ️"))
        return score, signals

    # ── P/E Ratio ──────────────────────────────
    pe = safe(info, "trailingPE")
    fpe = safe(info, "forwardPE")
    sector = safe(info, "sector", "")

    # Benchmarks de P/E por sector (aproximados)
    pe_benchmarks = {
        "Technology": 28,
        "Communication Services": 22,
        "Consumer Cyclical": 20,
        "Consumer Defensive": 18,
        "Healthcare": 22,
        "Financial Services": 14,
        "Industrials": 18,
        "Energy": 12,
        "Basic Materials": 14,
        "Real Estate": 20,
        "Utilities": 16,
    }
    sector_pe = pe_benchmarks.get(sector, 20)

    if pe:
        if pe < sector_pe * 0.75:
            score += 2
            signals.append(("P/E Trailing", f"{pe:.1f} (sector ~{sector_pe})", "🟢 Barato vs sector"))
        elif pe < sector_pe:
            score += 1
            signals.append(("P/E Trailing", f"{pe:.1f} (sector ~{sector_pe})", "🟡 Razonable"))
        elif pe < sector_pe * 1.3:
            score -= 1
            signals.append(("P/E Trailing", f"{pe:.1f} (sector ~{sector_pe})", "🟠 Algo caro"))
        else:
            score -= 2
            signals.append(("P/E Trailing", f"{pe:.1f} (sector ~{sector_pe})", "🔴 Caro"))
    else:
        signals.append(("P/E Trailing", "N/A", "ℹ️ Sin ganancias o ETF"))

    if fpe:
        if pe and fpe < pe * 0.9:
            score += 1
            signals.append(("P/E Forward", f"{fpe:.1f}", "🟢 Ganancias creciendo"))
        elif pe and fpe > pe * 1.1:
            score -= 1
            signals.append(("P/E Forward", f"{fpe:.1f}", "🔴 Ganancias cayendo"))
        else:
            signals.append(("P/E Forward", f"{fpe:.1f}", "🟡 Estable"))

    # ── PEG Ratio ──────────────────────────────
    peg = safe(info, "pegRatio")
    if peg:
        if peg < 1:
            score += 2
            signals.append(("PEG Ratio", f"{peg:.2f}", "🟢 Infravalorado (PEG<1)"))
        elif peg < 1.5:
            score += 1
            signals.append(("PEG Ratio", f"{peg:.2f}", "🟡 Justo"))
        elif peg < 2:
            score -= 1
            signals.append(("PEG Ratio", f"{peg:.2f}", "🟠 Algo caro"))
        else:
            score -= 2
            signals.append(("PEG Ratio", f"{peg:.2f}", "🔴 Caro vs crecimiento"))

    # ── P/B Ratio ──────────────────────────────
    pb = safe(info, "priceToBook")
    if pb:
        if pb < 1:
            score += 2
            signals.append(("P/Book", f"{pb:.2f}x", "🟢 Bajo valor en libros"))
        elif pb < 3:
            score += 0
            signals.append(("P/Book", f"{pb:.2f}x", "🟡 Normal"))
        elif pb < 6:
            score -= 1
            signals.append(("P/Book", f"{pb:.2f}x", "🟠 Premium"))
        else:
            score -= 2
            signals.append(("P/Book", f"{pb:.2f}x", "🔴 Muy premium"))

    # ── EV/EBITDA ──────────────────────────────
    ev_ebitda = safe(info, "enterpriseToEbitda")
    if ev_ebitda:
        if ev_ebitda < 8:
            score += 2
            signals.append(("EV/EBITDA", f"{ev_ebitda:.1f}x", "🟢 Muy barato"))
        elif ev_ebitda < 14:
            score += 1
            signals.append(("EV/EBITDA", f"{ev_ebitda:.1f}x", "🟡 Razonable"))
        elif ev_ebitda < 20:
            score -= 1
            signals.append(("EV/EBITDA", f"{ev_ebitda:.1f}x", "🟠 Algo caro"))
        else:
            score -= 2
            signals.append(("EV/EBITDA", f"{ev_ebitda:.1f}x", "🔴 Caro"))

    # ── Revenue Growth ──────────────────────────
    rev_growth = safe(info, "revenueGrowth")
    if rev_growth:
        pct = rev_growth * 100
        if pct > 20:
            score += 2
            signals.append(("Crecimiento Ingresos", f"{pct:.1f}%", "🟢 Alto crecimiento"))
        elif pct > 8:
            score += 1
            signals.append(("Crecimiento Ingresos", f"{pct:.1f}%", "🟡 Crecimiento sano"))
        elif pct > 0:
            score += 0
            signals.append(("Crecimiento Ingresos", f"{pct:.1f}%", "🟡 Crecimiento lento"))
        else:
            score -= 2
            signals.append(("Crecimiento Ingresos", f"{pct:.1f}%", "🔴 Cayendo"))

    # ── Profit Margins ──────────────────────────
    margin = safe(info, "profitMargins")
    if margin:
        pct = margin * 100
        if pct > 20:
            score += 1
            signals.append(("Margen Neto", f"{pct:.1f}%", "🟢 Excelente"))
        elif pct > 10:
            score += 0
            signals.append(("Margen Neto", f"{pct:.1f}%", "🟡 Bueno"))
        elif pct > 0:
            score -= 1
            signals.append(("Margen Neto", f"{pct:.1f}%", "🟠 Bajo"))
        else:
            score -= 2
            signals.append(("Margen Neto", f"{pct:.1f}%", "🔴 Pérdidas"))

    # ── Deuda ───────────────────────────────────
    debt_eq = safe(info, "debtToEquity")
    if debt_eq:
        de = debt_eq / 100
        if de < 0.3:
            score += 1
            signals.append(("Deuda/Equity", f"{de:.2f}x", "🟢 Muy poco endeudado"))
        elif de < 1:
            score += 0
            signals.append(("Deuda/Equity", f"{de:.2f}x", "🟡 Manejable"))
        elif de < 2:
            score -= 1
            signals.append(("Deuda/Equity", f"{de:.2f}x", "🟠 Alto"))
        else:
            score -= 2
            signals.append(("Deuda/Equity", f"{de:.2f}x", "🔴 Muy endeudado"))

    # ── ROE ─────────────────────────────────────
    roe = safe(info, "returnOnEquity")
    if roe:
        pct = roe * 100
        if pct > 20:
            score += 1
            signals.append(("ROE", f"{pct:.1f}%", "🟢 Excelente"))
        elif pct > 10:
            signals.append(("ROE", f"{pct:.1f}%", "🟡 Bueno"))
        elif pct > 0:
            score -= 1
            signals.append(("ROE", f"{pct:.1f}%", "🟠 Bajo"))
        else:
            score -= 2
            signals.append(("ROE", f"{pct:.1f}%", "🔴 Negativo"))

    # ── Dividend ────────────────────────────────
    div_yield = safe(info, "dividendYield")
    if div_yield:
        pct = div_yield * 100
        signals.append(("Dividendo", f"{pct:.2f}%", "💰 Paga dividendo"))

    # ── Analyst Target ──────────────────────────
    target = safe(info, "targetMeanPrice")
    price = safe(info, "currentPrice") or safe(info, "regularMarketPrice")
    if target and price:
        upside = (target / price - 1) * 100
        if upside > 20:
            score += 2
            signals.append(("Target Analistas", f"${target:.2f} ({upside:+.1f}%)", "🟢 Gran upside"))
        elif upside > 5:
            score += 1
            signals.append(("Target Analistas", f"${target:.2f} ({upside:+.1f}%)", "🟡 Upside moderado"))
        elif upside > -5:
            signals.append(("Target Analistas", f"${target:.2f} ({upside:+.1f}%)", "🟡 Precio justo"))
        else:
            score -= 2
            signals.append(("Target Analistas", f"${target:.2f} ({upside:+.1f}%)", "🔴 Downside"))

    return score, signals


# ─────────────────────────────────────────────
# ANÁLISIS TÉCNICO — SOPORTES Y RESISTENCIAS
# ─────────────────────────────────────────────

def find_support_resistance(hist, current_price, n_levels=5):
    """
    Encuentra soportes y resistencias usando:
    1. Mínimos/máximos locales
    2. Medias móviles clave (50, 100, 200 días)
    3. Niveles de Fibonacci desde el swing más reciente
    """
    levels = []

    close = hist["Close"].values
    high = hist["High"].values
    low = hist["Low"].values

    # ── 1. Pivots locales (mínimos y máximos) ──
    order = 10  # ventana de búsqueda
    local_min_idx = argrelextrema(low, np.less_equal, order=order)[0]
    local_max_idx = argrelextrema(high, np.greater_equal, order=order)[0]

    for idx in local_min_idx[-20:]:
        levels.append({"precio": round(float(low[idx]), 2), "tipo": "Soporte", "origen": "Pivot local"})
    for idx in local_max_idx[-20:]:
        levels.append({"precio": round(float(high[idx]), 2), "tipo": "Resistencia", "origen": "Pivot local"})

    # ── 2. Medias móviles ──────────────────────
    for ma_period, label in [(50, "MA50"), (100, "MA100"), (200, "MA200")]:
        if len(close) >= ma_period:
            ma_val = round(float(np.mean(close[-ma_period:])), 2)
            tipo = "Soporte" if ma_val < current_price else "Resistencia"
            levels.append({"precio": ma_val, "tipo": tipo, "origen": label})

    # ── 3. Fibonacci ───────────────────────────
    period = min(252, len(close))  # último año
    swing_high = float(np.max(high[-period:]))
    swing_low = float(np.min(low[-period:]))
    diff = swing_high - swing_low

    fib_levels = {
        "Fib 23.6%": swing_high - 0.236 * diff,
        "Fib 38.2%": swing_high - 0.382 * diff,
        "Fib 50.0%": swing_high - 0.500 * diff,
        "Fib 61.8%": swing_high - 0.618 * diff,
        "Fib 78.6%": swing_high - 0.786 * diff,
    }
    for label, val in fib_levels.items():
        val = round(val, 2)
        tipo = "Soporte" if val < current_price else "Resistencia"
        levels.append({"precio": val, "tipo": tipo, "origen": label})

    # ── Agrupar niveles cercanos (dentro del 1.5%) ──
    def cluster(levels, threshold=0.015):
        prices = sorted(set([l["precio"] for l in levels]))
        clusters = []
        used = set()
        for p in prices:
            if p in used:
                continue
            group = [x for x in prices if abs(x - p) / p < threshold and x not in used]
            if group:
                avg = round(np.mean(group), 2)
                origins = list(set([l["origen"] for l in levels if l["precio"] in group]))
                tipo = "Soporte" if avg < current_price else "Resistencia"
                clusters.append({"precio": avg, "tipo": tipo, "confirmaciones": len(group), "origen": ", ".join(origins)})
                for g in group:
                    used.add(g)
        return clusters

    clustered = cluster(levels)
    clustered.sort(key=lambda x: abs(x["precio"] - current_price))

    # Separar soportes y resistencias
    soportes = [l for l in clustered if l["tipo"] == "Soporte" and l["precio"] < current_price]
    resistencias = [l for l in clustered if l["tipo"] == "Resistencia" and l["precio"] > current_price]

    soportes.sort(key=lambda x: x["precio"], reverse=True)  # más cercano primero
    resistencias.sort(key=lambda x: x["precio"])             # más cercano primero

    return soportes[:n_levels], resistencias[:n_levels]


# ─────────────────────────────────────────────
# RSI
# ─────────────────────────────────────────────

def calc_rsi(close, period=14):
    delta = np.diff(close)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = np.mean(gain[-period:])
    avg_loss = np.mean(loss[-period:])
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def analyze(ticker_symbol):
    from tabulate import tabulate
    from colorama import Fore, Style, init
    init(autoreset=True)

    def color(val, good_if_positive=True):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return f"{Style.DIM}N/A{Style.RESET_ALL}"
        is_good = val > 0 if good_if_positive else val < 0
        c = Fore.GREEN if is_good else Fore.RED
        if isinstance(val, float):
            return f"{c}{val:+.2f}%{Style.RESET_ALL}"
        return f"{c}{val}{Style.RESET_ALL}"

    def fmt(val, prefix="", suffix="", decimals=2):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return f"{Style.DIM}N/A{Style.RESET_ALL}"
        if isinstance(val, float):
            return f"{prefix}{val:,.{decimals}f}{suffix}"
        return f"{prefix}{val}{suffix}"
    print(f"\n{'═'*60}")
    print(f"  📊 Analizando: {ticker_symbol.upper()}")
    print(f"{'═'*60}\n")

    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info

    name = safe(info, "longName") or safe(info, "shortName") or ticker_symbol
    asset_type = safe(info, "quoteType", "EQUITY")
    sector = safe(info, "sector", "")
    industry = safe(info, "industry", "")
    current_price = safe(info, "currentPrice") or safe(info, "regularMarketPrice") or safe(info, "navPrice")

    is_etf = asset_type in ("ETF", "MUTUALFUND")

    print(f"  🏢 {name}")
    if sector:
        print(f"  🏭 {sector} › {industry}")
    print(f"  💲 Precio actual: {Fore.CYAN}${current_price:,.2f}{Style.RESET_ALL}\n")

    # ── Precio vs 52w ──────────────────────────
    high52 = safe(info, "fiftyTwoWeekHigh")
    low52 = safe(info, "fiftyTwoWeekLow")
    if high52 and low52 and current_price:
        pct_from_high = (current_price / high52 - 1) * 100
        pct_from_low = (current_price / low52 - 1) * 100
        range_pct = (current_price - low52) / (high52 - low52) * 100

        print(f"  📅 Rango 52 semanas: ${low52:,.2f} — ${high52:,.2f}")
        print(f"     Posición en el rango: {range_pct:.0f}% ", end="")
        if range_pct < 30:
            print(f"{Fore.GREEN}(cerca del mínimo — zona de compra histórica){Style.RESET_ALL}")
        elif range_pct > 70:
            print(f"{Fore.RED}(cerca del máximo — zona de cautela){Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}(zona media){Style.RESET_ALL}")
        print(f"     Desde máximo: {Fore.RED}{pct_from_high:+.1f}%{Style.RESET_ALL}  |  Desde mínimo: {Fore.GREEN}{pct_from_low:+.1f}%{Style.RESET_ALL}\n")

    # ── Fundamentales ──────────────────────────
    print(f"{'─'*60}")
    print(f"  📋 ANÁLISIS FUNDAMENTAL")
    print(f"{'─'*60}")

    score, signals = evaluate_fundamentals(info, is_etf)

    table_data = [[s[0], s[1], s[2]] for s in signals]
    print(tabulate(table_data, headers=["Métrica", "Valor", "Señal"], tablefmt="rounded_outline"))

    # Veredicto
    max_score = 16
    pct_score = (score / max_score) * 100

    print(f"\n  Score fundamental: {score}/{max_score} ({pct_score:.0f}%)\n")
    print(f"  {'─'*40}")
    if score >= 6:
        print(f"  {Fore.GREEN}✅ VEREDICTO: BARATA / OPORTUNIDAD{Style.RESET_ALL}")
        print(f"  Los fundamentos sugieren que la acción tiene valor.")
    elif score >= 2:
        print(f"  {Fore.YELLOW}🟡 VEREDICTO: PRECIO JUSTO{Style.RESET_ALL}")
        print(f"  Ni muy cara ni muy barata. Depende del contexto.")
    elif score >= -2:
        print(f"  {Fore.YELLOW}🟠 VEREDICTO: ALGO CARA{Style.RESET_ALL}")
        print(f"  Hay mejores puntos de entrada.")
    else:
        print(f"  {Fore.RED}🔴 VEREDICTO: CARA{Style.RESET_ALL}")
        print(f"  Los fundamentos no justifican el precio actual.")
    print(f"  {'─'*40}\n")

    # ── Técnico ────────────────────────────────
    print(f"{'─'*60}")
    print(f"  📈 ANÁLISIS TÉCNICO — SOPORTES & RESISTENCIAS")
    print(f"{'─'*60}")

    hist = ticker.history(period="2y")
    if hist.empty:
        print("  ⚠️  Sin datos históricos suficientes.\n")
        return

    close = hist["Close"].values
    rsi = calc_rsi(close)

    print(f"\n  RSI (14): {rsi}", end="  ")
    if rsi < 30:
        print(f"{Fore.GREEN}← SOBREVENDIDO — zona de compra{Style.RESET_ALL}")
    elif rsi > 70:
        print(f"{Fore.RED}← SOBRECOMPRADO — zona de venta{Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}← neutral{Style.RESET_ALL}")

    # MACD simple
    ema12 = pd.Series(close).ewm(span=12).mean().iloc[-1]
    ema26 = pd.Series(close).ewm(span=26).mean().iloc[-1]
    macd = ema12 - ema26
    print(f"  MACD: {macd:+.2f}  ", end="")
    print(f"{Fore.GREEN}(alcista){Style.RESET_ALL}" if macd > 0 else f"{Fore.RED}(bajista){Style.RESET_ALL}")

    soportes, resistencias = find_support_resistance(hist, current_price)

    print(f"\n  🟢 SOPORTES (zonas de compra):")
    if soportes:
        for s in soportes:
            dist = (s["precio"] / current_price - 1) * 100
            stars = "⭐" * min(s["confirmaciones"], 4)
            print(f"     ${s['precio']:>8,.2f}  ({dist:+.1f}%)  {stars}  [{s['origen']}]")
    else:
        print("     Sin soportes identificados en el rango.")

    print(f"\n  🔴 RESISTENCIAS (zonas de venta / targets):")
    if resistencias:
        for r in resistencias:
            dist = (r["precio"] / current_price - 1) * 100
            stars = "⭐" * min(r["confirmaciones"], 4)
            print(f"     ${r['precio']:>8,.2f}  ({dist:+.1f}%)  {stars}  [{r['origen']}]")
    else:
        print("     Sin resistencias identificadas en el rango.")

    # ── Resumen ejecutivo ──────────────────────
    print(f"\n{'─'*60}")
    print(f"  📝 RESUMEN EJECUTIVO")
    print(f"{'─'*60}")

    target_mean = safe(info, "targetMeanPrice")
    rec = safe(info, "recommendationKey", "")
    rec_map = {
        "strong_buy": f"{Fore.GREEN}COMPRA FUERTE{Style.RESET_ALL}",
        "buy": f"{Fore.GREEN}COMPRA{Style.RESET_ALL}",
        "hold": f"{Fore.YELLOW}MANTENER{Style.RESET_ALL}",
        "sell": f"{Fore.RED}VENDER{Style.RESET_ALL}",
        "strong_sell": f"{Fore.RED}VENTA FUERTE{Style.RESET_ALL}",
    }
    if rec:
        print(f"  Consenso analistas: {rec_map.get(rec, rec.upper())}")
    if target_mean and current_price:
        upside = (target_mean / current_price - 1) * 100
        print(f"  Target promedio:    ${target_mean:,.2f}  ({upside:+.1f}% vs precio actual)")

    if soportes:
        print(f"  Soporte clave:      ${soportes[0]['precio']:,.2f}  ({(soportes[0]['precio']/current_price-1)*100:+.1f}%)")
    if resistencias:
        print(f"  Resistencia clave:  ${resistencias[0]['precio']:,.2f}  ({(resistencias[0]['precio']/current_price-1)*100:+.1f}%)")

    print(f"\n{'═'*60}\n")
    print(f"  ⚠️  Este análisis es informativo y no constituye asesoramiento")
    print(f"     financiero. Siempre hacé tu propio análisis.\n")
    print(f"{'═'*60}\n")


def analyze_to_dict(ticker_symbol: str) -> dict:
    """Same analysis as analyze() but returns structured data instead of printing."""
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info

    name = safe(info, "longName") or safe(info, "shortName") or ticker_symbol
    asset_type = safe(info, "quoteType", "EQUITY")
    sector = safe(info, "sector", "")
    industry = safe(info, "industry", "")
    current_price = safe(info, "currentPrice") or safe(info, "regularMarketPrice") or safe(info, "navPrice")
    is_etf = asset_type in ("ETF", "MUTUALFUND")

    high52 = safe(info, "fiftyTwoWeekHigh")
    low52  = safe(info, "fiftyTwoWeekLow")
    price_data: dict = {"current": current_price, "week52_high": high52, "week52_low": low52}
    if high52 and low52 and current_price:
        range_pct = (current_price - low52) / (high52 - low52) * 100
        price_data.update({
            "range_pct":      round(range_pct, 1),
            "pct_from_high":  round((current_price / high52 - 1) * 100, 1),
            "pct_from_low":   round((current_price / low52  - 1) * 100, 1),
        })

    score, signals = evaluate_fundamentals(info, is_etf)
    max_score = 16
    if score >= 6:
        verdict, verdict_emoji = "OPORTUNIDAD", "🟢"
    elif score >= 2:
        verdict, verdict_emoji = "PRECIO JUSTO", "🟡"
    elif score >= -2:
        verdict, verdict_emoji = "ALGO CARA", "🟠"
    else:
        verdict, verdict_emoji = "CARA", "🔴"

    hist = ticker.history(period="2y")
    technical: dict = {}
    supports: list = []
    resistances: list = []
    if not hist.empty and current_price:
        close = hist["Close"].values
        rsi = calc_rsi(close)
        ema12 = float(pd.Series(close).ewm(span=12).mean().iloc[-1])
        ema26 = float(pd.Series(close).ewm(span=26).mean().iloc[-1])
        macd  = round(ema12 - ema26, 2)
        technical = {
            "rsi":        rsi,
            "rsi_signal": "oversold" if rsi < 30 else ("overbought" if rsi > 70 else "neutral"),
            "macd":       macd,
            "macd_signal": "bullish" if macd > 0 else "bearish",
        }
        s, r = find_support_resistance(hist, current_price)
        supports    = [{**lvl, "dist_pct": round((lvl["precio"] / current_price - 1) * 100, 1)} for lvl in s]
        resistances = [{**lvl, "dist_pct": round((lvl["precio"] / current_price - 1) * 100, 1)} for lvl in r]

    target_mean = safe(info, "targetMeanPrice")
    rec = safe(info, "recommendationKey", "")
    rec_labels = {
        "strong_buy": "COMPRA FUERTE", "buy": "COMPRA",
        "hold": "MANTENER", "sell": "VENDER", "strong_sell": "VENTA FUERTE",
    }
    div_yield = safe(info, "dividendYield")

    return {
        "ticker":    ticker_symbol.upper(),
        "name":      name,
        "sector":    sector,
        "industry":  industry,
        "asset_type": asset_type,
        "is_etf":    is_etf,
        "price":     price_data,
        "fundamentals": {
            "score":         score,
            "max_score":     max_score,
            "score_pct":     round((score / max_score) * 100, 1),
            "verdict":       verdict,
            "verdict_emoji": verdict_emoji,
            "signals":       [{"metric": s[0], "value": s[1], "signal": s[2]} for s in signals],
        },
        "technical":   technical,
        "supports":    supports,
        "resistances": resistances,
        "summary": {
            "recommendation":       rec,
            "recommendation_label": rec_labels.get(rec, rec.upper() if rec else ""),
            "target_mean":          target_mean,
            "target_upside_pct":    round((target_mean / current_price - 1) * 100, 1) if target_mean and current_price else None,
            "key_support":          supports[0]    if supports    else None,
            "key_resistance":       resistances[0] if resistances else None,
        },
        "dividend_yield": round(div_yield * 100, 2) if div_yield else None,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("\n  Uso: python stock_analyzer.py <TICKER>")
        print("  Ejemplo: python stock_analyzer.py MSFT")
        print("           python stock_analyzer.py XOM")
        print("           python stock_analyzer.py SPY\n")
        sys.exit(1)

    analyze(sys.argv[1].upper())
