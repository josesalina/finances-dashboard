import re
import calendar as cal
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from .models import MonthlySnapshot, Dividend, DividendConfig

MONTH_NAMES = [
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
    "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
]

FREQ_LABELS = {1: "Mensual", 2: "Bimestral", 3: "Trimestral", 6: "Semestral", 12: "Anual"}


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def _period_label(period: str) -> str:
    parts = period.split(" - ")
    return parts[0][:3].upper() + " " + parts[1][-2:]


def _parse_desc(desc: str) -> dict:
    out = {}
    m = re.search(r"Cash DIV @ ([\d.]+)", desc)
    if m:
        out["div_per_share"] = float(m.group(1))
    m = re.search(r"Rec Date: (\d{4}-\d{2}-\d{2})", desc)
    if m:
        out["record_date"] = m.group(1)
    return out


def _infer_interval(payment_dates: list) -> int:
    if len(payment_dates) >= 2:
        avg_days = (payment_dates[-1] - payment_dates[0]).days / (len(payment_dates) - 1)
        return next(
            (m for days, m in [(30, 1), (60, 2), (91, 3), (182, 6), (365, 12)] if abs(avg_days - days) < 25),
            max(1, round(avg_days / 30.44)),
        )
    return 3


def build_dividend_calendar() -> dict:
    today = date.today()
    end_of_year = date(today.year, 12, 31)

    snapshots = list(
        MonthlySnapshot.objects.order_by("period_date").values("period_date", "period")
    )
    real_month_keys = {str(s["period_date"]) for s in snapshots}

    sym_month: dict = defaultdict(lambda: defaultdict(lambda: {"gross": Decimal("0"), "withheld": Decimal("0")}))
    for d in Dividend.objects.select_related("snapshot").order_by("snapshot__period_date"):
        mk = str(d.snapshot.period_date)
        if "withheld" in d.event_type.lower():
            sym_month[d.symbol][mk]["withheld"] += d.amount
        else:
            sym_month[d.symbol][mk]["gross"] += d.amount

    active_configs = {
        c.symbol.upper(): c
        for c in DividendConfig.objects.filter(start_date__lte=end_of_year)
        if c.end_date is None or c.end_date >= today
    }

    latest_snapshot = MonthlySnapshot.objects.order_by("-period_date").first()
    holdings_map: dict = {}
    if latest_snapshot:
        for h in latest_snapshot.holdings.all():
            holdings_map[h.symbol] = {"qty": float(h.qty)}

    projected_month_keys: set = set()
    projected_cells: dict = {}

    for sym, month_data in sym_month.items():
        payment_dates = sorted(date.fromisoformat(mk) for mk in month_data.keys())
        if not payment_dates:
            continue

        interval_months = _infer_interval(payment_dates)
        avg_gross = sum(v["gross"] for v in month_data.values()) / len(month_data)
        avg_withheld = sum(v["withheld"] for v in month_data.values()) / len(month_data)

        config = active_configs.get(sym)
        if config:
            interval_months = config.interval_months
            qty = Decimal(str(holdings_map.get(sym, {}).get("qty", 1)))
            avg_gross = config.amount_per_share * qty
            avg_withheld = Decimal("0") if config.tax_exempt else avg_gross * Decimal("0.30") * -1
            config_start = config.start_date.replace(day=1) if config.start_date else today.replace(day=1)
            config_end = config.end_date.replace(day=1) if config.end_date else end_of_year
            proj_end = min(config_end, end_of_year)
            next_date = config_start
        else:
            proj_end = end_of_year
            next_date = _add_months(payment_dates[-1], interval_months)

        sym_proj: dict = {}
        while next_date <= proj_end:
            mk = str(next_date)
            if mk not in real_month_keys:
                sym_proj[mk] = {
                    "gross": float(avg_gross),
                    "withheld": float(avg_withheld),
                    "net": float(avg_gross + avg_withheld),
                    "projected": True,
                }
                projected_month_keys.add(mk)
            next_date = _add_months(next_date, interval_months)

        if sym_proj:
            projected_cells[sym] = sym_proj

    for sym, config in active_configs.items():
        if sym in sym_month:
            continue

        qty = Decimal(str(holdings_map.get(sym, {}).get("qty", 1)))
        avg_gross = config.amount_per_share * qty
        avg_withheld = Decimal("0") if config.tax_exempt else avg_gross * Decimal("0.30") * -1
        interval_months = config.interval_months
        config_start = config.start_date.replace(day=1)
        config_end = config.end_date.replace(day=1) if config.end_date else end_of_year
        proj_end = min(config_end, end_of_year)

        sym_proj = {}
        next_date = config_start
        while next_date <= proj_end:
            mk = str(next_date)
            if mk not in real_month_keys:
                sym_proj[mk] = {
                    "gross": float(avg_gross),
                    "withheld": float(avg_withheld),
                    "net": float(avg_gross + avg_withheld),
                    "projected": True,
                }
                projected_month_keys.add(mk)
            next_date = _add_months(next_date, interval_months)

        if sym_proj:
            projected_cells[sym] = sym_proj

    all_month_keys = sorted(real_month_keys | projected_month_keys)
    months_info = []
    for mk in all_month_keys:
        d = date.fromisoformat(mk)
        snap = next((s for s in snapshots if str(s["period_date"]) == mk), None)
        period = snap["period"] if snap else f"{MONTH_NAMES[d.month - 1]} - {d.year}"
        months_info.append({
            "period_date": mk,
            "period": period,
            "label": _period_label(period),
            "projected": mk not in real_month_keys,
        })

    totals_by_month: dict = {
        mk: {"gross": Decimal("0"), "withheld": Decimal("0"), "projected": mk not in real_month_keys}
        for mk in all_month_keys
    }

    all_symbols = sorted(set(sym_month.keys()) | set(projected_cells.keys()))
    rows = []
    grand_real_gross = Decimal("0")
    grand_real_withheld = Decimal("0")
    grand_proj_gross = Decimal("0")
    grand_proj_withheld = Decimal("0")

    for sym in all_symbols:
        months_out: dict = {}
        real_gross = Decimal("0")
        real_withheld = Decimal("0")
        for mk in real_month_keys:
            if mk in sym_month.get(sym, {}):
                g = sym_month[sym][mk]["gross"]
                w = sym_month[sym][mk]["withheld"]
                months_out[mk] = {"gross": float(g), "withheld": float(w), "net": float(g + w), "projected": False}
                totals_by_month[mk]["gross"] += g
                totals_by_month[mk]["withheld"] += w
                real_gross += g
                real_withheld += w

        proj_gross = Decimal("0")
        proj_withheld = Decimal("0")
        for mk, cell in projected_cells.get(sym, {}).items():
            months_out[mk] = cell
            g = Decimal(str(cell["gross"]))
            w = Decimal(str(cell["withheld"]))
            totals_by_month[mk]["gross"] += g
            totals_by_month[mk]["withheld"] += w
            proj_gross += g
            proj_withheld += w

        grand_real_gross += real_gross
        grand_real_withheld += real_withheld
        grand_proj_gross += proj_gross
        grand_proj_withheld += proj_withheld

        rows.append({
            "symbol": sym,
            "total_real_gross": float(real_gross),
            "total_real_withheld": float(real_withheld),
            "total_real_net": float(real_gross + real_withheld),
            "total_proj_gross": float(proj_gross),
            "total_proj_withheld": float(proj_withheld),
            "total_proj_net": float(proj_gross + proj_withheld),
            "months": months_out,
        })

    rows.sort(key=lambda r: r["total_real_net"], reverse=True)

    schedule = _build_schedule(all_symbols, sym_month, active_configs, holdings_map, today, end_of_year)

    return {
        "months": months_info,
        "rows": rows,
        "totals": {
            "real_gross": float(grand_real_gross),
            "real_withheld": float(grand_real_withheld),
            "real_net": float(grand_real_gross + grand_real_withheld),
            "proj_gross": float(grand_proj_gross),
            "proj_withheld": float(grand_proj_withheld),
            "proj_net": float(grand_proj_gross + grand_proj_withheld),
            "by_month": {
                mk: {
                    "gross": float(v["gross"]),
                    "withheld": float(v["withheld"]),
                    "net": float(v["gross"] + v["withheld"]),
                    "projected": v["projected"],
                }
                for mk, v in totals_by_month.items()
            },
        },
        "schedule": schedule,
    }


def _build_schedule(all_symbols, sym_month, active_configs, holdings_map, today, end_of_year) -> list:
    schedule = []
    today_first = today.replace(day=1)

    for sym in all_symbols:
        month_data = sym_month.get(sym, {})
        payment_dates = sorted(date.fromisoformat(mk) for mk in month_data.keys())
        if not payment_dates:
            continue

        interval_months = _infer_interval(payment_dates)
        config = active_configs.get(sym)
        if config:
            interval_months = config.interval_months

        last_pay = payment_dates[-1]
        last_div_obj = (
            Dividend.objects
            .filter(snapshot__period_date=last_pay, symbol=sym)
            .exclude(event_type__icontains="withheld")
            .order_by("-date")
            .first()
        )
        last_div_per_share = None
        last_record_date = None
        last_pay_date = None
        if last_div_obj:
            last_pay_date = str(last_div_obj.date)
            info = _parse_desc(last_div_obj.description)
            last_div_per_share = info.get("div_per_share")
            last_record_date = info.get("record_date")

        if config and config.start_date:
            candidate = max(config.start_date.replace(day=1), today_first)
        else:
            candidate = _add_months(payment_dates[-1], interval_months)
            while candidate < today_first:
                candidate = _add_months(candidate, interval_months)

        config_end = config.end_date.replace(day=1) if config and config.end_date else end_of_year
        next_pay_date_str = None
        next_ex_date_str = None
        if candidate <= min(end_of_year, config_end):
            pay_day = last_div_obj.date.day if last_div_obj else 15
            max_day = cal.monthrange(candidate.year, candidate.month)[1]
            actual_pay = date(candidate.year, candidate.month, min(pay_day, max_day))
            next_pay_date_str = str(actual_pay)
            next_ex_date_str = str(actual_pay - timedelta(days=3))

        schedule.append({
            "symbol": sym,
            "frequency": FREQ_LABELS.get(interval_months, f"Cada {interval_months}m"),
            "interval_months": interval_months,
            "last_pay_date": last_pay_date,
            "last_record_date": last_record_date,
            "last_ex_date": str(date.fromisoformat(last_record_date) - timedelta(days=1)) if last_record_date else None,
            "last_div_per_share": last_div_per_share,
            "next_pay_date": next_pay_date_str,
            "next_ex_date": next_ex_date_str,
        })

    for sym, config in active_configs.items():
        if sym in sym_month:
            continue
        interval_months = config.interval_months
        candidate = max(config.start_date.replace(day=1), today_first)
        config_end = config.end_date.replace(day=1) if config.end_date else end_of_year
        proj_end = min(end_of_year, config_end)
        next_pay_date_str = None
        next_ex_date_str = None
        if candidate <= proj_end:
            max_day = cal.monthrange(candidate.year, candidate.month)[1]
            actual_pay = date(candidate.year, candidate.month, min(15, max_day))
            next_pay_date_str = str(actual_pay)
            next_ex_date_str = str(actual_pay - timedelta(days=3))
        schedule.append({
            "symbol": sym,
            "frequency": FREQ_LABELS.get(interval_months, f"Cada {interval_months}m"),
            "interval_months": interval_months,
            "last_pay_date": None,
            "last_record_date": None,
            "last_ex_date": None,
            "last_div_per_share": float(config.amount_per_share),
            "next_pay_date": next_pay_date_str,
            "next_ex_date": next_ex_date_str,
        })

    schedule.sort(key=lambda s: (s["next_ex_date"] or "9999", s["symbol"]))
    return schedule
