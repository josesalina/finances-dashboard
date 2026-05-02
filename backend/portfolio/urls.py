from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import SnapshotViewSet, StockAnalyzerView

router = DefaultRouter()
router.register(r"snapshots", SnapshotViewSet, basename="snapshot")

urlpatterns = router.urls + [
    path("analyze/", StockAnalyzerView.as_view(), name="stock-analyze"),
]
