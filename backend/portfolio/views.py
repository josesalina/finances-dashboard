import logging
import traceback
import tempfile
from pathlib import Path
from datetime import datetime, date
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def _parse_date(val: str) -> date:
    """Accept MM/DD/YYYY or YYYY-MM-DD."""
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {val}")

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser
from django.db.models import F
from django.db import transaction

from .models import MonthlySnapshot, Holding, Dividend, Transaction, DividendConfig, SemaphoreRun
from .serializers import SnapshotListSerializer, SnapshotDetailSerializer, DividendConfigSerializer, SemaphoreRunSerializer
from rest_framework.views import APIView
from .script_runner import run_parse_pdf, run_markowitz, run_semaforo, run_asesor, run_stock_analyzer, period_to_date

TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def _upsert_snapshot(data: dict) -> tuple[MonthlySnapshot, bool]:
    """Create or overwrite a MonthlySnapshot from alpaca_data dict."""
    period = data["header"].get("period", "UNKNOWN - 0000")
    period_date = period_to_date(period)
    account_no = data["header"].get("account_no", "unknown")

    income = data.get("income", {})
    dividend_income = income.get("dividend", {}).get("period", 0.0)
    pnl = data.get("realized_pnl", {})
    st = pnl.get("short_term", {})
    lt = pnl.get("long_term", {})
    realized_net = (
        st.get("net", {}).get("period", 0.0) +
        lt.get("net", {}).get("period", 0.0)
    )

    snapshot, created = MonthlySnapshot.objects.update_or_create(
        account_no=account_no,
        period_date=period_date,
        defaults={
            "period": period,
            "source_pdf_name": data.get("source_file", ""),
            "parsed_at": datetime.fromisoformat(data["parsed_at"]),
            "total_value": data.get("total_value", 0),
            "cash": data.get("cash", 0),
            "dividend_income": dividend_income,
            "realized_pnl_net": realized_net,
            "alpaca_raw": data,
        },
    )

    # Overwrite related rows
    snapshot.holdings.all().delete()
    snapshot.dividends.all().delete()
    snapshot.transactions.all().delete()

    Holding.objects.bulk_create([
        Holding(
            snapshot=snapshot,
            symbol=sym,
            description=h.get("description", ""),
            qty=h["qty"],
            market_price=h["market_price"],
            market_value=h["market_value"],
            cost_price=h["cost_price"],
            cost_basis=h["cost_basis"],
            unrealized_pnl=h["unrealized_pnl"],
            pnl_pct=h["pnl_pct"],
            weight=h["weight"],
        )
        for sym, h in data.get("holdings", {}).items()
    ])

    Dividend.objects.bulk_create([
        Dividend(
            snapshot=snapshot,
            date=_parse_date(d["date"]),
            symbol=d.get("symbol", ""),
            event_type=d.get("type", ""),
            description=d.get("description", ""),
            amount=d["amount"],
        )
        for d in data.get("dividends", [])
        if d.get("amount", 0) != 0
    ])

    Transaction.objects.bulk_create([
        Transaction(
            snapshot=snapshot,
            date=_parse_date(t["date"]),
            symbol=t.get("symbol", ""),
            side=t.get("side", ""),
            event_type=t.get("type", ""),
            qty=t.get("qty", 0),
            price=t.get("price", 0),
            amount=t.get("amount", 0),
        )
        for t in data.get("transactions", [])
        if t.get("symbol")
    ])

    return snapshot, created


class SnapshotViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MonthlySnapshot.objects.all()

    def get_serializer_class(self):
        if self.action == "retrieve":
            return SnapshotDetailSerializer
        return SnapshotListSerializer

    @action(detail=False, methods=["post"], url_path="upload-pdf", parser_classes=[MultiPartParser])
    def upload_pdf(self, request):
        pdf_file = request.FILES.get("pdf")
        if not pdf_file:
            return Response({"error": "No PDF file provided."}, status=status.HTTP_400_BAD_REQUEST)

        # Save to temp file
        suffix = Path(pdf_file.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            for chunk in pdf_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            data = run_parse_pdf(tmp_path)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        with transaction.atomic():
            snapshot, created = _upsert_snapshot(data)

        return Response(
            {
                "id": snapshot.id,
                "period": snapshot.period,
                "total_value": str(snapshot.total_value),
                "holdings_count": snapshot.holdings.count(),
                "created": created,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="evolution")
    def evolution(self, request):
        data = (
            MonthlySnapshot.objects
            .order_by("period_date")
            .values("id", "period_date", "period", "total_value", "cash", "dividend_income")
        )
        return Response(list(data))

    @action(detail=False, methods=["get"], url_path="holdings-history")
    def holdings_history(self, request):
        symbols = request.query_params.get("symbols")
        qs = Holding.objects.select_related("snapshot").order_by("snapshot__period_date")
        if symbols:
            qs = qs.filter(symbol__in=symbols.split(","))
        data = qs.values(
            "symbol",
            period_date=F("snapshot__period_date"),
            period=F("snapshot__period"),
        ).annotate(
            w=F("weight"),
            mv=F("market_value"),
            pnl=F("unrealized_pnl"),
        )
        return Response(list(data))

    @action(detail=False, methods=["get"], url_path="current")
    def current(self, request):
        snapshot = MonthlySnapshot.objects.order_by("-period_date").first()
        if not snapshot:
            return Response({"detail": "No snapshots yet."}, status=status.HTTP_404_NOT_FOUND)
        return Response(SnapshotDetailSerializer(snapshot).data)

    @action(detail=True, methods=["post"], url_path="run-markowitz")
    def run_markowitz_action(self, request, pk=None):
        snapshot = self.get_object()
        if not snapshot.alpaca_raw:
            return Response({"error": "No alpaca_raw data on this snapshot."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            markowitz_data = run_markowitz(snapshot.alpaca_raw)
        except Exception as e:
            logger.error("run_markowitz failed for snapshot %s:\n%s", pk, traceback.format_exc())
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        primary = markowitz_data.get("primary_strategy", "")
        target_weights = markowitz_data.get("optimal_portfolios", {}).get(primary, {}).get("weights", {})
        sharpe_map = {
            row["Símbolo"]: row["Sharpe"]
            for row in markowitz_data.get("risk_individual", [])
            if "Símbolo" in row and "Sharpe" in row
        }

        with transaction.atomic():
            snapshot.markowitz_raw = markowitz_data
            snapshot.save(update_fields=["markowitz_raw", "updated_at"])

            for holding in snapshot.holdings.all():
                updated = False
                tw = target_weights.get(holding.symbol)
                if tw is not None:
                    holding.target_weight = tw
                    updated = True
                sh = sharpe_map.get(holding.symbol)
                if sh is not None:
                    holding.sharpe = sh
                    updated = True
                if updated:
                    holding.save(update_fields=["target_weight", "sharpe"])

        return Response({"id": snapshot.id, "period": snapshot.period, "primary_strategy": primary})

    @action(detail=True, methods=["post"], url_path="run-semaforo")
    def run_semaforo_action(self, request, pk=None):
        snapshot = self.get_object()
        if not snapshot.alpaca_raw:
            return Response({"error": "No alpaca_raw data on this snapshot."}, status=status.HTTP_400_BAD_REQUEST)
        if not snapshot.markowitz_raw:
            return Response({"error": "Run Markowitz first."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            semaforo_data = run_semaforo(snapshot.alpaca_raw, snapshot.markowitz_raw)
        except Exception as e:
            logger.error("run_semaforo failed for snapshot %s:\n%s", pk, traceback.format_exc())
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        snapshot.semaforo_raw = semaforo_data
        snapshot.save(update_fields=["semaforo_raw", "updated_at"])

        run = SemaphoreRun.objects.create(snapshot=snapshot, semaforo_raw=semaforo_data)

        sem = semaforo_data.get("semaforo", {})
        return Response({
            "id": snapshot.id,
            "period": snapshot.period,
            "semaphore_code": sem.get("code"),
            "decision": sem.get("decision"),
            "consejo": sem.get("consejo"),
            "run_id": run.id,
            "ran_at": run.ran_at.isoformat(),
        })

    @action(detail=True, methods=["post"], url_path="run-advisor")
    def run_advisor_action(self, request, pk=None):
        snapshot = self.get_object()
        if not snapshot.alpaca_raw:
            return Response({"error": "No alpaca_raw data on this snapshot."}, status=status.HTTP_400_BAD_REQUEST)
        if not snapshot.markowitz_raw:
            return Response({"error": "Run Markowitz first."}, status=status.HTTP_400_BAD_REQUEST)
        if not snapshot.semaforo_raw:
            return Response({"error": "Run Semáforo first."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            report = run_asesor(snapshot.alpaca_raw, snapshot.markowitz_raw, snapshot.semaforo_raw)
        except Exception as e:
            logger.error("run_asesor failed for snapshot %s:\n%s", pk, traceback.format_exc())
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        snapshot.advisor_report = report
        snapshot.save(update_fields=["advisor_report", "updated_at"])

        return Response({
            "id": snapshot.id,
            "period": snapshot.period,
            "report_length": len(report),
            "report": report,
        })


    @action(detail=False, methods=["get"], url_path="dividends-calendar")
    def dividends_calendar(self, request):
        from collections import defaultdict
        from decimal import Decimal
        from datetime import date

        MONTH_NAMES = [
            "JANUARY","FEBRUARY","MARCH","APRIL","MAY","JUNE",
            "JULY","AUGUST","SEPTEMBER","OCTOBER","NOVEMBER","DECEMBER",
        ]

        def add_months(d: date, n: int) -> date:
            m = d.month - 1 + n
            return date(d.year + m // 12, m % 12 + 1, 1)

        def period_label(period: str) -> str:
            parts = period.split(" - ")
            return parts[0][:3].upper() + " " + parts[1][-2:]

        today = date.today()
        end_of_year = date(today.year, 12, 31)

        snapshots = list(
            MonthlySnapshot.objects.order_by("period_date").values("period_date", "period")
        )
        real_month_keys = {str(s["period_date"]) for s in snapshots}

        # Aggregate real dividend amounts per (symbol, period_date)
        sym_month: dict = defaultdict(lambda: defaultdict(lambda: {"gross": Decimal("0"), "withheld": Decimal("0")}))
        for d in Dividend.objects.select_related("snapshot").order_by("snapshot__period_date"):
            mk = str(d.snapshot.period_date)
            if "withheld" in d.event_type.lower():
                sym_month[d.symbol][mk]["withheld"] += d.amount
            else:
                sym_month[d.symbol][mk]["gross"] += d.amount

        # Build active DividendConfig overrides (active = end_date is null or >= today)
        active_configs = {
            c.symbol.upper(): c
            for c in DividendConfig.objects.filter(start_date__lte=end_of_year)
            if c.end_date is None or c.end_date >= today
        }

        # Also build latest holdings qty map from most recent snapshot
        latest_snapshot = MonthlySnapshot.objects.order_by("-period_date").first()
        holdings_map: dict = {}
        if latest_snapshot:
            for h in latest_snapshot.holdings.all():
                holdings_map[h.symbol] = {"qty": float(h.qty)}

        # Project future months until end of current year
        projected_month_keys: set = set()
        projected_cells: dict = {}

        for sym, month_data in sym_month.items():
            payment_dates = sorted(date.fromisoformat(mk) for mk in month_data.keys())
            if not payment_dates:
                continue

            # Determine payment interval in months
            if len(payment_dates) >= 2:
                avg_days = (payment_dates[-1] - payment_dates[0]).days / (len(payment_dates) - 1)
                interval_months = next(
                    (m for days, m in [(30,1),(60,2),(91,3),(182,6),(365,12)] if abs(avg_days - days) < 25),
                    max(1, round(avg_days / 30.44)),
                )
            else:
                interval_months = 3

            # Use average of all historical payments as projected amount
            avg_gross = sum(v["gross"] for v in month_data.values()) / len(month_data)
            avg_withheld = sum(v["withheld"] for v in month_data.values()) / len(month_data)

            # Check if manual config overrides the historical projection
            config = active_configs.get(sym)
            if config:
                interval_months = config.interval_months
                qty = Decimal(str(holdings_map.get(sym, {}).get("qty", 1)))
                avg_gross = config.amount_per_share * qty
                avg_withheld = Decimal("0") if config.tax_exempt else avg_gross * Decimal("0.30") * -1
                if config.start_date:
                    config_start = config.start_date.replace(day=1)
                else:
                    config_start = today.replace(day=1)
                config_end = config.end_date.replace(day=1) if config.end_date else end_of_year

            if config:
                proj_end = min(config_end, end_of_year)
                next_date = config_start
            else:
                next_date = add_months(payment_dates[-1], interval_months)

            sym_proj: dict = {}
            while next_date <= (proj_end if config else end_of_year):
                mk = str(next_date)
                # Include if no real snapshot exists for this month
                if mk not in real_month_keys:
                    sym_proj[mk] = {
                        "gross": float(avg_gross),
                        "withheld": float(avg_withheld),
                        "net": float(avg_gross + avg_withheld),
                        "projected": True,
                    }
                    projected_month_keys.add(mk)
                next_date = add_months(next_date, interval_months)

            if sym_proj:
                projected_cells[sym] = sym_proj

        # Build sorted list of all months (real + projected)
        all_month_keys = sorted(real_month_keys | projected_month_keys)
        months_info = []
        for mk in all_month_keys:
            d = date.fromisoformat(mk)
            is_proj = mk not in real_month_keys
            snap = next((s for s in snapshots if str(s["period_date"]) == mk), None)
            period = snap["period"] if snap else f"{MONTH_NAMES[d.month - 1]} - {d.year}"
            months_info.append({
                "period_date": mk,
                "period": period,
                "label": period_label(period),
                "projected": is_proj,
            })

        # Build per-month totals
        totals_by_month: dict = {mk: {"gross": Decimal("0"), "withheld": Decimal("0"), "projected": mk not in real_month_keys}
                                  for mk in all_month_keys}

        # Build rows
        all_symbols = sorted(set(sym_month.keys()) | set(projected_cells.keys()))
        rows = []
        grand_real_gross = Decimal("0")
        grand_real_withheld = Decimal("0")
        grand_proj_gross = Decimal("0")
        grand_proj_withheld = Decimal("0")

        for sym in all_symbols:
            months_out: dict = {}

            # Real cells
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

            # Projected cells
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

        # Build payment schedule (last real + next projected per symbol)
        import re
        from datetime import timedelta

        def parse_desc(desc: str) -> dict:
            out = {}
            m = re.search(r"Cash DIV @ ([\d.]+)", desc)
            if m:
                out["div_per_share"] = float(m.group(1))
            m = re.search(r"Rec Date: (\d{4}-\d{2}-\d{2})", desc)
            if m:
                out["record_date"] = m.group(1)
            return out

        FREQ_LABELS = {1: "Mensual", 2: "Bimestral", 3: "Trimestral", 6: "Semestral", 12: "Anual"}

        schedule = []
        for sym in all_symbols:
            month_data = sym_month.get(sym, {})
            payment_dates = sorted(date.fromisoformat(mk) for mk in month_data.keys())
            if not payment_dates:
                continue

            # Determine interval
            if len(payment_dates) >= 2:
                avg_days = (payment_dates[-1] - payment_dates[0]).days / (len(payment_dates) - 1)
                interval_months = next(
                    (m for days, m in [(30,1),(60,2),(91,3),(182,6),(365,12)] if abs(avg_days - days) < 25),
                    max(1, round(avg_days / 30.44)),
                )
            else:
                interval_months = 3

            config = active_configs.get(sym)
            if config:
                interval_months = config.interval_months

            # Last real payment details
            last_pay = payment_dates[-1]
            last_mk = str(last_pay)
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
                info = parse_desc(last_div_obj.description)
                last_div_per_share = info.get("div_per_share")
                last_record_date = info.get("record_date")

            # Next projected payment — advance until we find one >= today
            today_first = today.replace(day=1)
            config_sched = active_configs.get(sym)
            if config_sched and config_sched.start_date:
                candidate = max(config_sched.start_date.replace(day=1), today_first)
            else:
                candidate = add_months(payment_dates[-1], interval_months)
                while candidate < today_first:
                    candidate = add_months(candidate, interval_months)
            config_end = (config_sched.end_date.replace(day=1) if config_sched and config_sched.end_date else end_of_year)
            next_pay_date_str = None
            next_ex_date_str = None
            if candidate <= min(end_of_year, config_end):
                pay_day = last_div_obj.date.day if last_div_obj else 15
                try:
                    import calendar as cal
                    max_day = cal.monthrange(candidate.year, candidate.month)[1]
                    actual_pay = date(candidate.year, candidate.month, min(pay_day, max_day))
                except Exception:
                    actual_pay = candidate
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

        schedule.sort(key=lambda s: (s["next_ex_date"] or "9999", s["symbol"]))

        return Response({
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
        })


class DividendConfigViewSet(viewsets.ModelViewSet):
    queryset = DividendConfig.objects.all()
    serializer_class = DividendConfigSerializer


class SemaphoreRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SemaphoreRun.objects.select_related("snapshot").all()
    serializer_class = SemaphoreRunSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        snapshot_id = self.request.query_params.get("snapshot_id")
        if snapshot_id:
            qs = qs.filter(snapshot_id=snapshot_id)
        return qs

    @action(detail=False, methods=["post"], url_path="run")
    def run(self, request):
        snapshot_id = request.data.get("snapshot_id")
        if not snapshot_id:
            return Response({"error": "snapshot_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            snapshot = MonthlySnapshot.objects.get(pk=snapshot_id)
        except MonthlySnapshot.DoesNotExist:
            return Response({"error": "Snapshot not found."}, status=status.HTTP_400_BAD_REQUEST)

        if not snapshot.alpaca_raw:
            return Response({"error": "No alpaca_raw data on this snapshot."}, status=status.HTTP_400_BAD_REQUEST)
        if not snapshot.markowitz_raw:
            return Response({"error": "Run Markowitz first."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            semaforo_data = run_semaforo(snapshot.alpaca_raw, snapshot.markowitz_raw)
        except Exception as e:
            logger.error("run_semaforo (SemaphoreRunViewSet) failed for snapshot %s:\n%s", snapshot_id, traceback.format_exc())
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        snapshot.semaforo_raw = semaforo_data
        snapshot.save(update_fields=["semaforo_raw", "updated_at"])

        run = SemaphoreRun.objects.create(snapshot=snapshot, semaforo_raw=semaforo_data)

        return Response(SemaphoreRunSerializer(run).data, status=status.HTTP_201_CREATED)


class StockAnalyzerView(APIView):
    def get(self, request):
        ticker = request.query_params.get("ticker", "").strip().upper()
        if not ticker:
            return Response({"error": "Parámetro 'ticker' requerido."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            data = run_stock_analyzer(ticker)
        except Exception as e:
            logger.error("stock_analyzer failed for %s:\n%s", ticker, traceback.format_exc())
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(data)
