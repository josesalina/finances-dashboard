from rest_framework import serializers
from .models import MonthlySnapshot, Holding, Dividend, Transaction, DividendConfig, SemaphoreRun


class HoldingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Holding
        exclude = ["snapshot"]


class DividendSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dividend
        exclude = ["snapshot"]


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        exclude = ["snapshot"]


class TransactionWithPeriodSerializer(serializers.ModelSerializer):
    period = serializers.CharField(source="snapshot.period", read_only=True)
    period_date = serializers.DateField(source="snapshot.period_date", read_only=True)

    class Meta:
        model = Transaction
        fields = ["id", "date", "symbol", "side", "event_type", "qty", "price", "amount", "period", "period_date"]


class SnapshotListSerializer(serializers.ModelSerializer):
    semaphore_code = serializers.SerializerMethodField()

    class Meta:
        model = MonthlySnapshot
        fields = [
            "id", "period", "period_date", "total_value",
            "cash", "dividend_income", "realized_pnl_net",
            "semaphore_code", "created_at",
        ]

    def get_semaphore_code(self, obj):
        # Use prefetch cache (_latest_runs) when available, fallback to DB query
        runs = getattr(obj, "_latest_runs", None)
        run = runs[0] if runs else obj.semaphore_runs.first()
        if run:
            return run.semaforo_raw.get("semaforo", {}).get("code")
        return None


class SnapshotDetailSerializer(serializers.ModelSerializer):
    holdings = HoldingSerializer(many=True, read_only=True)
    dividends = DividendSerializer(many=True, read_only=True)
    transactions = TransactionSerializer(many=True, read_only=True)
    semaphore_code = serializers.SerializerMethodField()

    class Meta:
        model = MonthlySnapshot
        fields = "__all__"

    def get_semaphore_code(self, obj):
        # Use prefetch cache (_latest_runs) when available, fallback to DB query
        runs = getattr(obj, "_latest_runs", None)
        run = runs[0] if runs else obj.semaphore_runs.first()
        if run:
            return run.semaforo_raw.get("semaforo", {}).get("code")
        return None


class SemaphoreRunSerializer(serializers.ModelSerializer):
    semaphore_code = serializers.SerializerMethodField()
    period = serializers.CharField(source="snapshot.period", read_only=True)
    period_date = serializers.DateField(source="snapshot.period_date", read_only=True)

    def get_semaphore_code(self, obj):
        return obj.semaforo_raw.get("semaforo", {}).get("code")

    class Meta:
        model = SemaphoreRun
        fields = ["id", "snapshot_id", "period", "period_date", "ran_at", "semaphore_code", "semaforo_raw"]


class DividendConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = DividendConfig
        fields = [
            "id", "symbol", "amount_per_share", "interval_months",
            "start_date", "end_date", "tax_exempt", "notes",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        start = attrs.get("start_date") or (self.instance.start_date if self.instance else None)
        end = attrs.get("end_date") or (self.instance.end_date if self.instance else None)
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "end_date must be >= start_date."})
        return attrs
