#!/usr/bin/env python3
"""
distribuir_inversion.py
=======================
Dado un monto a invertir hoy, calcula cómo distribuirlo en la cartera
siguiendo los pesos objetivo de Markowitz y el semáforo de mercado.

Uso:
    python distribuir_inversion.py 500
    python distribuir_inversion.py 500 --modo agresivo
    python distribuir_inversion.py 500 --ignorar-semaforo
"""

import sys
import argparse
from dataclasses import dataclass, field
from typing import Optional

# ─────────────────────────────────────────────
#  CONFIGURACIÓN DE CARTERA (desde el reporte)
# ─────────────────────────────────────────────

@dataclass
class Activo:
    sym: str
    peso_actual: float       # % actual en cartera
    peso_objetivo: float     # % objetivo Markowitz conservador
    valor_actual: float      # USD en cartera hoy
    precio_actual: float     # USD por acción (estimado)
    sharpe: float
    semaforo: str            # "verde", "naranja", "rojo"
    sector: str
    nota: str = ""

# Fuente: reporte 07/03/2026 — estrategia Conservador (max 12%)
# Precios estimados a partir de valor_actual / acciones implícitas en el reporte
CARTERA: list[Activo] = [
    # En el portafolio óptimo (8 activos con peso > 2% objetivo)
    Activo("AAPL",  11.2, 12.0,  695.39, 213.00, 0.52, "naranja", "Tech",       "Cerca del objetivo"),
    Activo("GOOG",   6.2, 12.0,  384.40, 318.00, 0.62, "naranja", "Tech",       "Subponderado, mercado adverso"),
    Activo("KO",     5.5, 12.0,  341.97,  65.50, 0.21, "naranja", "Dividendos", "Subponderado, mercado adverso"),
    Activo("MU",     8.7, 12.0,  542.09, 992.00, 0.53, "naranja", "Tech",       "Subponderado, mercado adverso"),
    Activo("NVDA",   3.0, 12.0,  188.95,  91.00, 0.97, "naranja", "Tech",       "Muy subponderado, mercado adverso"),
    Activo("XOM",    2.6, 12.0,  163.87,  42.67, 0.39, "naranja", "Energía",    "Muy subponderado, mercado adverso"),
    Activo("SCHD",   5.2,  8.0,  321.45,  28.76, 0.36, "naranja", "Dividendos", "Subponderado, mercado adverso"),
    Activo("ADBE",   4.1,  2.0,  254.53, 363.62, -0.18,"rojo",    "Tech",       "Sharpe negativo — VENDER"),
    # Activos sin peso objetivo explícito (mantener en 2% mínimo o reducir)
    Activo("CVX",   12.2,  2.0,  758.09, 227.10, 0.22, "verde",   "Energía",    "Sobre peso objetivo — reducir"),
    Activo("SPY",   11.1,  2.0,  686.55, 820.33, 0.44, "rojo",    "Index",      "Sobre peso objetivo — reducir"),
    Activo("VOOG",   7.0,  2.0,  433.48, 596.53, 0.45, "rojo",    "Index",      "Sobre peso objetivo — reducir"),
    Activo("BMA",    4.6,  2.0,  286.63, 124.13, 0.18, "rojo",    "ARG",        "P&L -18.6% — VENDER"),
    Activo("YPF",    4.1,  2.0,  252.85,  72.44, 0.25, "rojo",    "ARG",        "Sobre peso objetivo"),
    Activo("NU",     2.7,  2.0,  169.17,  54.69, 0.03, "rojo",    "ARG",        "Sharpe casi 0 — VENDER"),
    Activo("XLE",    0.0,  0.0,    0.00,   0.00, 0.00, "verde",   "Energía",    "ETF sector energía"),
    Activo("VZ",     2.6,  2.0,  163.80,  42.87, -0.06,"rojo",    "Dividendos", "Sharpe negativo — VENDER"),
    Activo("IWM",    1.7,  2.0,  104.82, 210.35, 0.14, "naranja", "Index",      "Cerca del objetivo"),
    Activo("MSFT",   2.1,  0.0,  127.92, 382.00, 0.40, "rojo",    "Tech",       "No en portafolio óptimo"),
]

VALOR_TOTAL_CARTERA = 6203.81  # USD total cartera

# Semáforo global del día
SEMAFORO_GLOBAL = "naranja"   # 🟠 ESPERAR
VIX_HOY = 29.49

# ─────────────────────────────────────────────
#  LÓGICA DE DISTRIBUCIÓN
# ─────────────────────────────────────────────

def calcular_distribucion(
    monto: float,
    modo: str = "conservador",   # "conservador" | "agresivo"
    ignorar_semaforo: bool = False,
) -> None:

    print()
    print("=" * 62)
    print("  💰  DISTRIBUCIÓN DE INVERSIÓN DIARIA")
    print("=" * 62)
    print(f"  Monto a invertir : ${monto:,.2f}")
    print(f"  Modo             : {modo.upper()}")
    print(f"  Semáforo global  : {'🟠 NARANJA — ESPERAR' if SEMAFORO_GLOBAL == 'naranja' else SEMAFORO_GLOBAL}")
    print(f"  VIX              : {VIX_HOY}")
    print(f"  Ignorar semáforo : {'Sí ⚠️' if ignorar_semaforo else 'No'}")
    print("=" * 62)

    # Filtrar activos elegibles para COMPRA
    candidatos = []
    excluidos = []

    for a in CARTERA:
        gap = a.peso_objetivo - a.peso_actual   # cuánto le falta para llegar al objetivo

        # Solo considerar activos que estén subponderados y tengan peso objetivo > 0
        if a.peso_objetivo <= 2.0 or gap <= 0:
            excluidos.append((a, f"No requiere compra (gap={gap:+.1f}%)"))
            continue

        # Filtro semáforo
        if not ignorar_semaforo and a.semaforo in ("naranja", "rojo"):
            if modo == "conservador":
                excluidos.append((a, f"Semáforo {a.semaforo} — omitido en modo conservador"))
                continue
            # En modo agresivo solo excluir rojo
            if modo == "agresivo" and a.semaforo == "rojo":
                excluidos.append((a, f"Semáforo rojo — siempre excluido"))
                continue

        # Filtro Sharpe negativo (nunca comprar)
        if a.sharpe < 0:
            excluidos.append((a, f"Sharpe negativo ({a.sharpe}) — nunca comprar"))
            continue

        candidatos.append((a, gap))

    if not candidatos:
        print()
        print("  ⚠️  No hay activos elegibles para compra hoy.")
        print()
        if SEMAFORO_GLOBAL == "naranja" and not ignorar_semaforo:
            print("  💡 El semáforo está en NARANJA. Opciones:")
            print("     • Esperar a que el VIX baje de 20")
            print("     • Usar --ignorar-semaforo para forzar la distribución")
            print("     • Usar --modo agresivo para incluir activos naranja")
        print()
        _mostrar_excluidos(excluidos)
        return

    # Distribuir proporcionalmente al gap (más gap → más dinero)
    total_gap = sum(g for _, g in candidatos)
    asignaciones = []

    for activo, gap in candidatos:
        proporcion = gap / total_gap
        monto_asignado = monto * proporcion
        acciones = monto_asignado / activo.precio_actual if activo.precio_actual > 0 else 0
        asignaciones.append({
            "activo": activo,
            "gap": gap,
            "proporcion": proporcion,
            "monto": monto_asignado,
            "acciones": acciones,
        })

    # Ordenar por monto descendente
    asignaciones.sort(key=lambda x: x["monto"], reverse=True)

    # ── Tabla de resultados ──
    print()
    print(f"  {'SYM':<6} {'Peso act':>8} {'Obj':>6} {'Gap':>6} {'%Dist':>7} {'USD':>9} {'Acciones':>9}  Sector")
    print("  " + "─" * 60)

    total_asignado = 0
    for row in asignaciones:
        a = row["activo"]
        print(
            f"  {a.sym:<6} "
            f"{a.peso_actual:>7.1f}% "
            f"{a.peso_objetivo:>5.1f}% "
            f"{row['gap']:>+5.1f}% "
            f"{row['proporcion']*100:>6.1f}% "
            f"${row['monto']:>8,.2f} "
            f"{row['acciones']:>8.3f}  "
            f"{a.sector}"
        )
        total_asignado += row["monto"]

    print("  " + "─" * 60)
    print(f"  {'TOTAL':<6} {'':>8} {'':>6} {'':>6} {'100%':>7} ${total_asignado:>8,.2f}")

    # ── Resumen ejecutivo ──
    print()
    print("  📋 RESUMEN EJECUTIVO")
    print("  " + "─" * 40)
    for row in asignaciones:
        a = row["activo"]
        acc_txt = f"{row['acciones']:.3f} acciones" if row["acciones"] > 0 else "fraccionado"
        print(f"  ✅ {a.sym:<5}  ${row['monto']:>8,.2f}  →  {acc_txt}")

    # ── Advertencias ──
    print()
    print("  ⚠️  ADVERTENCIAS")
    print("  " + "─" * 40)
    if VIX_HOY > 25:
        print(f"  🔴 VIX alto ({VIX_HOY}): mercado volátil, considerar reducir monto")
    if SEMAFORO_GLOBAL == "naranja":
        print("  🟠 Semáforo NARANJA: solo ejecutar si tenés convicción en los activos")
    if modo == "agresivo":
        print("  ⚡ Modo AGRESIVO: incluye activos con condiciones adversas")

    # ── Activos excluidos ──
    print()
    _mostrar_excluidos(excluidos)

    # ── Nota final ──
    print()
    print("  💡 SUGERENCIA DEL ASESOR")
    print("  " + "─" * 40)
    print(f"  Con VIX en {VIX_HOY}, el reporte recomienda congelar compras.")
    print("  Si igual querés invertir, priorizá los activos con mayor gap")
    print("  y mejor Sharpe (NVDA, GOOG, MU) en pequeñas dosis.")
    print()
    print("  Este script es informativo. No constituye asesoramiento financiero.")
    print("=" * 62)
    print()


def _mostrar_excluidos(excluidos: list) -> None:
    if not excluidos:
        return
    print("  🚫 ACTIVOS EXCLUIDOS")
    print("  " + "─" * 40)
    for activo, razon in excluidos:
        print(f"  {activo.sym:<6}  {razon}")


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Distribuye un monto a invertir en tu cartera según Markowitz + semáforo."
    )
    parser.add_argument(
        "monto",
        type=float,
        help="Monto en USD a invertir hoy (ej: 500)"
    )
    parser.add_argument(
        "--modo",
        choices=["conservador", "agresivo"],
        default="conservador",
        help="conservador: solo activos verdes | agresivo: incluye naranjas (default: conservador)"
    )
    parser.add_argument(
        "--ignorar-semaforo",
        action="store_true",
        help="Ignorar el semáforo de mercado y distribuir en todos los activos subponderados"
    )

    args = parser.parse_args()

    if args.monto <= 0:
        print("❌ El monto debe ser mayor a 0.")
        sys.exit(1)

    calcular_distribucion(
        monto=args.monto,
        modo=args.modo,
        ignorar_semaforo=args.ignorar_semaforo,
    )


if __name__ == "__main__":
    main()
