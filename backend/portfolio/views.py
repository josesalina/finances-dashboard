import logging
import traceback
import tempfile
from pathlib import Path
from datetime import datetime, date
from zoneinfo import ZoneInfo

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser
from rest_framework.views import APIView
from django.db import transaction
from django.db.models import F, Prefetch, Sum, DecimalField, Value
from django.db.models.functions import Coalesce

from .models import MonthlySnapshot, Holding, Dividend, Transaction, DividendConfig, SemaphoreRun
from .serializers import SnapshotListSerializer, SnapshotDetailSerializer, DividendConfigSerializer, SemaphoreRunSerializer
from .script_runner import run_parse_pdf, run_markowitz, run_semaforo, run_asesor, run_stock_analyzer, run_current_prices, period_to_date
from .services import build_dividend_calendar

logger = logging.getLogger(__name__)
TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def _parse_date(val: str) -> date:
    """Accept MM/DD/YYYY or YYYY-MM-DD."""
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {val}")

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

    def get_queryset(self):
        semaphore_prefetch = Prefetch(
            "semaphore_runs",
            queryset=SemaphoreRun.objects.order_by("-ran_at"),
            to_attr="_latest_runs",
        )
        if self.action == "retrieve":
            return MonthlySnapshot.objects.prefetch_related(
                "holdings", "dividends", "transactions", semaphore_prefetch
            )
        return MonthlySnapshot.objects.prefetch_related(semaphore_prefetch)

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
            .annotate(
                invested_capital=Coalesce(
                    Sum("holdings__cost_basis"),
                    Value(0, output_field=DecimalField()),
                )
            )
            .values("id", "period_date", "period", "total_value", "cash", "dividend_income", "invested_capital")
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
        snapshot = (
            MonthlySnapshot.objects
            .prefetch_related(
                "holdings", "dividends", "transactions",
                Prefetch("semaphore_runs", queryset=SemaphoreRun.objects.order_by("-ran_at"), to_attr="_latest_runs"),
            )
            .order_by("-period_date")
            .first()
        )
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

        with transaction.atomic():
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

        with transaction.atomic():
            snapshot.advisor_report = report
            snapshot.save(update_fields=["advisor_report", "updated_at"])

        return Response({
            "id": snapshot.id,
            "period": snapshot.period,
            "report_length": len(report),
            "report": report,
        })


    @action(detail=False, methods=["get"], url_path="current-prices")
    def current_prices(self, request):
        snapshot = (
            MonthlySnapshot.objects
            .prefetch_related("holdings")
            .order_by("-period_date")
            .first()
        )
        if not snapshot:
            return Response({"detail": "No snapshots yet."}, status=status.HTTP_404_NOT_FOUND)

        symbols = list(snapshot.holdings.values_list("symbol", flat=True))
        if not symbols:
            return Response({
                "snapshot_id": snapshot.id,
                "period": snapshot.period,
                "cash": float(snapshot.cash),
                "total_live_value": float(snapshot.total_value),
                "holdings": [],
                "updated_at": datetime.now(TZ).isoformat(),
            })

        try:
            prices = run_current_prices(symbols)
        except Exception as e:
            logger.error("current_prices failed:\n%s", traceback.format_exc())
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        holdings_data = []
        total_live_value = float(snapshot.cash)

        for h in snapshot.holdings.all():
            live_price = prices.get(h.symbol)
            snap_price = float(h.market_price)
            cost_basis = float(h.cost_basis)
            qty = float(h.qty)

            if live_price is not None:
                live_value = qty * live_price
                live_pnl = live_value - cost_basis
                live_pnl_pct = (live_pnl / cost_basis * 100) if cost_basis else 0
                price_change = live_price - snap_price
                price_change_pct = (price_change / snap_price * 100) if snap_price else 0
            else:
                live_value = float(h.market_value)
                live_pnl = float(h.unrealized_pnl)
                live_pnl_pct = float(h.pnl_pct)
                price_change = 0.0
                price_change_pct = 0.0

            total_live_value += live_value
            holdings_data.append({
                "symbol": h.symbol,
                "qty": qty,
                "current_price": live_price,
                "current_value": round(live_value, 2),
                "cost_basis": cost_basis,
                "live_pnl": round(live_pnl, 2),
                "live_pnl_pct": round(live_pnl_pct, 2),
                "price_change": round(price_change, 4),
                "price_change_pct": round(price_change_pct, 4),
                "snapshot_price": snap_price,
            })

        return Response({
            "snapshot_id": snapshot.id,
            "period": snapshot.period,
            "cash": float(snapshot.cash),
            "total_live_value": round(total_live_value, 2),
            "holdings": holdings_data,
            "updated_at": datetime.now(TZ).isoformat(),
        })

    @action(detail=False, methods=["get"], url_path="dividends-calendar")
    def dividends_calendar(self, request):
        return Response(build_dividend_calendar())



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

        with transaction.atomic():
            snapshot.semaforo_raw = semaforo_data
            snapshot.save(update_fields=["semaforo_raw", "updated_at"])
            run = SemaphoreRun.objects.create(snapshot=snapshot, semaforo_raw=semaforo_data)

        return Response(SemaphoreRunSerializer(run).data, status=status.HTTP_201_CREATED)


class StockAnalyzerView(APIView):
    def get(self, request, ticker: str):
        ticker = ticker.strip().upper()
        try:
            data = run_stock_analyzer(ticker)
        except Exception as e:
            logger.error("stock_analyzer failed for %s:\n%s", ticker, traceback.format_exc())
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(data)
