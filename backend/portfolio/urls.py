from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import SnapshotViewSet, StockAnalyzerView, DividendConfigViewSet, SemaphoreRunViewSet

router = DefaultRouter()
router.register(r"snapshots", SnapshotViewSet, basename="snapshot")
router.register(r"dividend-configs", DividendConfigViewSet, basename="dividend-config")
router.register(r"semaphore-runs", SemaphoreRunViewSet, basename="semaphore-run")

urlpatterns = router.urls + [
    path("analyze/", StockAnalyzerView.as_view(), name="stock-analyze"),
]
