"""Student Dropout Risk — web app.

Two API endpoints:
    POST /api/predict     score one student's survey answers with the Logistic Regression model
    GET  /api/dashboard   all dashboard data (optional filters: major, study_year, gender, university_type)

UI:  GET /  (risk check form + dashboards)        API docs: /docs

Run:
    uv run python app.py
    uv run uvicorn app:app --reload
"""

import json
from functools import cache
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from dropout_risk.config import load_config
from dropout_risk.dashboard.catalog import BASE_FEATURES, GROUPS
from dropout_risk.dashboard.service import DashboardService
from dropout_risk.inference import InputError, LogisticRegressionPredictor, form_schema

WEB_DIR = Path(__file__).parent / "web"
DATASET = "augmented"  # the training dataset the dashboards describe
CFG = load_config()

app = FastAPI(
    title="Student Dropout Risk",
    description="Predict a student's dropout risk from survey answers and explore the dashboards.",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@cache
def predictor() -> LogisticRegressionPredictor:
    return LogisticRegressionPredictor(Path(CFG["output_dir"]) / "models" / "logistic_regression.joblib",
                                       CFG["dashboard"]["risk_bands"])


@cache
def analytics() -> DashboardService:
    return DashboardService(CFG)


# --- request / response models -------------------------------------------------------------------
Answer = str | int

class StudentAnswers(BaseModel):
    """One student's survey answers. Single-choice answers accept the English label, the original
    Arabic answer, or the answer code."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{
        "gender": "Female", "major": "Engineering & Tech", "degree": "Bachelor", "study_year": "4th year",
        "residence": "Capital", "university_type": "Public", "ever_used_ai": "Yes",
        "ai_study_frequency": "Always", "ai_replaces_research": "Often",
        "analytical_skills_effect": "Negative", "independent_learning": "Somewhat",
        "motivation_effect": "Reduces", "over_reliance": "Yes", "ai_cheating_view": "Depends on use",
        "submitted_full_project": "Yes", "reviews_content": "Sometimes", "content_errors": "Often",
        "used_ai_in_exam": "No", "saves_time": "Greatly", "flagged_by_professor": "Yes",
        "professor_was_right": "Partly", "detector_knowledge": "Average", "easy_to_detect": "Sometimes",
        "ai_improved_education": "Somewhat", "ai_replaces_search_engines": "Always",
        "ai_tools": ["ChatGPT", "Google Gemini"], "learned_prompting": "No", "advice": "",
    }]})

    gender: Answer
    major: Answer
    degree: Answer
    study_year: Answer
    residence: Answer
    university_type: Answer
    ever_used_ai: Answer
    ai_study_frequency: Answer
    ai_replaces_research: Answer
    analytical_skills_effect: Answer
    independent_learning: Answer
    motivation_effect: Answer
    over_reliance: Answer
    ai_cheating_view: Answer
    submitted_full_project: Answer
    reviews_content: Answer
    content_errors: Answer
    used_ai_in_exam: Answer
    saves_time: Answer
    flagged_by_professor: Answer
    professor_was_right: Answer
    detector_knowledge: Answer
    easy_to_detect: Answer
    ai_improved_education: Answer
    ai_replaces_search_engines: Answer
    ai_tools: list[str] | str = Field(default_factory=list, description='List or ";"-separated tool names')
    learned_prompting: str = Field("", description="Free text or Yes / No")
    advice: str = Field("", description="Free-text advice on using AI positively")


class Factor(BaseModel):
    factor: str
    feature: str
    impact: float = Field(description="Contribution to the log-odds of dropping (positive = raises risk)")


class Prediction(BaseModel):
    prediction: str
    drop_probability: float
    risk_level: str
    decision_threshold: float
    model: str
    factors_increasing_risk: list[Factor]
    factors_decreasing_risk: list[Factor]
    processed_input: dict[str, int]


# --- API -----------------------------------------------------------------------------------------
@app.post("/api/predict", response_model=Prediction, tags=["api"],
          summary="Predict dropout risk for one student (Logistic Regression)")
def predict(answers: StudentAnswers):
    try:
        model = predictor()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e
    try:
        return model.predict(answers.model_dump())
    except InputError as e:
        raise HTTPException(422, e.errors) from e


@app.get("/api/dashboard", tags=["api"], summary="Dashboard data, optionally filtered by segment")
def dashboard(
    major: Annotated[int | None, Query(description="Major code (see filters in the response)")] = None,
    study_year: Annotated[int | None, Query()] = None,
    gender: Annotated[int | None, Query(description="0 = Female, 1 = Male")] = None,
    university_type: Annotated[int | None, Query(description="0 = Public, 1 = Private")] = None,
):
    svc = analytics()
    chosen = {"major": major, "study_year": study_year, "is_male": gender, "is_private_university": university_type}
    filters = {}
    for feature, code in chosen.items():
        if code is None:
            continue
        if code not in BASE_FEATURES[feature].answers:
            raise HTTPException(422, f"Invalid code {code} for {feature}. Valid: {list(BASE_FEATURES[feature].answers)}")
        filters[feature] = [code]

    k = svc.kpis(DATASET, filters)
    sections = []
    for group in GROUPS:
        charts = [b for b in svc.breakdowns(group, DATASET, filters) if not b["feature"].startswith("uses_")]
        sections.append({"id": group.lower().replace(" ", "-"), "title": group, "charts": charts})
    return {
        "filters": {
            "applied": {k_: v[0] for k_, v in filters.items()},
            "options": {name: [{"code": c, "label": l} for c, l in BASE_FEATURES[feat].answers.items()]
                        for name, feat in (("major", "major"), ("study_year", "study_year"),
                                           ("gender", "is_male"), ("university_type", "is_private_university"))},
        },
        "summary": {"students": k["rows"], "drop_count": k["drop_count"],
                    "no_drop_count": k["rows"] - k["drop_count"], "drop_share": k["drop_share"]},
        "key_signals": svc.risk_signals(DATASET, filters, limit=8),
        "heatmap": svc.crosstab("major", "study_year", DATASET, filters),
        "tools": svc.tools(DATASET, filters)["tools"],
        "profiles": [svc.profile(n, DATASET, filters) for n in
                     ("ai_dependency_index", "integrity_risk_count", "negative_impact_count", "ai_literacy")],
        "sections": sections,
        "jordan": _jordan(svc, filters),
        "groups": {name: svc.scorecard(name, DATASET, filters) for name in ("major", "study_year", "degree_level", "is_male")},
        "model": _model_card(),
    }


def _jordan(svc: DashboardService, filters: dict) -> dict:
    """University-type and residence views of the dataset."""
    return {
        "university_type": {"breakdown": svc.breakdown("is_private_university", DATASET, filters),
                            "scorecard": svc.scorecard("is_private_university", DATASET, filters)},
        "residence": {"breakdown": svc.breakdown("residence_urbanity", DATASET, filters),
                      "scorecard": svc.scorecard("residence_urbanity", DATASET, filters)},
        "heatmaps": [svc.crosstab(r, c, DATASET, filters) for r, c in (
            ("major", "is_private_university"), ("residence_urbanity", "is_private_university"),
            ("study_year", "is_private_university"), ("residence_urbanity", "major"))],
    }


@cache
def _model_card() -> dict | None:
    path = Path(CFG["output_dir"]) / "model_results.csv"
    if not path.exists():
        return None
    r = pd.read_csv(path).set_index("model").loc["logistic_regression"]
    metrics = ("f1", "roc_auc", "recall", "precision", "accuracy")
    return {"name": "Logistic Regression",
            "test": {m: round(float(r[f"test_{m}"]), 3) for m in metrics},
            "cross_validation": {m: round(float(r[f"cv_{m}"]), 3) for m in metrics}}


# --- UI ------------------------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def ui():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    return html.replace("__FORM_SCHEMA__", json.dumps({"groups": GROUPS, "questions": form_schema()}))


@app.exception_handler(InputError)
def _input_error(_, exc: InputError):  # safety net if InputError escapes elsewhere
    return JSONResponse(status_code=422, content={"detail": exc.errors})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=CFG["dashboard"]["host"], port=CFG["dashboard"]["port"])
