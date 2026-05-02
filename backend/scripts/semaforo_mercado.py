"""
=============================================================
  SCRIPT 3/4 — SEMÁFORO DE MERCADO
  semaforo_mercado.py
=============================================================
Lee alpaca_data.json y markowitz_output.json.
Evalúa condiciones del mercado y ajusta las órdenes en tiempo real.

USO:
    python semaforo_mercado.py
    python semaforo_mercado.py alpaca_data.json markowitz_output.json

SALIDA:
    semaforo_output.json   ← para asesor_financiero.py
    ordenes_ajustadas_YYYYMMDD_HHMM.csv

INDICADORES:
    VIX (nivel + tendencia vs SMA20), SPY/QQQ (ret 1d/5d/20d, SMA50, RSI14),
    HYG (crédito high-yield), GLD/TLT/UUP (refugios / risk-off),
    XLF (financiero), XLU (defensivos), ^TNX (tasa 10Y), EEM (emergentes),
    XLE/USO (energía)
"""

import warnings, sys, json
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ_ARG  = ZoneInfo("America/Argentina/Buenos_Aires")
TZ_ET   = ZoneInfo("America/New_York")
NOW_ARG = datetime.now(TZ_ARG)
NOW_ET  = datetime.now(TZ_ET)

VIX_NORMAL  = 20
VIX_ALERTA  = 25
VIX_PELIGRO = 30
SPY_CAIDA   = -1.5

# ─────────────────────────────────────────────
#  CARGA DE DATOS
# ─────────────────────────────────────────────

def cargar_datos(alpaca_path="alpaca_data.json",
                 markowitz_path="markowitz_output.json"):
    for p in [alpaca_path, markowitz_path]:
        if not Path(p).exists():
            print(f"❌ No se encontró {p}")
            print("   Ejecutá primero los scripts anteriores.")
            sys.exit(1)
    with open(alpaca_path, encoding="utf-8") as f:
        alpaca = json.load(f)
    with open(markowitz_path, encoding="utf-8") as f:
        markowitz = json.load(f)
    print(f"✅ Datos Alpaca: {alpaca['header'].get('period','?')}")
    print(f"✅ Markowitz:   {markowitz.get('primary_strategy','?')}")
    return alpaca, markowitz


def extraer_ordenes(markowitz_data: dict) -> dict:
    """Convierte la lista de órdenes del JSON al formato del semáforo."""
    ordenes = {}
    for row in markowitz_data.get("orders", []):
        sym = row.get("Símbolo") or row.get("Symbol", "")
        if not sym:
            continue
        ordenes[sym] = {
            "accion":    row.get("Acción", "MANTENER"),
            "delta_usd": row.get("Δ Dólares ($)", 0.0),
            "peso_obj":  row.get("Peso Objetivo (%)", 2.0) / 100,
        }
    return ordenes

# ─────────────────────────────────────────────
#  DATOS DE MERCADO
# ─────────────────────────────────────────────

def get_market_data(symbols_portfolio):
    print("\n📡 Descargando datos de mercado...")
    macro = [
        "SPY", "QQQ",        # mercado broad
        "XLE", "USO",        # energía
        "GLD", "TLT", "UUP", # refugios
        "HYG",               # crédito high-yield
        "XLF",               # financiero
        "XLU",               # utilities/defensivos
        "XLK",               # tecnología
        "EEM",               # emergentes
        "^VIX",              # volatilidad
        "^TNX",              # tasa 10 años USA
    ]
    all_tickers = list(dict.fromkeys(macro + symbols_portfolio))

    raw = yf.download(all_tickers, period="60d", interval="1d",
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"]
    else:
        prices = raw[["Close"]]
    prices.columns = [c.replace("^", "") for c in prices.columns]
    prices.ffill(inplace=True)
    print(f"  ✅ {len(prices)} días cargados")
    return prices

# ─────────────────────────────────────────────
#  HELPERS TÉCNICOS
# ─────────────────────────────────────────────

def calcular_rsi(series: pd.Series, period: int = 14) -> float:
    """RSI clásico de Wilder. Devuelve el último valor."""
    delta = series.diff().dropna()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_g = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_l = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs    = avg_g / avg_l.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 1) if not rsi.empty else 50.0

# ─────────────────────────────────────────────
#  ANÁLISIS DE CONDICIONES
# ─────────────────────────────────────────────

def analizar_vix(prices):
    if "VIX" not in prices.columns:
        return {"valor": 20, "cambio": 0, "nivel": "DESCONOCIDO",
                "semaforo": "🟡", "vs_sma20": 0.0}
    s     = prices["VIX"].dropna()
    v     = float(s.iloc[-1])
    delta = float(s.iloc[-1] - s.iloc[-2])
    sma20 = float(s.rolling(20).mean().iloc[-1]) if len(s) >= 20 else v
    vs_sma20 = round((v / sma20 - 1) * 100, 1) if sma20 else 0.0

    if v < VIX_NORMAL:    sem, nivel = "🟢", "BAJO — Mercado tranquilo"
    elif v < VIX_ALERTA:  sem, nivel = "🟡", "MODERADO — Precaución"
    elif v < VIX_PELIGRO: sem, nivel = "🟠", "ALTO — Considerar esperar"
    else:                 sem, nivel = "🔴", "CRÍTICO — NO operar hoy"

    return {"valor": round(v, 2), "cambio": round(delta, 2),
            "nivel": nivel, "semaforo": sem, "vs_sma20": vs_sma20}


def analizar_mercado(prices):
    resultado = {}
    for t in ["SPY", "QQQ", "XLE"]:
        if t not in prices.columns:
            continue
        s    = prices[t].dropna()
        r1   = float((s.iloc[-1] / s.iloc[-2] - 1) * 100)
        r5   = float((s.iloc[-1] / s.iloc[-6] - 1) * 100)  if len(s) >= 6  else 0.0
        r10  = float((s.iloc[-1] / s.iloc[-11] - 1) * 100) if len(s) >= 11 else 0.0
        r20  = float((s.iloc[-1] / s.iloc[-21] - 1) * 100) if len(s) >= 21 else 0.0
        sma10 = float(s.rolling(10).mean().iloc[-1])
        sma50 = float(s.rolling(50).mean().iloc[-1]) if len(s) >= 50 else float(s.mean())
        rsi14 = calcular_rsi(s)
        resultado[t] = {
            "ret_1d":    round(r1, 2),
            "ret_5d":    round(r5, 2),
            "ret_10d":   round(r10, 2),
            "ret_20d":   round(r20, 2),
            "bajo_sma10": bool(s.iloc[-1] < sma10),
            "bajo_sma50": bool(s.iloc[-1] < sma50),
            "rsi14":     rsi14,
            "precio":    round(float(s.iloc[-1]), 2),
        }
    return resultado


def analizar_energia(prices):
    resultado = {}
    for t in ["XLE", "USO", "XOM", "CVX"]:
        if t not in prices.columns:
            continue
        s  = prices[t].dropna()
        r1 = float((s.iloc[-1] / s.iloc[-2] - 1) * 100)
        r5 = float((s.iloc[-1] / s.iloc[-6] - 1) * 100) if len(s) >= 6 else 0.0
        resultado[t] = {"ret_1d": round(r1, 2), "ret_5d": round(r5, 2),
                        "precio": round(float(s.iloc[-1]), 2)}
    return resultado


def analizar_refugios(prices):
    refugios = {}
    for t in ["GLD", "TLT", "UUP"]:
        if t not in prices.columns:
            continue
        s  = prices[t].dropna()
        r5 = float((s.iloc[-1] / s.iloc[-6] - 1) * 100) if len(s) >= 6 else 0.0
        refugios[t] = round(r5, 2)
    risk_off = sum(1 for v in refugios.values() if v > 0.5) >= 2
    return refugios, risk_off


def analizar_credito(prices) -> dict:
    """HYG: crédito high-yield. Caída = spread widening = stress crediticio."""
    if "HYG" not in prices.columns:
        return {"hyg_ret_1d": 0.0, "hyg_ret_5d": 0.0, "stress": False}
    s    = prices["HYG"].dropna()
    r1   = float((s.iloc[-1] / s.iloc[-2] - 1) * 100)
    r5   = float((s.iloc[-1] / s.iloc[-6] - 1) * 100) if len(s) >= 6 else 0.0
    stress = r5 < -0.8
    return {"hyg_ret_1d": round(r1, 2), "hyg_ret_5d": round(r5, 2), "stress": stress}


def analizar_sectores(prices) -> dict:
    """XLF (financiero) y XLU (utilities/defensivos). Rotación defensiva = riesgo."""
    resultado = {}
    for t in ["XLF", "XLU", "XLK"]:
        if t not in prices.columns:
            continue
        s  = prices[t].dropna()
        r1 = float((s.iloc[-1] / s.iloc[-2] - 1) * 100)
        r5 = float((s.iloc[-1] / s.iloc[-6] - 1) * 100) if len(s) >= 6 else 0.0
        resultado[t] = {"ret_1d": round(r1, 2), "ret_5d": round(r5, 2),
                        "precio": round(float(s.iloc[-1]), 2)}

    spy5 = 0.0
    if "SPY" in prices.columns:
        s = prices["SPY"].dropna()
        spy5 = float((s.iloc[-1] / s.iloc[-6] - 1) * 100) if len(s) >= 6 else 0.0

    xlu5 = resultado.get("XLU", {}).get("ret_5d", 0.0)
    xlf5 = resultado.get("XLF", {}).get("ret_5d", 0.0)

    # XLU supera a SPY significativamente = rotación defensiva = señal de riesgo
    rotacion_defensiva = (xlu5 - spy5) > 2.0
    # Financieras muy debilitadas = stress sistémico potencial
    stress_financiero   = xlf5 < -3.0

    resultado["rotacion_defensiva"] = rotacion_defensiva
    resultado["stress_financiero"]  = stress_financiero
    return resultado


def analizar_tasas(prices) -> dict:
    """TNX: tasa del tesoro a 10 años. Suba brusca presiona valuaciones."""
    if "TNX" not in prices.columns:
        return {"valor": 0.0, "cambio_5d": 0.0, "spike": False}
    s    = prices["TNX"].dropna()
    val  = float(s.iloc[-1])
    c5   = float(s.iloc[-1] - s.iloc[-6]) if len(s) >= 6 else 0.0
    spike = c5 > 0.15  # +15bps en 5 días = presión significativa
    return {"valor": round(val, 3), "cambio_5d": round(c5, 3), "spike": spike}


def analizar_emergentes(prices) -> dict:
    """EEM: mercados emergentes. Señal de estrés global."""
    if "EEM" not in prices.columns:
        return {"ret_1d": 0.0, "ret_5d": 0.0, "stress": False}
    s  = prices["EEM"].dropna()
    r1 = float((s.iloc[-1] / s.iloc[-2] - 1) * 100)
    r5 = float((s.iloc[-1] / s.iloc[-6] - 1) * 100) if len(s) >= 6 else 0.0
    return {"ret_1d": round(r1, 2), "ret_5d": round(r5, 2), "stress": r5 < -3.0}

# ─────────────────────────────────────────────
#  SEMÁFORO PRINCIPAL
# ─────────────────────────────────────────────

def semaforo_principal(vix_data, mercado, risk_off,
                       credito=None, sectores=None, tasas=None, emergentes=None):
    puntos, razones, detalle = 0, [], {}

    # ── VIX ──────────────────────────────────
    v = vix_data["valor"]
    if v >= VIX_PELIGRO:
        p = 3; puntos += p; razones.append(f"VIX crítico ({v:.1f})")
    elif v >= VIX_ALERTA:
        p = 2; puntos += p; razones.append(f"VIX elevado ({v:.1f})")
    elif v >= VIX_NORMAL:
        p = 1; puntos += p; razones.append(f"VIX moderado ({v:.1f})")
    else:
        p = 0
    detalle["vix_nivel"] = p

    vs_sma20 = vix_data.get("vs_sma20", 0.0)
    if vs_sma20 > 20:
        puntos += 1; razones.append(f"VIX +{vs_sma20:.0f}% sobre SMA20 (acelerando)")
        detalle["vix_tendencia"] = 1
    else:
        detalle["vix_tendencia"] = 0

    # ── SPY retornos ─────────────────────────
    spy = mercado.get("SPY", {})
    spy1d = spy.get("ret_1d", 0)
    spy5d = spy.get("ret_5d", 0)
    spy20d = spy.get("ret_20d", 0)

    if spy1d < -2.0:
        p = 3; puntos += p; razones.append(f"SPY cae {spy1d:.1f}% hoy (caída fuerte)")
    elif spy1d < SPY_CAIDA:
        p = 2; puntos += p; razones.append(f"SPY cae {spy1d:.1f}% hoy")
    else:
        p = 0
    detalle["spy_1d"] = p

    if spy5d < -3.0:
        p = 2; puntos += p; razones.append(f"SPY cae {spy5d:.1f}% en 5 días")
    elif spy5d < -1.0:
        p = 1; puntos += p; razones.append(f"SPY débil esta semana ({spy5d:.1f}%)")
    else:
        p = 0
    detalle["spy_5d"] = p

    if spy20d < -5.0:
        p = 2; puntos += p; razones.append(f"SPY cae {spy20d:.1f}% en 20 días (tendencia bajista)")
    else:
        p = 0
    detalle["spy_20d"] = p

    # ── SPY posición técnica ──────────────────
    if spy.get("bajo_sma50"):
        puntos += 1; razones.append("SPY bajo SMA50 (tendencia bajista de mediano plazo)")
        detalle["spy_sma50"] = 1
    else:
        detalle["spy_sma50"] = 0

    rsi14 = spy.get("rsi14", 50)
    if rsi14 < 35:
        puntos += 1; razones.append(f"RSI14 SPY = {rsi14} (momentum muy débil)")
        detalle["spy_rsi"] = 1
    else:
        detalle["spy_rsi"] = 0

    # ── Refugios / risk-off ───────────────────
    if risk_off:
        puntos += 2; razones.append("Risk-off activo (GLD/TLT/UUP subiendo)")
        detalle["risk_off"] = 2
    else:
        detalle["risk_off"] = 0

    # ── Crédito (HYG) ────────────────────────
    if credito:
        if credito.get("stress"):
            hyg5 = credito.get("hyg_ret_5d", 0)
            puntos += 2; razones.append(f"Crédito high-yield bajo presión (HYG {hyg5:.1f}% en 5D)")
            detalle["credito"] = 2
        else:
            detalle["credito"] = 0

    # ── Sectores ─────────────────────────────
    if sectores:
        if sectores.get("rotacion_defensiva"):
            puntos += 1; razones.append("Rotación defensiva: XLU supera a SPY en 5D")
            detalle["rotacion_defensiva"] = 1
        else:
            detalle["rotacion_defensiva"] = 0

        if sectores.get("stress_financiero"):
            xlf5 = sectores.get("XLF", {}).get("ret_5d", 0)
            puntos += 2; razones.append(f"Financiero bajo presión (XLF {xlf5:.1f}% en 5D)")
            detalle["stress_financiero"] = 2
        else:
            detalle["stress_financiero"] = 0

    # ── Tasas ────────────────────────────────
    if tasas and tasas.get("spike"):
        c5 = tasas.get("cambio_5d", 0)
        puntos += 1; razones.append(f"Tasas 10Y subieron {c5*100:.0f}bps en 5D (presión en valuaciones)")
        detalle["tasas_spike"] = 1
    else:
        detalle["tasas_spike"] = 0

    # ── Emergentes ───────────────────────────
    if emergentes and emergentes.get("stress"):
        eem5 = emergentes.get("ret_5d", 0)
        puntos += 1; razones.append(f"Emergentes en stress (EEM {eem5:.1f}% en 5D)")
        detalle["emergentes"] = 1
    else:
        detalle["emergentes"] = 0

    # ── Decisión final ───────────────────────
    if puntos <= 2:
        dec, cons, code = (
            "🟢 EJECUTAR",
            "Condiciones favorables. Ejecutá el plan completo.",
            "GO",
        )
    elif puntos <= 6:
        dec, cons, code = (
            "🟡 EJECUTAR PARCIAL",
            "Ejecutá ventas + compras defensivas. Esperá para tech y activos volátiles.",
            "PARTIAL",
        )
    elif puntos <= 10:
        dec, cons, code = (
            "🟠 ESPERAR",
            "Solo ejecutá ventas prioritarias. Postergá todas las compras.",
            "WAIT",
        )
    else:
        dec, cons, code = (
            "🔴 NO OPERAR",
            "Múltiples señales de estrés simultáneas. Esperá estabilización 1-3 días.",
            "ABORT",
        )

    return dec, cons, code, razones, puntos, detalle

# ─────────────────────────────────────────────
#  AJUSTE DE ÓRDENES
# ─────────────────────────────────────────────

def ajustar_ordenes(ordenes, mercado, energia, vix_data, risk_off, semaforo_code,
                    credito=None, sectores=None):
    spy_1d   = mercado.get("SPY", {}).get("ret_1d", 0)
    vix_val  = vix_data["valor"]
    xle_5d   = energia.get("XLE", {}).get("ret_5d", 0)
    xom_5d   = energia.get("XOM", {}).get("ret_5d", 0)
    xlf_5d   = (sectores or {}).get("XLF", {}).get("ret_5d", 0)
    credito_stress = (credito or {}).get("stress", False)
    ajustadas, alertas = {}, []

    SIEMPRE_VENDER = ["ADBE", "NU", "VZ"]
    VOLATILES      = ["NVDA", "MU", "GOOG"]

    for sym, orden in ordenes.items():
        acc   = orden["accion"]
        delta = orden["delta_usd"]
        factor, razon, prioridad = 1.0, "Sin cambios", "NORMAL"

        if acc == "VENDER" and sym in SIEMPRE_VENDER:
            factor, razon, prioridad = 1.0, "Sharpe negativo → vender siempre", "PRIORITARIA"

        elif acc == "COMPRAR":
            if semaforo_code == "ABORT":
                factor, razon, prioridad = 0.0, "🔴 Mercado en pánico → no comprar", "CANCELADA"
            elif semaforo_code == "WAIT":
                factor, razon, prioridad = 0.0, "🟠 Condiciones adversas → posponer", "POSPUESTA"
            elif credito_stress and risk_off:
                factor, razon, prioridad = 0.15, "Crédito + risk-off simultáneos → compra mínima", "MÍNIMA"
            elif risk_off:
                factor, razon, prioridad = 0.25, "Risk-off global → compra mínima", "MÍNIMA"
            elif credito_stress:
                factor, razon, prioridad = 0.4, "Stress crediticio → compra reducida", "REDUCIDA"
            elif spy_1d < SPY_CAIDA:
                factor, razon, prioridad = 0.5, f"SPY cae {spy_1d:.1f}% → compra 50%", "REDUCIDA"
            elif sym in VOLATILES and vix_val > VIX_ALERTA:
                factor, razon, prioridad = 0.3, f"VIX={vix_val:.0f} + activo volátil → 30%", "ESPERAR"
            elif xlf_5d < -3.0:
                factor, razon, prioridad = 0.5, f"Financiero débil ({xlf_5d:.1f}%) → caución", "REDUCIDA"

        elif acc == "VENDER":
            if sym == "CVX" and xle_5d > 3.0:
                factor, razon, prioridad = 0.4, f"XLE +{xle_5d:.1f}% esta semana → venta parcial", "AJUSTADA"
                alertas.append(f"CVX: energía en rally, venta reducida al 40%")

        if sym == "XOM" and acc == "COMPRAR" and xom_5d > 5.0:
            factor = min(factor, 0.6)
            razon  = f"XOM subió {xom_5d:.1f}% → comprar escalonado"
            prioridad = "ESCALONADA"
            alertas.append("XOM: comprar en 2 tandas, no perseguir el rally")

        delta_adj = round(delta * factor, 2)
        ajustadas[sym] = {
            "accion":         acc,
            "delta_original": round(delta, 2),
            "delta_ajustado": delta_adj,
            "factor":         factor,
            "prioridad":      prioridad,
            "razon":          razon,
        }
        if factor != 1.0 and acc != "MANTENER":
            alertas.append(f"{sym}: {razon}")

    return ajustadas, alertas

# ─────────────────────────────────────────────
#  REPORTE EN CONSOLA
# ─────────────────────────────────────────────

def imprimir_reporte(vix, mercado, energia, refugios, risk_off,
                     credito, sectores, tasas, emergentes,
                     decision, consejo, razones, puntos, detalle,
                     ajustadas, alertas, cash):
    W = 72
    print("\n" + "═" * W)
    print(f"  🚦  SEMÁFORO DE MERCADO")
    print(f"  🇦🇷  {NOW_ARG.strftime('%A %d/%m/%Y %H:%M')} (Buenos Aires)")
    print(f"  🇺🇸  {NOW_ET.strftime('%A %d/%m/%Y %H:%M')} (New York ET)")
    print("═" * W)

    print(f"\n  {vix['semaforo']} VIX: {vix['valor']} ({vix['cambio']:+.2f}) — {vix['nivel']}")
    print(f"     vs SMA20: {vix.get('vs_sma20', 0):+.1f}%")

    print(f"\n  📊 Mercado:")
    for t, d in mercado.items():
        e = "🔴" if d["ret_1d"] < -1 else ("🟡" if d["ret_1d"] < 0 else "🟢")
        sma = "⚠️ bajo SMA50" if d.get("bajo_sma50") else "✅ sobre SMA50"
        print(f"     {e} {t:5s}  Hoy:{d['ret_1d']:+.2f}%  5D:{d['ret_5d']:+.2f}%  "
              f"20D:{d.get('ret_20d', 0):+.2f}%  RSI:{d.get('rsi14', 50):.0f}  {sma}")

    print(f"\n  🛢️  Energía:")
    for t, d in energia.items():
        e = "🟢" if d["ret_5d"] > 2 else ("🟡" if d["ret_5d"] > 0 else "🔴")
        print(f"     {e} {t:5s}  Hoy:{d['ret_1d']:+.2f}%  5D:{d['ret_5d']:+.2f}%")

    print(f"\n  🏦 Refugios (5D): " +
          "  ".join(f"{t}:{v:+.1f}%" for t, v in refugios.items()))
    if risk_off:
        print(f"     ⚠️  SEÑAL RISK-OFF ACTIVA")

    if credito:
        hyg1 = credito.get("hyg_ret_1d", 0)
        hyg5 = credito.get("hyg_ret_5d", 0)
        stress_lbl = "⚠️ STRESS CREDITICIO" if credito.get("stress") else "✅ Normal"
        print(f"\n  💳 Crédito HYG:  Hoy:{hyg1:+.2f}%  5D:{hyg5:+.2f}%  {stress_lbl}")

    if sectores:
        print(f"\n  🔄 Sectores:")
        for t in ["XLF", "XLU", "XLK"]:
            if t in sectores:
                d = sectores[t]
                print(f"     {t:5s}  Hoy:{d['ret_1d']:+.2f}%  5D:{d['ret_5d']:+.2f}%")
        if sectores.get("rotacion_defensiva"):
            print(f"     ⚠️  ROTACIÓN DEFENSIVA (XLU supera a SPY)")
        if sectores.get("stress_financiero"):
            print(f"     ⚠️  FINANCIERO BAJO PRESIÓN")

    if tasas:
        spike_lbl = "⚠️ SPIKE" if tasas.get("spike") else "Normal"
        print(f"\n  📈 Tasas 10Y: {tasas.get('valor', 0):.3f}%  Δ5D:{tasas.get('cambio_5d', 0)*100:+.0f}bps  {spike_lbl}")

    if emergentes:
        e1 = emergentes.get("ret_1d", 0)
        e5 = emergentes.get("ret_5d", 0)
        stress_lbl = "⚠️ STRESS" if emergentes.get("stress") else "Normal"
        print(f"\n  🌎 Emergentes EEM:  Hoy:{e1:+.2f}%  5D:{e5:+.2f}%  {stress_lbl}")

    if razones:
        print(f"\n  📋 Factores (score total: {puntos}):")
        for r in razones:
            print(f"     • {r}")

    if alertas:
        print(f"\n  ⚠️  Alertas:")
        for a in alertas:
            print(f"     • {a}")

    print(f"\n{'═' * W}")
    print(f"  DECISIÓN: {decision}")
    print(f"  {consejo}")
    print(f"{'═' * W}")

    ventas  = {k: v for k, v in ajustadas.items() if v["accion"] == "VENDER" and v["delta_ajustado"] != 0}
    compras = {k: v for k, v in ajustadas.items() if v["accion"] == "COMPRAR" and v["delta_ajustado"] != 0}

    print(f"\n  {'SYM':<7} {'ORIG':>8} {'AJUST':>8}  {'PRIOR':<14} RAZÓN")
    print(f"  {'─'*7} {'─'*8} {'─'*8}  {'─'*14} {'─'*28}")

    print(f"\n  — VENTAS (ejecutar primero) —")
    for sym, o in sorted(ventas.items(), key=lambda x: x[1]["delta_original"]):
        mod = "✏️" if o["factor"] != 1.0 else "  "
        print(f"  {sym:<7} ${o['delta_original']:>7.0f} ${o['delta_ajustado']:>7.0f}  "
              f"{mod}{o['prioridad']:<13} {o['razon'][:38]}")

    print(f"\n  — COMPRAS (ejecutar después) —")
    for sym, o in sorted(compras.items(), key=lambda x: -abs(x[1]["delta_original"])):
        mod = "✏️" if o["factor"] != 1.0 else "  "
        print(f"  {sym:<7} ${o['delta_original']:>7.0f} ${o['delta_ajustado']:>7.0f}  "
              f"{mod}{o['prioridad']:<13} {o['razon'][:38]}")

    tv  = sum(abs(o["delta_ajustado"]) for o in ventas.values())
    tc  = sum(o["delta_ajustado"] for o in compras.values())
    net = cash + tv - tc
    print(f"\n  💰 Cash: ${cash:.2f} + ventas ${tv:.2f} - compras ${tc:.2f} = ${net:.2f} "
          f"{'✅' if net >= 0 else '⚠️ DÉFICIT'}")
    print("═" * W)

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    ap = sys.argv[1] if len(sys.argv) > 1 else "alpaca_data.json"
    mp = sys.argv[2] if len(sys.argv) > 2 else "markowitz_output.json"

    alpaca, markowitz = cargar_datos(ap, mp)
    ordenes  = extraer_ordenes(markowitz)
    symbols  = alpaca["symbols"]
    cash     = alpaca["cash"]

    prices             = get_market_data(symbols)
    vix                = analizar_vix(prices)
    mercado            = analizar_mercado(prices)
    energia            = analizar_energia(prices)
    refugios, risk_off = analizar_refugios(prices)
    credito            = analizar_credito(prices)
    sectores           = analizar_sectores(prices)
    tasas              = analizar_tasas(prices)
    emergentes         = analizar_emergentes(prices)

    decision, consejo, code, razones, puntos, detalle = semaforo_principal(
        vix, mercado, risk_off,
        credito=credito, sectores=sectores, tasas=tasas, emergentes=emergentes,
    )
    ajustadas, alertas = ajustar_ordenes(
        ordenes, mercado, energia, vix, risk_off, code,
        credito=credito, sectores=sectores,
    )

    imprimir_reporte(vix, mercado, energia, refugios, risk_off,
                     credito, sectores, tasas, emergentes,
                     decision, consejo, razones, puntos, detalle,
                     ajustadas, alertas, cash)

    # Guardar CSV ajustado
    rows = []
    for sym, o in ajustadas.items():
        if o["accion"] != "MANTENER":
            rows.append({"Símbolo": sym, **o})
    if rows:
        import pandas as pd
        fname = f"ordenes_ajustadas_{NOW_ARG.strftime('%Y%m%d_%H%M')}.csv"
        pd.DataFrame(rows).to_csv(fname, index=False)
        print(f"\n  💾 {fname}")

    # Output JSON para asesor
    ventas_adj  = {k: v for k, v in ajustadas.items() if v["accion"] == "VENDER" and v["delta_ajustado"] != 0}
    compras_adj = {k: v for k, v in ajustadas.items() if v["accion"] == "COMPRAR" and v["delta_ajustado"] != 0}
    tv = sum(abs(o["delta_ajustado"]) for o in ventas_adj.values())
    tc = sum(o["delta_ajustado"] for o in compras_adj.values())

    output = {
        "generated_at": NOW_ARG.isoformat(),
        "hora_arg":     NOW_ARG.strftime("%A %d/%m/%Y %H:%M"),
        "hora_ny":      NOW_ET.strftime("%A %d/%m/%Y %H:%M ET"),
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
    with open("semaforo_output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"  💾 semaforo_output.json")
    print(f"  ▶  Siguiente: python asesor_financiero.py")


if __name__ == "__main__":
    main()
