from rest_framework import serializers
from .models import MonthlySnapshot, Holding, Dividend, Transaction


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
        if obj.semaforo_raw:
            return obj.semaforo_raw.get("semaforo", {}).get("code")
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
        if obj.semaforo_raw:
            return obj.semaforo_raw.get("semaforo", {}).get("code")
        return None
