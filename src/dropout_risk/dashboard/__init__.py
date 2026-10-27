"""Decision dashboards + JSON API for the dropout-risk data, pluggable into any FastAPI app."""

from .app import create_app, include_dashboards
from .service import DashboardService

__all__ = ["create_app", "include_dashboards", "DashboardService"]
