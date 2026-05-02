from django.contrib import admin
from .models import MonthlySnapshot, Holding, Dividend, Transaction


class HoldingInline(admin.TabularInline):
    model = Holding
    extra = 0
    readonly_fields = ["symbol", "qty", "market_value", "weight", "unrealized_pnl", "pnl_pct"]


@admin.register(MonthlySnapshot)
class SnapshotAdmin(admin.ModelAdmin):
    list_display = ["period", "total_value", "cash", "dividend_income", "created_at"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [HoldingInline]


@admin.register(Holding)
class HoldingAdmin(admin.ModelAdmin):
    list_display = ["symbol", "snapshot", "market_value", "weight", "pnl_pct"]
    list_filter = ["snapshot"]


admin.site.register(Dividend)
admin.site.register(Transaction)
