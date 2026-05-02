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
        run = obj.semaphore_runs.first()  # ordered by -ran_at
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
        run = obj.semaphore_runs.first()  # ordered by -ran_at
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
        fields = "__all__"
