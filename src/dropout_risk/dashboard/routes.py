"""FastAPI routers: a JSON API router and a UI router that serves the dashboards."""

import io
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse

from .schemas import Breakdown, PredictRequest, PredictResponse
from .service import BANDS, SOURCES, DashboardService, NotReadyError

STATIC_DIR = Path(__file__).parent / "static"

SourceQ = Query(None, description=f"Data source: {', '.join(SOURCES)} (default from config)")
FiltersQ = Query([], description="Segment filters as '<feature>:<code>', repeatable. "
                                 "Same feature twice = OR, different features = AND.")


def build_api_router(service: DashboardService) -> APIRouter:
    router = APIRouter(tags=["dropout-dashboards"])

    def src(source: str | None) -> str:
        return source or service.dcfg["default_source"]

    def call(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except NotReadyError as e:
            raise HTTPException(503, str(e)) from e
        except (ValueError, KeyError) as e:
            raise HTTPException(422, str(e)) from e

    def filters(f: list[str]) -> dict:
        return call(service.parse_filters, f)

    @router.get("/meta", summary="Data dictionary, sources, filters and settings")
    def meta():
        return service.meta()

    @router.get("/kpis", summary="Headline numbers for a source/segment")
    def kpis(source: str | None = SourceQ, f: list[str] = FiltersQ):
        return call(service.kpis, src(source), filters(f))

    @router.get("/breakdown/{feature}", response_model=Breakdown,
                summary="Drop share and lift for every answer to one question")
    def breakdown(feature: str, source: str | None = SourceQ, f: list[str] = FiltersQ):
        return call(service.breakdown, feature, src(source), filters(f))

    @router.get("/breakdowns", response_model=list[Breakdown], summary="Breakdowns for a question group")
    def breakdowns(group: str, source: str | None = SourceQ, f: list[str] = FiltersQ):
        return call(service.breakdowns, group, src(source), filters(f))

    @router.get("/profile/{feature}", summary="Answer distribution of drop vs no-drop students")
    def profile(feature: str, source: str | None = SourceQ, f: list[str] = FiltersQ):
        return call(service.profile, feature, src(source), filters(f))

    @router.get("/crosstab", summary="Drop share for every combination of two questions")
    def crosstab(row: str, col: str, source: str | None = SourceQ, f: list[str] = FiltersQ):
        return call(service.crosstab, row, col, src(source), filters(f))

    @router.get("/tools", summary="AI tool adoption by class")
    def tools(source: str | None = SourceQ, f: list[str] = FiltersQ):
        return call(service.tools, src(source), filters(f))

    @router.get("/risk-signals", summary="Answers ranked by drop-risk lift")
    def risk_signals(source: str | None = SourceQ, f: list[str] = FiltersQ,
                     limit: int | None = Query(None, ge=1), min_n: int | None = Query(None, ge=1)):
        return call(service.risk_signals, src(source), filters(f), limit, min_n)

    @router.get("/data-quality", summary="Real vs synthetic (SMOTEN) comparison")
    def data_quality():
        return call(service.data_quality)

    @router.get("/data-quality/{feature}", summary="Real vs synthetic answer shares for one question")
    def compare(feature: str):
        return call(service.compare_distribution, feature)

    @router.get("/model/performance", summary="CV and test metrics, ROC curves, confusion matrices")
    def performance():
        return call(lambda: service.performance)

    @router.get("/model/importance", summary="Permutation importance and feature selection")
    def importance():
        return call(service.importance)

    @router.get("/watchlist", summary="Surveyed students ranked by predicted drop probability")
    def watchlist(f: list[str] = FiltersQ, limit: int | None = Query(None, ge=1, le=500),
                  band: Literal["low", "medium", "high"] | None = None):
        return call(service.watchlist, filters(f), limit, band)

    @router.post("/predict", response_model=PredictResponse, summary="Score one student's answers")
    def predict(body: PredictRequest):
        return call(service.predict, body.answers)

    @router.get("/dataset", summary="Export rows (JSON or CSV) for BI tools")
    def dataset(source: str | None = SourceQ, f: list[str] = FiltersQ,
                decoded: bool = Query(True, description="Return answer labels instead of codes"),
                format: Literal["json", "csv"] = "json"):
        df = call(service.dataset, src(source), filters(f), decoded)
        if format == "csv":
            buf = io.StringIO()
            df.to_csv(buf, index=False)
            return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                     headers={"Content-Disposition": f"attachment; filename={src(source)}.csv"})
        return json.loads(df.to_json(orient="records"))

    return router


def build_ui_router(api_base: str, ui_base: str) -> APIRouter:
    """Serves the dashboard shell with the API location injected, so it works under any prefix."""
    router = APIRouter(include_in_schema=False)
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("__API_BASE__", api_base).replace("__STATIC_BASE__", f"{ui_base}/static")

    @router.get("/", response_class=HTMLResponse)
    def index():
        return html

    return router


__all__ = ["build_api_router", "build_ui_router", "BANDS", "STATIC_DIR"]
