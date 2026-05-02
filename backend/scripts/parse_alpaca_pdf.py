"""
=============================================================
  SCRIPT 1/4 — PARSER DE PDF ALPACA
  parse_alpaca_pdf.py
=============================================================
Extrae toda la información del estado de cuenta mensual de
Alpaca y genera alpaca_data.json que alimenta a los demás scripts.

USO:
    python parse_alpaca_pdf.py account_statement.pdf

SALIDA:
    alpaca_data.json
"""

import sys
import json
import re
import pdfplumber
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ_ARG = ZoneInfo("America/Argentina/Buenos_Aires")

def parse_money(val):
    """Convierte string '$1,234.56' o '-$1,234.56' a float. Devuelve 0.0 si vacío."""
    if not val or val.strip() in ("$ --", "--", "", "None"):
        return 0.0
    val = val.strip().replace("$", "").replace(",", "").replace(" ", "")
    try:
        return float(val)
    except ValueError:
        return 0.0

def parse_qty(val):
    if not val or val.strip() in ("$ --", "--", "", "None"):
        return 0.0
    try:
        return float(val.strip())
    except ValueError:
        return 0.0

def extraer_header(texto):
    """Extrae número de cuenta, período y nombre del titular."""
    data = {}
    m = re.search(r"Account No[:\s]+(\d+)", texto)
    if m:
        data["account_no"] = m.group(1)
    m = re.search(r"Period[:\s]+([A-Z]+ - \d{4})", texto)
    if m:
        data["period"] = m.group(1)
    # Nombre: primera línea antes de la dirección
    lines = [l.strip() for l in texto.split("\n") if l.strip()]
    for line in lines[:5]:
        if re.match(r"^[A-Z][A-Z\s]+$", line) and len(line) > 5:
            data["name"] = line
            break
    return data

def extraer_cash_summary(tables):
    """Extrae el resumen de cash del período."""
    result = {}
    for table in tables:
        if not table or len(table) < 2:
            continue
        if table[0] and "Cash Summary" in str(table[0][0]):
            for row in table[1:]:
                if not row or not row[0]:
                    continue
                key = row[0].strip()
                val_period = parse_money(str(row[1])) if len(row) > 1 else 0.0
                val_ytd    = parse_money(str(row[2])) if len(row) > 2 else 0.0
                key_map = {
                    "Beginning Balance": "beginning_balance",
                    "Addition":          "additions",
                    "Subtraction":       "subtractions",
                    "Trade Transaction": "trade_transactions",
                    "Cost and Fees":     "fees",
                    "Ending Value":      "ending_cash",
                }
                if key in key_map:
                    result[key_map[key]] = {"period": val_period, "ytd": val_ytd}
    return result

def extraer_account_summary(tables):
    result = {}
    for table in tables:
        if not table or len(table) < 2:
            continue
        if table[0] and "Account Summary" in str(table[0][0]):
            for row in table[1:]:
                if not row or not row[0]:
                    continue
                key = row[0].strip()
                val = parse_money(str(row[1])) if len(row) > 1 else 0.0
                key_map = {
                    "Long":              "long_value",
                    "Short":             "short_value",
                    "Options":           "options_value",
                    "Fixed Income":      "fixed_income_value",
                    "Total Market Value":"total_market_value",
                }
                if key in key_map:
                    result[key_map[key]] = val
    return result

def extraer_income(tables):
    result = {}
    for table in tables:
        if not table or len(table) < 2:
            continue
        if table[0] and "Income Summary" in str(table[0][0]):
            for row in table[1:]:
                if not row or not row[0]:
                    continue
                key = row[0].strip().replace("**", "")
                val_p = parse_money(str(row[1])) if len(row) > 1 else 0.0
                val_y = parse_money(str(row[2])) if len(row) > 2 else 0.0
                result[key.lower()] = {"period": val_p, "ytd": val_y}
    return result

def extraer_pnl(tables):
    result = {"short_term": {}, "long_term": {}}
    for table in tables:
        if not table:
            continue
        if table[0] and "Realized Gain" in str(table[0][0]):
            current = None
            for row in table[1:]:
                if not row or not row[0]:
                    continue
                key = str(row[0]).strip()
                if "Short Term" in key:
                    current = "short_term"
                elif "Long Term" in key:
                    current = "long_term"
                elif current and key in ("Gain", "Loss", "Net"):
                    val_p = parse_money(str(row[1])) if len(row) > 1 else 0.0
                    val_y = parse_money(str(row[2])) if len(row) > 2 else 0.0
                    result[current][key.lower()] = {"period": val_p, "ytd": val_y}
    return result

def extraer_holdings(tables):
    """Extrae todas las posiciones con sus métricas."""
    holdings = {}
    for table in tables:
        if not table or len(table) < 3:
            continue
        # Detectar tabla de Holdings por cabecera
        header = [str(c).strip() if c else "" for c in (table[1] if len(table) > 1 else [])]
        if "Symbol" not in header:
            continue
        for row in table[2:]:
            if not row or not row[0] or row[0] == "*Cash":
                continue
            try:
                symbol      = str(row[0]).strip()
                description = str(row[1]).strip() if row[1] else ""
                qty         = parse_qty(str(row[2]))
                mkt_price   = parse_money(str(row[3]))
                mkt_value   = parse_money(str(row[4]))
                cost_price  = parse_money(str(row[5]))
                unrealized  = parse_money(str(row[6]))
                cost_basis  = parse_money(str(row[7]))

                if symbol and qty > 0:
                    holdings[symbol] = {
                        "description": description,
                        "qty":         qty,
                        "market_price":mkt_price,
                        "market_value":mkt_value,
                        "cost_price":  cost_price,
                        "unrealized_pnl": unrealized,
                        "cost_basis":  cost_basis,
                        "weight":      0.0,  # se calcula después
                        "pnl_pct":     round((mkt_price / cost_price - 1) * 100, 2)
                                       if cost_price > 0 else 0.0,
                    }
            except Exception:
                continue
    return holdings

def extraer_cash_position(texto):
    """Extrae el cash disponible desde el texto de Holdings."""
    m = re.search(r"\*Cash\s+USD\s+\$\s*--\s+\$\s*--\s+\$([\d,]+\.?\d*)", texto)
    if m:
        return parse_money("$" + m.group(1))
    return 0.0

def extraer_transacciones(tables):
    """Extrae el historial de operaciones del período."""
    transactions = []
    for table in tables:
        if not table or len(table) < 2:
            continue

        # Buscar la fila de header en las primeras 3 filas (el título puede ocupar la fila 0)
        header_idx = None
        header = []
        for idx in range(min(3, len(table))):
            row = table[idx]
            if not row:
                continue
            row_str = [str(c).strip() if c else "" for c in row]
            # Una tabla de trades siempre tiene "Side" y al menos "Symbol" o "Qty"
            if "Side" in row_str and ("Symbol" in row_str or "Qty" in row_str):
                header_idx = idx
                header = row_str
                break

        if header_idx is None:
            continue

        def col(name, fallback):
            """Devuelve el índice de la columna por nombre, o el fallback."""
            try:
                return header.index(name)
            except ValueError:
                return fallback

        idx_date   = col("Trade Date", 0)
        idx_type   = col("Entry Type", 1)
        idx_side   = col("Side",       2)
        idx_symbol = col("Symbol",     3)
        idx_qty    = next((col(n, 5) for n in ("Quantity", "Qty") if n in header), 5)
        idx_price  = col("Price",      6)
        idx_amount = col("Amount",     7)

        for row in table[header_idx + 1:]:
            if not row or not row[0]:
                continue
            if not re.match(r"\d{2}/\d{2}/\d{4}", str(row[0])):
                continue
            try:
                def cell(idx):
                    return row[idx] if idx < len(row) and row[idx] else None

                transactions.append({
                    "date":   str(cell(idx_date) or "").strip(),
                    "type":   str(cell(idx_type)   or "").strip(),
                    "side":   str(cell(idx_side)   or "").strip(),
                    "symbol": str(cell(idx_symbol) or "").strip(),
                    "qty":    parse_qty(str(cell(idx_qty)    or 0)),
                    "price":  parse_money(str(cell(idx_price)  or 0)),
                    "amount": parse_money(str(cell(idx_amount) or 0)),
                })
            except Exception:
                continue
    return transactions

def extraer_dividendos(tables):
    """Extrae dividendos e impuestos retenidos."""
    dividends = []
    for table in tables:
        if not table or len(table) < 3:
            continue
        if table[0] and "Income" in str(table[0][0]) and "Trade Date" in str(table[1] if len(table) > 1 else []):
            for row in table[2:]:
                if not row or not row[0]:
                    continue
                if re.match(r"\d{2}/\d{2}/\d{4}", str(row[0])):
                    dividends.append({
                        "date":        str(row[0]).strip(),
                        "type":        str(row[1]).strip() if row[1] else "",
                        "symbol":      str(row[2]).strip() if row[2] else "",
                        "description": str(row[3]).strip() if row[3] else "",
                        "amount":      parse_money(str(row[4])) if row[4] else 0.0,
                    })
    return dividends

def calcular_pesos(holdings, total_value):
    """Calcula el peso porcentual de cada posición."""
    for sym in holdings:
        mv = holdings[sym]["market_value"]
        holdings[sym]["weight"] = round(mv / total_value * 100, 2) if total_value > 0 else 0.0
    return holdings

def parsear_pdf(pdf_path: str) -> dict:
    """Pipeline principal de extracción."""
    print(f"📄 Parseando: {pdf_path}")
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró: {pdf_path}")

    data = {
        "parsed_at":  datetime.now(TZ_ARG).isoformat(),
        "source_file": path.name,
        "header":     {},
        "cash":       0.0,
        "cash_summary": {},
        "account_summary": {},
        "income":     {},
        "realized_pnl": {},
        "holdings":   {},
        "transactions": [],
        "dividends":  [],
        "symbols":    [],
        "total_value": 0.0,
        "weights":    {},
    }

    all_tables = []
    full_text  = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            full_text += text + "\n"
            tables = page.extract_tables()
            all_tables.extend(tables or [])

    # Extracción sección por sección
    data["header"]          = extraer_header(full_text)
    data["cash_summary"]    = extraer_cash_summary(all_tables)
    data["account_summary"] = extraer_account_summary(all_tables)
    data["income"]          = extraer_income(all_tables)
    data["realized_pnl"]    = extraer_pnl(all_tables)
    data["holdings"]        = extraer_holdings(all_tables)
    data["transactions"]    = extraer_transacciones(all_tables)
    data["dividends"]       = extraer_dividendos(all_tables)
    data["cash"]            = extraer_cash_position(full_text)

    # Cash fallback desde cash_summary
    if data["cash"] == 0.0 and "ending_cash" in data["cash_summary"]:
        data["cash"] = data["cash_summary"]["ending_cash"].get("period", 0.0)

    # Total y pesos
    total = data["account_summary"].get("total_market_value", 0.0)
    if total == 0.0:
        total = sum(h["market_value"] for h in data["holdings"].values())
    data["total_value"] = total
    data["holdings"]    = calcular_pesos(data["holdings"], total)
    data["symbols"]     = sorted(data["holdings"].keys())
    data["weights"]     = {s: data["holdings"][s]["weight"] for s in data["symbols"]}

    return data

def imprimir_resumen(data):
    print("\n" + "═" * 55)
    print(f"  ✅ EXTRACCIÓN COMPLETADA")
    print("═" * 55)
    h = data["header"]
    print(f"  Titular:      {h.get('name', 'N/A')}")
    print(f"  Cuenta:       {h.get('account_no', 'N/A')}")
    print(f"  Período:      {h.get('period', 'N/A')}")
    print(f"  Generado:     {data['parsed_at']}")
    print(f"\n  Valor total:  ${data['total_value']:,.2f}")
    print(f"  Cash:         ${data['cash']:,.2f}")
    print(f"  Posiciones:   {len(data['holdings'])}")
    print(f"  Operaciones:  {len(data['transactions'])}")
    print(f"  Dividendos:   {len(data['dividends'])} registros")
    print(f"\n  Holdings:")
    for sym, h in sorted(data["holdings"].items(), key=lambda x: -x[1]["market_value"]):
        pnl = h["unrealized_pnl"]
        emoji = "🟢" if pnl >= 0 else "🔴"
        print(f"  {emoji} {sym:6s}  ${h['market_value']:>8.2f}  "
              f"{h['weight']:>5.1f}%  P&L: ${pnl:>+8.2f}  ({h['pnl_pct']:+.1f}%)")
    print("═" * 55)

def main():
    if len(sys.argv) < 2:
        # Buscar PDF en directorio actual
        pdfs = list(Path(".").glob("*.pdf"))
        if not pdfs:
            print("USO: python parse_alpaca_pdf.py account_statement.pdf")
            sys.exit(1)
        pdf_path = str(pdfs[0])
        print(f"  ℹ️  PDF encontrado automáticamente: {pdf_path}")
    else:
        pdf_path = sys.argv[1]

    data = parsear_pdf(pdf_path)
    imprimir_resumen(data)

    output = "alpaca_data.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n  💾 Datos guardados en: {output}")
    print(f"  ▶  Siguiente paso: python rebalanceo_markowitz.py")

if __name__ == "__main__":
    main()
