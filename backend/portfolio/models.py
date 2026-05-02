from django.db import models


class MonthlySnapshot(models.Model):
    period = models.CharField(max_length=30)        # "FEBRUARY - 2026"
    period_date = models.DateField(db_index=True)   # 2026-02-01 (for ordering)
    account_no = models.CharField(max_length=20)
    source_pdf_name = models.CharField(max_length=255)
    parsed_at = models.DateTimeField()

    total_value = models.DecimalField(max_digits=12, decimal_places=2)
    cash = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    dividend_income = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    realized_pnl_net = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    alpaca_raw = models.JSONField()
    markowitz_raw = models.JSONField(null=True, blank=True)
    semaforo_raw = models.JSONField(null=True, blank=True)
    advisor_report = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-period_date"]
        unique_together = ["account_no", "period_date"]

    def __str__(self):
        return f"{self.period} — ${self.total_value}"


class Holding(models.Model):
    snapshot = models.ForeignKey(
        MonthlySnapshot, on_delete=models.CASCADE, related_name="holdings"
    )
    symbol = models.CharField(max_length=10, db_index=True)
    description = models.CharField(max_length=200, blank=True)
    qty = models.DecimalField(max_digits=16, decimal_places=8)
    market_price = models.DecimalField(max_digits=10, decimal_places=2)
    market_value = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_basis = models.DecimalField(max_digits=10, decimal_places=2)
    unrealized_pnl = models.DecimalField(max_digits=10, decimal_places=2)
    pnl_pct = models.DecimalField(max_digits=8, decimal_places=2)
    weight = models.DecimalField(max_digits=6, decimal_places=2)
    target_weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    sharpe = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True)

    class Meta:
        unique_together = ["snapshot", "symbol"]

    def __str__(self):
        return f"{self.symbol} — {self.snapshot.period}"


class Dividend(models.Model):
    snapshot = models.ForeignKey(
        MonthlySnapshot, on_delete=models.CASCADE, related_name="dividends"
    )
    date = models.DateField()
    symbol = models.CharField(max_length=10, db_index=True)
    event_type = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        return f"{self.symbol} ${self.amount} — {self.date}"


class Transaction(models.Model):
    snapshot = models.ForeignKey(
        MonthlySnapshot, on_delete=models.CASCADE, related_name="transactions"
    )
    date = models.DateField()
    symbol = models.CharField(max_length=10, db_index=True)
    side = models.CharField(max_length=10)
    event_type = models.CharField(max_length=50, blank=True)
    qty = models.DecimalField(max_digits=16, decimal_places=8)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.side} {self.symbol} — {self.date}"


class SemaphoreRun(models.Model):
    snapshot = models.ForeignKey(
        MonthlySnapshot, on_delete=models.CASCADE, related_name="semaphore_runs"
    )
    ran_at = models.DateTimeField(auto_now_add=True)
    semaforo_raw = models.JSONField()

    class Meta:
        ordering = ["-ran_at"]

    def __str__(self):
        return f"{self.snapshot.period} — {self.ran_at:%Y-%m-%d %H:%M}"


class DividendConfig(models.Model):
    FREQ_CHOICES = [(1,"Mensual"),(2,"Bimestral"),(3,"Trimestral"),(6,"Semestral"),(12,"Anual")]

    symbol = models.CharField(max_length=10, db_index=True)
    amount_per_share = models.DecimalField(max_digits=10, decimal_places=6)
    interval_months = models.PositiveSmallIntegerField(default=3, choices=FREQ_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    tax_exempt = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["symbol", "start_date"]

    def __str__(self):
        return f"{self.symbol} ${self.amount_per_share}/sh every {self.interval_months}m from {self.start_date}"
