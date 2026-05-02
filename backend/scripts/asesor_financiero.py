"""
=============================================================
  SCRIPT 4/4 — ASESOR FINANCIERO
  asesor_financiero.py
=============================================================
Lee alpaca_data.json + markowitz_output.json + semaforo_output.json
y genera reporte_asesor_YYYYMM.md con análisis consolidado.

USO:
    python asesor_financiero.py

SALIDA:
    reporte_asesor_YYYYMM.md
"""

import json, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ_ARG     = ZoneInfo("America/Argentina/Buenos_Aires")
NOW        = datetime.now(TZ_ARG)

VIX_NORMAL  = 20
VIX_ALERTA  = 25
VIX_PELIGRO = 30

# ─────────────────────────────────────────────
#  CARGA
# ─────────────────────────────────────────────

def load(path, label):
    if not Path(path).exists():
        print(f"❌ Falta {path} — ejecutá el script {label} primero")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def pnl_emoji(v):
    return "🟢" if v >= 0 else "🔴"

def sharpe_label(s):
    if s >= 0.7:  return "✅ Excelente"
    if s >= 0.4:  return "🟡 Aceptable"
    if s >= 0.0:  return "🟠 Mediocre"
    return "🔴 Negativo"

def trend_short(t):
    if "ALCISTA" in t: return "↑"
    if "BAJISTA" in t: return "↓"
    return "→"

def fmt_usd(v):
    return f"${v:,.2f}"

def fmt_pct(v, plus=True):
    return f"{'+' if plus and v>0 else ''}{v:.1f}%"

# ─────────────────────────────────────────────
#  GENERADOR DE REPORTE
# ─────────────────────────────────────────────

def generar_reporte(alpaca, markowitz, semaforo):
    h      = alpaca["header"]
    period = h.get("period", "?")
    name   = h.get("name", "?")
    acct   = h.get("account_no", "?")
    total  = alpaca["total_value"]
    cash   = alpaca["cash"]

    mk_primary = markowitz.get("primary_strategy", "?")
    mk_opt     = markowitz.get("optimal_portfolios", {})
    mk_orders  = markowitz.get("orders", [])
    mk_risk    = markowitz.get("risk_individual", [])
    mk_cash    = markowitz.get("cash_flow", {})
    mk_sector  = markowitz.get("sector_concentration", {})

    sem      = semaforo.get("semaforo", {})
    sem_code = sem.get("code", "?")
    vix      = semaforo.get("vix", {})
    mercado  = semaforo.get("mercado", {})
    energia  = semaforo.get("energia", {})
    refugios = semaforo.get("refugios", {})
    risk_off = semaforo.get("risk_off", False)
    alertas  = semaforo.get("alertas", [])
    ordenes_adj = semaforo.get("ordenes_ajustadas", {})
    sem_cash = semaforo.get("cash_flow", {})

    lines = []
    a = lines.append

    # ── HEADER ───────────────────────────────
    a(f"# 📊 Reporte de Portafolio — {period}")
    a(f"**{name}** | Cuenta `{acct}` | Generado: {NOW.strftime('%d/%m/%Y %H:%M')} ARG\n")
    a("---\n")

    # ── 1. SNAPSHOT ──────────────────────────
    a("## 1. Snapshot")
    a(f"| | |")
    a(f"|---|---|")
    a(f"| Valor total | **{fmt_usd(total)}** |")
    a(f"| Cash disponible | {fmt_usd(cash)} |")
    a(f"| Posiciones | {len(alpaca['holdings'])} |")

    cs = alpaca.get("cash_summary", {})
    if cs:
        a(f"| Depósitos período | {fmt_usd(cs.get('additions',{}).get('period',0))} |")
        a(f"| P&L realizado (neto) | {fmt_usd(alpaca.get('realized_pnl',{}).get('short_term',{}).get('net',{}).get('period',0))} |")
    inc = alpaca.get("income", {})
    if inc.get("dividend"):
        a(f"| Dividendos cobrados | {fmt_usd(inc['dividend'].get('period',0))} |")
    a("")

    # ── 2. HOLDINGS ──────────────────────────
    a("## 2. Holdings")
    a("| Sym | Valor | Peso | P&L$ | P&L% | Tendencia |")
    a("|---|---|---|---|---|---|")

    holdings = alpaca.get("holdings", {})
    # buscar tendencia desde markowitz risk si está disponible
    risk_map = {}
    for r in mk_risk:
        sym = r.get("Símbolo","")
        risk_map[sym] = r

    for sym, h in sorted(holdings.items(), key=lambda x: -x[1]["market_value"]):
        pnl  = h["unrealized_pnl"]
        ppct = h["pnl_pct"]
        e    = pnl_emoji(pnl)
        a(f"| {e} **{sym}** | {fmt_usd(h['market_value'])} | {h['weight']:.1f}% "
          f"| {fmt_usd(pnl)} | {fmt_pct(ppct)} | — |")
    a("")

    # ── 3. RIESGO INDIVIDUAL ─────────────────
    a("## 3. Riesgo Individual")
    a("| Sym | Ret/año | Vol | Sharpe | VaR95 | Calidad |")
    a("|---|---|---|---|---|---|")

    for r in sorted(mk_risk, key=lambda x: -x.get("Sharpe", 0)):
        sym = r.get("Símbolo","")
        sh  = r.get("Sharpe", 0)
        a(f"| **{sym}** | {fmt_pct(r.get('Ret Anual%',0))} "
          f"| {r.get('Vol Anual%',0):.0f}% "
          f"| {sh:.2f} {sharpe_label(sh).split()[0]} "
          f"| {r.get('VaR 95% día',0):.1f}% "
          f"| {sharpe_label(sh)} |")
    a("")

    # ── 4. OPTIMIZACIÓN ──────────────────────
    a("## 4. Optimización Markowitz")
    a(f"Lookback: 2020–{NOW.year} | Min: 2% | Max: 12% | RF: {markowitz.get('risk_free', 4.25)}%\n")
    a("| Portafolio | Ret/año | Vol | Sharpe |")
    a("|---|---|---|---|")

    for key, p in mk_opt.items():
        star = " ⭐" if key == mk_primary else ""
        a(f"| {p['label']}{star} | {fmt_pct(p['return'])} | {p['vol']:.1f}% | **{p['sharpe']:.3f}** |")
    a("")

    # Top pesos del portafolio primario
    if mk_primary in mk_opt:
        pw = mk_opt[mk_primary].get("weights", {})
        top = sorted(pw.items(), key=lambda x: -x[1])[:8]
        a(f"**Pesos óptimos ({mk_primary}):**\n")
        a("| Sym | Peso obj | Peso actual |")
        a("|---|---|---|")
        for sym, w in top:
            curr = holdings.get(sym, {}).get("weight", 0)
            delta_w = w - curr
            arrow = "↑" if delta_w > 1 else ("↓" if delta_w < -1 else "→")
            a(f"| {sym} | {w:.1f}% | {curr:.1f}% {arrow} |")
    a("")

    # ── 5. ÓRDENES ───────────────────────────
    a("## 5. Órdenes de Rebalanceo")
    a(f"Estrategia: **{mk_primary}**\n")

    ventas  = [o for o in mk_orders if o.get("Acción") == "VENDER"]
    compras = [o for o in mk_orders if o.get("Acción") == "COMPRAR"]

    if ventas:
        a("**Ventas (ejecutar primero):**\n")
        a("| Sym | Δ$ | Δ Acciones | Peso → Obj |")
        a("|---|---|---|---|")
        for o in sorted(ventas, key=lambda x: x.get("Δ Dólares ($)", 0)):
            sym = o.get("Símbolo","")
            adj = ordenes_adj.get(sym, {})
            mod = f" ✏️→{fmt_usd(adj.get('delta_ajustado',o.get('Δ Dólares ($)',0)))}" if adj.get("factor",1)!=1 else ""
            a(f"| **{sym}** | {fmt_usd(o.get('Δ Dólares ($)',0))}{mod} "
              f"| {o.get('Δ Acciones',0):.3f} "
              f"| {o.get('Peso Actual (%)',0):.1f}%→{o.get('Peso Objetivo (%)',0):.1f}% |")

    if compras:
        a("\n**Compras (ejecutar después):**\n")
        a("| Sym | Δ$ | Δ Acciones | Peso → Obj |")
        a("|---|---|---|---|")
        for o in sorted(compras, key=lambda x: -x.get("Δ Dólares ($)", 0)):
            sym = o.get("Símbolo","")
            adj = ordenes_adj.get(sym, {})
            mod = f" ✏️→{fmt_usd(adj.get('delta_ajustado',o.get('Δ Dólares ($)',0)))}" if adj.get("factor",1)!=1 else ""
            a(f"| **{sym}** | {fmt_usd(o.get('Δ Dólares ($)',0))}{mod} "
              f"| {o.get('Δ Acciones',0):.3f} "
              f"| {o.get('Peso Actual (%)',0):.1f}%→{o.get('Peso Objetivo (%)',0):.1f}% |")

    a(f"\n| | |")
    a(f"|---|---|")
    a(f"| Cash inicial | {fmt_usd(mk_cash.get('sell',0)+cash-mk_cash.get('buy',0))} |")
    a(f"| Total a vender | +{fmt_usd(mk_cash.get('sell',0))} |")
    a(f"| Total a comprar | -{fmt_usd(mk_cash.get('buy',0))} |")
    net_m = mk_cash.get("net", 0)
    a(f"| Cash resultante | **{fmt_usd(net_m)}** {'✅' if net_m >= 0 else '⚠️'} |")
    a("")

    # ── 6. SEMÁFORO ──────────────────────────
    a("## 6. Semáforo de Mercado")
    sem_icons = {"GO":"🟢","PARTIAL":"🟡","WAIT":"🟠","ABORT":"🔴"}
    a(f"**{sem_icons.get(sem_code,'🔵')} {sem.get('decision','?')}**\n")
    a(f"> {sem.get('consejo','')}\n")

    a(f"| Indicador | Valor | Estado |")
    a(f"|---|---|---|")
    a(f"| VIX | {vix.get('valor','?')} ({vix.get('cambio',0):+.1f}) | {vix.get('semaforo','')} {vix.get('nivel','')} |")
    for t, d in mercado.items():
        e = "🟢" if d["ret_1d"] >= 0 else "🔴"
        a(f"| {t} | {fmt_pct(d['ret_1d'])} hoy / {fmt_pct(d['ret_5d'])} 5D | {e} {'⚠️ bajo SMA10' if d.get('bajo_sma10') else '✅'} |")
    a(f"| Risk-Off | {'ACTIVO ⚠️' if risk_off else 'No'} | {'Refugios subiendo' if risk_off else 'Normal'} |")
    a("")

    a("**Energía (contexto geopolítico):**\n")
    a("| Sym | Hoy | 5D |")
    a("|---|---|---|")
    for t, d in energia.items():
        e = "🟢" if d["ret_5d"] > 1 else ("🔴" if d["ret_5d"] < -1 else "🟡")
        a(f"| {e} {t} | {fmt_pct(d['ret_1d'])} | {fmt_pct(d['ret_5d'])} |")
    a("")

    if alertas:
        a("**Alertas:**\n")
        for al in alertas:
            a(f"- {al}")
        a("")

    # ── 7. CONCENTRACIÓN SECTORIAL ───────────
    a("## 7. Concentración Sectorial")
    a("| Sector | Peso actual | Peso óptimo | Estado |")
    a("|---|---|---|---|")

    energy_curr = sum(holdings.get(s,{}).get("weight",0) for s in ["CVX","XOM"])
    tech_curr   = sum(holdings.get(s,{}).get("weight",0) for s in ["AAPL","MSFT","NVDA","ADBE","GOOG","MU"])
    div_curr    = sum(holdings.get(s,{}).get("weight",0) for s in ["KO","SCHD","VZ"])
    emerg_curr  = sum(holdings.get(s,{}).get("weight",0) for s in ["BMA","YPF","NU"])

    energy_opt = mk_sector.get("energy_pct", 0)
    tech_opt   = mk_sector.get("tech_pct", 0)

    a(f"| Energía (CVX+XOM) | {energy_curr:.1f}% | {energy_opt:.1f}% | {'⚠️ >20%' if energy_curr>20 else '✅'} |")
    a(f"| Tech (6 activos)  | {tech_curr:.1f}% | {tech_opt:.1f}% | {'⚠️ >40%' if tech_opt>40 else '✅'} |")
    a(f"| Dividendos (KO+SCHD+VZ) | {div_curr:.1f}% | — | {'✅' if div_curr>10 else '🟡 bajo'} |")
    a(f"| Emergente ARG (BMA+YPF+NU) | {emerg_curr:.1f}% | — | {'⚠️ >10%' if emerg_curr>10 else '✅'} |")
    a("")

    # ── 8. DIVIDENDOS ────────────────────────
    divs = alpaca.get("dividends", [])
    if divs:
        a("## 8. Dividendos del Período")
        a("| Fecha | Sym | Monto | Tipo |")
        a("|---|---|---|---|")
        for d in divs:
            tipo = "💰 Dividendo" if "Dividends" in d.get("type","") else "🏦 Retención"
            a(f"| {d.get('date','')} | {d.get('symbol','')} | {fmt_usd(d.get('amount',0))} | {tipo} |")
        a("")

    # ── 9. TESIS DE ASESOR ───────────────────
    a("## 9. Tesis del Asesor\n")

    # Peores posiciones
    worst = sorted(holdings.items(), key=lambda x: x[1]["unrealized_pnl"])[:3]
    best  = sorted(holdings.items(), key=lambda x: -x[1]["unrealized_pnl"])[:3]

    a("**Top 3 posiciones a revisar:**\n")
    for sym, h in worst:
        r = risk_map.get(sym, {})
        sh = r.get("Sharpe", 0)
        a(f"- **{sym}** P&L {fmt_pct(h['pnl_pct'])} | Sharpe {sh:.2f} {sharpe_label(sh).split()[0]} "
          f"| Vol {r.get('Vol Anual%',0):.0f}% — "
          + ("Vender o reducir fuertemente." if sh < 0.2 else "Reducir según plan."))

    a("\n**Top 3 posiciones a mantener/aumentar:**\n")
    for sym, h in best:
        r = risk_map.get(sym, {})
        sh = r.get("Sharpe", 0)
        a(f"- **{sym}** P&L {fmt_pct(h['pnl_pct'])} | Sharpe {sh:.2f} {sharpe_label(sh).split()[0]} "
          f"| Ret/año {r.get('Ret Anual%',0):+.0f}% — Posición justificada, considerar aumentar.")

    a("\n**Contexto macro:**\n")
    spy_5d = mercado.get("SPY", {}).get("ret_5d", 0)
    xle_5d = energia.get("XLE", {}).get("ret_5d", 0)
    a(f"- SPY 5D: {fmt_pct(spy_5d)} | XLE 5D: {fmt_pct(xle_5d)} | VIX: {vix.get('valor','?')}")
    if risk_off:
        a("- ⚠️ **Risk-off activo**: reducir exposición a activos volátiles, aumentar defensivos (KO, SCHD, GLD).")
    if xle_5d > 3:
        a(f"- 🛢️ **Energía en rally +{xle_5d:.1f}%**: no liquidar CVX/XOM apresuradamente. Esperar consolidación.")
    if vix.get("valor", 0) > VIX_ALERTA:
        a(f"- ⚠️ **VIX elevado ({vix.get('valor','?')})**: aplazar compras en NVDA, MU, GOOG. Ejecutar solo ventas defensivas.")

    a(f"\n**Acción recomendada para hoy:**\n")
    actions = {
        "GO":      "✅ Ejecutar rebalanceo completo. Ventas primero, compras entre 10:00–11:30 AM ET.",
        "PARTIAL": "🟡 Ejecutar ventas + compras defensivas (KO, SCHD). Posponer NVDA/MU/GOOG 1-2 días.",
        "WAIT":    "🟠 Solo ejecutar ADBE, NU, VZ (Sharpe negativo). Congelar compras hasta que VIX baje.",
        "ABORT":   "🔴 No operar. Esperar estabilización del mercado (VIX < 25) antes de cualquier movimiento.",
    }
    a(actions.get(sem_code, "Ver semáforo."))
    a("")

    # ── FOOTER ───────────────────────────────
    a("---")
    a(f"*Generado: {NOW.strftime('%d/%m/%Y %H:%M')} ARG | "
      f"Scripts: parse_alpaca_pdf → rebalanceo_markowitz → semaforo_mercado → asesor_financiero*\n")
    a("*Este reporte es informativo. No constituye asesoramiento financiero.*")

    return "\n".join(lines)

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  📋  ASESOR FINANCIERO — CONSOLIDANDO REPORTE")
    print("=" * 55)

    alpaca    = load("alpaca_data.json",       "1 (parse_alpaca_pdf.py)")
    markowitz = load("markowitz_output.json",  "2 (rebalanceo_markowitz.py)")
    semaforo  = load("semaforo_output.json",   "3 (semaforo_mercado.py)")

    print(f"  ✅ Período:   {alpaca['header'].get('period','?')}")
    print(f"  ✅ Total:     ${alpaca['total_value']:,.2f}")
    print(f"  ✅ Semáforo:  {semaforo.get('semaforo',{}).get('decision','?')}")
    print(f"  ✅ Estrategia:{markowitz.get('primary_strategy','?')}")

    reporte = generar_reporte(alpaca, markowitz, semaforo)

    period_clean = alpaca["header"].get("period","").replace(" - ","_").replace(" ","")
    fname = f"reporte_asesor_{period_clean}_{NOW.strftime('%Y%m%d')}.md"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(reporte)

    print(f"\n  💾 Reporte guardado: {fname}")
    print(f"  📏 {len(reporte.splitlines())} líneas | {len(reporte):,} caracteres")
    print("=" * 55)

if __name__ == "__main__":
    main()