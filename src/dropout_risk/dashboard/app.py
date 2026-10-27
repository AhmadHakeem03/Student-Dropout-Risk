"""Plug the dashboards into any FastAPI app, or run them standalone.

    # existing app
    from dropout_risk.dashboard import include_dashboards
    include_dashboards(app, api_prefix="/api/dropout", ui_prefix="/dashboards")

    # standalone
    uv run dropout-dashboard          # http://127.0.0.1:8000/dashboards/
"""

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from ..config import load_config
from .routes import STATIC_DIR, build_api_router, build_ui_router
from .service import DashboardService


def include_dashboards(app: FastAPI, api_prefix: str = "/api/dropout", ui_prefix: str = "/dashboards",
                       cfg: dict | None = None) -> DashboardService:
    """Register the JSON API under `api_prefix` and the dashboards under `ui_prefix`.
    Returns the service so the host app can reuse it (e.g. in its own endpoints)."""
    service = DashboardService(cfg or load_config())
    app.include_router(build_api_router(service), prefix=api_prefix)
    app.include_router(build_ui_router(api_prefix, ui_prefix), prefix=ui_prefix)
    app.mount(f"{ui_prefix}/static", StaticFiles(directory=STATIC_DIR), name="dropout-dashboard-static")
    return service


def create_app(cfg: dict | None = None) -> FastAPI:
    app = FastAPI(title="Dropout Risk Dashboards",
                  description="Decision dashboards and JSON API over the SMOTE-augmented survey data.")
    include_dashboards(app, cfg=cfg)

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/dashboards/")

    return app


def main() -> None:
    import uvicorn

    cfg = load_config()
    print(f"Dashboards: http://{cfg['dashboard']['host']}:{cfg['dashboard']['port']}/dashboards/  "
          f"| API docs: /docs")
    uvicorn.run(create_app(cfg), host=cfg["dashboard"]["host"], port=cfg["dashboard"]["port"])


if __name__ == "__main__":
    main()
