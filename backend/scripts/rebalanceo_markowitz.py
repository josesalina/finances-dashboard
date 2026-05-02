"""
=============================================================
  SCRIPT 2/4 — REBALANCEO DE MARKOWITZ
  rebalanceo_markowitz.py
=============================================================
Lee alpaca_data.json generado por parse_alpaca_pdf.py
y calcula el portafolio óptimo por máximo Sharpe Ratio.

USO:
    python rebalanceo_markowitz.py
    python3 rebalanceo_markowitz.py mi_carpeta/alpaca_data.json

SALIDA:
    markowitz_output.json   ← para asesor_financiero.py
    rebalanceo_ordenes.csv
    riesgo_individual.csv
    markowitz_rebalanceo.png
"""

import warnings, sys, json
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy.optimize import minimize
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ_ARG    = ZoneInfo("America/Argentina/Buenos_Aires")
NOW_ARG   = datetime.now(TZ_ARG)

RISK_FREE  = 0.0425
LOOKBACK   = "2020-01-01"
MIN_WEIGHT = 0.02
MAX_WEIGHT = 0.12

# ─────────────────────────────────────────────
#  CARGA DE DATOS
# ─────────────────────────────────────────────

def cargar_alpaca_data(json_path="alpaca_data.json") -> dict:
    path = Path(json_path)
    if not path.exists():
        print(f"❌ No se encontró {json_path}")
        print("   Ejecutá primero: python parse_alpaca_pdf.py account_statement.pdf")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    print(f"✅ Datos cargados: {data['header'].get('period','?')} "
          f"| {len(data['holdings'])} posiciones "
          f"| Total: ${data['total_value']:,.2f}")
    return data

def construir_portfolio_dict(alpaca_data: dict) -> dict:
    """Convierte alpaca_data.holdings al formato que usan las funciones de optimización."""
    portfolio = {}
    for sym, h in alpaca_data["holdings"].items():
        portfolio[sym] = {
            "qty":   h["qty"],
            "cost":  h["cost_price"],
            "value": h["market_value"],
        }
    return portfolio

# ─────────────────────────────────────────────
#  DESCARGA DE PRECIOS
# ─────────────────────────────────────────────

def download_data(symbols, start, end):
    print(f"\n📥 Descargando precios ({start} → {end})...")
    end_date = datetime.now(TZ_ARG).strftime("%Y-%m-%d")
    raw = yf.download(symbols, start=start, end=end_date,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"]
    else:
        prices = raw[["Close"]]
        prices.columns = symbols
    prices.dropna(how="all", inplace=True)
    prices.ffill(inplace=True)
    prices.bfill(inplace=True)
    available = [s for s in symbols if s in prices.columns]
    print(f"  ✅ {len(prices)} días | {len(available)} activos")
    return prices[available]

# ─────────────────────────────────────────────
#  OPTIMIZACIÓN
# ─────────────────────────────────────────────

def portfolio_performance(weights, mean_returns, cov_matrix, rf=RISK_FREE):
    w   = np.array(weights)
    ret = np.sum(mean_returns * w) * 252
    vol = np.sqrt(w @ cov_matrix @ w) * np.sqrt(252)
    sharpe = (ret - rf) / vol if vol > 0 else 0
    return ret, vol, sharpe

def neg_sharpe(weights, mean_returns, cov_matrix, rf=RISK_FREE):
    return -portfolio_performance(weights, mean_returns, cov_matrix, rf)[2]

def min_volatility(weights, mean_returns, cov_matrix, rf=RISK_FREE):
    return portfolio_performance(weights, mean_returns, cov_matrix, rf)[1]

def optimize_portfolio(log_returns, symbols):
    n           = len(symbols)
    mean_ret    = log_returns.mean()
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    rng         = np.random.default_rng(42)

    try:
        from sklearn.covariance import LedoitWolf
        cov_matrix = pd.DataFrame(
            LedoitWolf().fit(log_returns.dropna()).covariance_,
            index=log_returns.columns, columns=log_returns.columns)
        print("  ✅ Covarianza Ledoit-Wolf aplicada")
    except ImportError:
        cov_matrix = log_returns.cov()

    results = {}

    def _optimize(obj_fn, bounds, label, n_starts=20):
        best_sol, best_val = None, np.inf
        for _ in range(n_starts):
            w0  = rng.dirichlet(np.ones(n))
            w0  = np.clip(w0, bounds[0][0], bounds[0][1])
            w0 /= w0.sum()
            sol = minimize(obj_fn, w0, args=(mean_ret, cov_matrix),
                           method="SLSQP", bounds=bounds,
                           constraints=constraints,
                           options={"maxiter": 2000, "ftol": 1e-14})
            if sol.success and sol.fun < best_val:
                best_val, best_sol = sol.fun, sol
        if best_sol:
            w = np.clip(best_sol.x, bounds[0][0], bounds[0][1])
            w /= w.sum()
            r, v, s = portfolio_performance(w, mean_ret, cov_matrix)
            results[label] = {"weights": dict(zip(symbols, w)),
                              "return": r, "vol": v, "sharpe": s,
                              "label": label}
            print(f"  ✅ {label:30s} Ret:{r*100:.1f}% Vol:{v*100:.1f}% Sharpe:{s:.3f}")
        else:
            print(f"  ⚠️  {label} no convergió")

    print("\n🔬 Optimizando portafolios...")
    _optimize(neg_sharpe,    tuple((MIN_WEIGHT, MAX_WEIGHT) for _ in range(n)),
              "Máximo Sharpe")
    _optimize(min_volatility,tuple((MIN_WEIGHT, MAX_WEIGHT) for _ in range(n)),
              "Mínima Volatilidad")
    _optimize(neg_sharpe,    tuple((MIN_WEIGHT, 0.12) for _ in range(n)),
              "Conservador (max 12%)")

    return results, mean_ret, cov_matrix

# ─────────────────────────────────────────────
#  ÓRDENES
# ─────────────────────────────────────────────

def generate_orders(optimal_weights, prices_last, portfolio, cash,
                    strategy="Conservador (max 12%)"):
    current_total = sum(v["value"] for v in portfolio.values()) + cash
    weights       = optimal_weights[strategy]["weights"]
    orders        = []

    for sym, w_opt in weights.items():
        current_val  = portfolio.get(sym, {}).get("value", 0.0)
        target_val   = current_total * w_opt
        delta_val    = target_val - current_val
        price        = prices_last.get(sym, 0)
        if price <= 0:
            continue
        delta_shares = delta_val / price
        action = "COMPRAR" if delta_val > 10 else ("VENDER" if delta_val < -10 else "MANTENER")
        orders.append({
            "Símbolo":           sym,
            "Acción":            action,
            "Precio ($)":        round(price, 2),
            "Valor Actual ($)":  round(current_val, 2),
            "Valor Objetivo ($)":round(target_val, 2),
            "Δ Dólares ($)":     round(delta_val, 2),
            "Δ Acciones":        round(delta_shares, 4),
            "Peso Actual (%)":   round(current_val / current_total * 100, 2),
            "Peso Objetivo (%)": round(w_opt * 100, 2),
        })

    df = pd.DataFrame(orders).set_index("Símbolo")
    df = df.sort_values("Δ Dólares ($)")
    total_buy  = df[df["Δ Dólares ($)"] > 10]["Δ Dólares ($)"].sum()
    total_sell = abs(df[df["Δ Dólares ($)"] < -10]["Δ Dólares ($)"].sum())
    net_cash   = total_sell + cash - total_buy
    return df, total_buy, total_sell, net_cash

# ─────────────────────────────────────────────
#  RIESGO INDIVIDUAL
# ─────────────────────────────────────────────

def risk_analysis(log_returns, portfolio):
    rows = []
    for sym in log_returns.columns:
        if sym not in portfolio:
            continue
        r    = log_returns[sym].dropna()
        ret  = r.mean() * 252
        vol  = r.std() * np.sqrt(252)
        shp  = (ret - RISK_FREE) / vol if vol > 0 else 0
        var  = np.percentile(r, 5) * 100
        cvar = r[r <= np.percentile(r, 5)].mean() * 100
        pos  = (r > 0).sum() / len(r) * 100
        cost = portfolio[sym]["cost"]
        curr = portfolio[sym]["value"] / portfolio[sym]["qty"] if portfolio[sym]["qty"] > 0 else 0
        pnl  = (curr / cost - 1) * 100 if cost > 0 else 0
        rows.append({
            "Símbolo":       sym,
            "Ret Anual%":    round(ret * 100, 1),
            "Vol Anual%":    round(vol * 100, 1),
            "Sharpe":        round(shp, 3),
            "VaR 95% día":   round(var, 2),
            "CVaR 95%":      round(cvar, 2),
            "Días+ (%)":     round(pos, 0),
            "P&L Real%":     round(pnl, 1),
        })
    return pd.DataFrame(rows).set_index("Símbolo")

# ─────────────────────────────────────────────
#  FRONTERA EFICIENTE
# ─────────────────────────────────────────────

def efficient_frontier(mean_ret, cov_matrix, n=6000):
    print(f"\n📐 Frontera eficiente ({n} simulaciones)...")
    n_assets = len(mean_ret)
    rets, vols, sharpes = [], [], []
    rng = np.random.default_rng(0)
    for _ in range(n):
        w = rng.random(n_assets); w /= w.sum()
        r, v, s = portfolio_performance(w, mean_ret, cov_matrix)
        rets.append(r * 100); vols.append(v * 100); sharpes.append(s)
    return np.array(vols), np.array(rets), np.array(sharpes)

# ─────────────────────────────────────────────
#  VISUALIZACIÓN
# ─────────────────────────────────────────────

def plot_all(frontier, optimal, orders_df, current_weights, portfolio):
    DARK, PANEL, BORDER, WHITE = "#0d1117", "#161b22", "#30363d", "#e6edf3"
    fig = plt.figure(figsize=(20, 14), facecolor=DARK)
    gs  = gridspec.GridSpec(2, 3, figure=fig, hspace=0.42, wspace=0.38)
    vols, rets, sharpes = frontier

    ax1 = fig.add_subplot(gs[0, :2])
    ax1.set_facecolor(PANEL)
    ax1.set_title("Frontera Eficiente de Markowitz", color=WHITE, fontsize=13, fontweight="bold")
    sc = ax1.scatter(vols, rets, c=sharpes, cmap="plasma", alpha=0.3, s=4)
    cb = plt.colorbar(sc, ax=ax1)
    cb.set_label("Sharpe", color=WHITE)
    cb.ax.yaxis.set_tick_params(color=WHITE)
    plt.setp(plt.getp(cb.ax.axes, "yticklabels"), color=WHITE)
    COLORS = {"Máximo Sharpe": "#ffd93d", "Mínima Volatilidad": "#6bceff",
               "Conservador (max 12%)": "#00d4aa"}
    for key, p in optimal.items():
        c = COLORS.get(key, "white")
        ax1.scatter(p["vol"] * 100, p["return"] * 100, marker="*", s=300,
                    color=c, zorder=5, label=f"{key} (S={p['sharpe']:.2f})")
    ax1.set_xlabel("Volatilidad (%)", color=WHITE)
    ax1.set_ylabel("Retorno (%)", color=WHITE)
    ax1.tick_params(colors=WHITE)
    ax1.legend(facecolor=PANEL, labelcolor=WHITE, fontsize=9)
    for sp in ax1.spines.values(): sp.set_edgecolor(BORDER)

    ax2 = fig.add_subplot(gs[0, 2])
    ax2.set_facecolor(PANEL)
    ax2.set_title("Pesos: Actual vs Conservador", color=WHITE, fontsize=10, fontweight="bold")
    syms = sorted(current_weights.keys())
    x    = np.arange(len(syms))
    wc   = [current_weights.get(s, 0) for s in syms]
    wo   = [optimal.get("Conservador (max 12%)", {}).get("weights", {}).get(s, 0) * 100 for s in syms]
    ax2.barh(x + 0.2, wc, 0.38, color="#6bceff", alpha=0.8, label="Actual")
    ax2.barh(x - 0.2, wo, 0.38, color="#00d4aa", alpha=0.8, label="Óptimo")
    ax2.set_yticks(x); ax2.set_yticklabels(syms, fontsize=7, color=WHITE)
    ax2.set_xlabel("Peso (%)", color=WHITE, fontsize=9)
    ax2.tick_params(colors=WHITE, labelsize=8)
    ax2.legend(facecolor=PANEL, labelcolor=WHITE, fontsize=8)
    for sp in ax2.spines.values(): sp.set_edgecolor(BORDER)

    ax3 = fig.add_subplot(gs[1, :2])
    ax3.set_facecolor(PANEL)
    ax3.set_title("Δ Dólares por Orden (Conservador)", color=WHITE, fontsize=11, fontweight="bold")
    op  = orders_df[orders_df["Acción"] != "MANTENER"].copy().sort_values("Δ Dólares ($)")
    clr = ["#ff6b6b" if v < 0 else "#00d4aa" for v in op["Δ Dólares ($)"]]
    ax3.barh(op.index, op["Δ Dólares ($)"], color=clr)
    ax3.axvline(0, color=WHITE, lw=0.8, alpha=0.5)
    ax3.set_xlabel("Δ ($) — Rojo=Vender | Verde=Comprar", color=WHITE)
    ax3.tick_params(colors=WHITE)
    for sp in ax3.spines.values(): sp.set_edgecolor(BORDER)

    ax4 = fig.add_subplot(gs[1, 2])
    ax4.set_facecolor(PANEL); ax4.axis("off")
    ax4.set_title("Portafolios Óptimos", color=WHITE, fontsize=11, fontweight="bold")
    rows = [[p["label"][:22], f"{p['return']*100:.1f}%",
             f"{p['vol']*100:.1f}%", f"{p['sharpe']:.3f}"]
            for p in optimal.values()]
    tbl  = ax4.table(cellText=rows, colLabels=["Estrategia","Ret%","Vol%","Sharpe"],
                     cellLoc="center", loc="center")
    tbl.auto_set_font_size(False); tbl.set_fontsize(8)
    for (r, c), cell in tbl.get_celld().items():
        cell.set_facecolor("#21262d" if r > 0 else "#388bfd")
        cell.set_text_props(color=WHITE); cell.set_edgecolor(BORDER)

    fig.suptitle(f"Optimización Markowitz — Alpaca #{''} | "
                 f"{NOW_ARG.strftime('%d/%m/%Y %H:%M')} (ARG)",
                 color=WHITE, fontsize=12, fontweight="bold", y=0.99)
    plt.savefig("markowitz_rebalanceo.png", dpi=150, bbox_inches="tight", facecolor=DARK)
    plt.close()
    print("  ✅ markowitz_rebalanceo.png")

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    json_path = sys.argv[1] if len(sys.argv) > 1 else "alpaca_data.json"
    alpaca    = cargar_alpaca_data(json_path)
    portfolio = construir_portfolio_dict(alpaca)
    symbols   = alpaca["symbols"]
    cash      = alpaca["cash"]
    total_val = alpaca["total_value"]
    current_w = {s: alpaca["holdings"][s]["weight"] for s in symbols}

    print(f"\n  Hora Argentina: {NOW_ARG.strftime('%A %d/%m/%Y %H:%M')}")

    prices    = download_data(symbols, LOOKBACK, "")
    available = [s for s in symbols if s in prices.columns]
    prices    = prices[available]
    log_ret   = np.log(prices / prices.shift(1)).dropna()
    last_p    = prices.iloc[-1].to_dict()

    # Riesgo individual
    risk_df = risk_analysis(log_ret, portfolio)
    print("\n📉 Riesgo individual:\n" + risk_df.to_string())
    risk_df.to_csv("riesgo_individual.csv")

    # Optimización
    optimal, mean_ret, cov = optimize_portfolio(log_ret, available)

    # Frontera
    frontier = efficient_frontier(mean_ret, cov)

    # Órdenes — estrategia conservadora como principal
    PRIMARY = "Conservador (max 12%)"
    if PRIMARY not in optimal:
        PRIMARY = list(optimal.keys())[0]

    orders_df, buy, sell, net = generate_orders(optimal, last_p, portfolio, cash, PRIMARY)
    orders_df.to_csv("rebalanceo_ordenes.csv")

    # Sector check
    energy = sum(optimal[PRIMARY]["weights"].get(s, 0) for s in ["CVX", "XOM"]) * 100
    tech   = sum(optimal[PRIMARY]["weights"].get(s, 0)
                 for s in ["AAPL","MSFT","NVDA","ADBE","GOOG","MU"]) * 100

    print(f"\n  Energía: {energy:.1f}% {'⚠️' if energy > 20 else '✅'}")
    print(f"  Tech:    {tech:.1f}% {'⚠️' if tech > 40 else '✅'}")
    print(f"\n  Cash disponible:  ${cash:.2f}")
    print(f"  Total a vender:  +${sell:.2f}")
    print(f"  Total a comprar: -${buy:.2f}")
    print(f"  Cash resultante:  ${net:.2f} {'✅' if net >= 0 else '⚠️ DÉFICIT'}")

    # Gráfico
    plot_all(frontier, optimal, orders_df, current_w, portfolio)

    # ── OUTPUT JSON para asesor_financiero.py ──
    output = {
        "generated_at": NOW_ARG.isoformat(),
        "period":        alpaca["header"].get("period"),
        "total_value":   total_val,
        "cash":          cash,
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
        "orders": orders_df.reset_index().to_dict(orient="records"),
        "cash_flow": {"sell": round(sell, 2), "buy": round(buy, 2), "net": round(net, 2)},
        "sector_concentration": {"energy_pct": round(energy, 1), "tech_pct": round(tech, 1)},
        "risk_individual": risk_df.reset_index().to_dict(orient="records"),
        "current_weights": current_w,
    }
    with open("markowitz_output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print("\n  💾 markowitz_output.json")
    print("  💾 rebalanceo_ordenes.csv")
    print("  💾 riesgo_individual.csv")
    print("  ▶  Siguiente: python semaforo_mercado.py")

if __name__ == "__main__":
    main()
