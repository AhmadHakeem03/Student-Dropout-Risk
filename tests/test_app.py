import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import app
from dropout_risk.config import load_config
from dropout_risk.data import load_dataset
from dropout_risk.inference import FEATURE_ORDER, InputError, encode_answers

client = TestClient(app)

ENGLISH = {
    "gender": "Female", "major": "Engineering & Tech", "degree": "Bachelor", "study_year": "4th year",
    "residence": "Capital", "university_type": "Public", "ever_used_ai": "Yes",
    "ai_study_frequency": "Always", "ai_replaces_research": "Often", "analytical_skills_effect": "Negative",
    "independent_learning": "Somewhat", "motivation_effect": "Reduces", "over_reliance": "Yes",
    "ai_cheating_view": "Depends on use", "submitted_full_project": "Yes", "reviews_content": "Sometimes",
    "content_errors": "Often", "used_ai_in_exam": "No", "saves_time": "Greatly", "flagged_by_professor": "Yes",
    "professor_was_right": "Partly", "detector_knowledge": "Average", "easy_to_detect": "Sometimes",
    "ai_improved_education": "Somewhat", "ai_replaces_search_engines": "Always",
    "ai_tools": ["ChatGPT", "Google Gemini"], "learned_prompting": "No", "advice": "",
}
model_ready = (load_config()["output_dir"] / "models" / "logistic_regression.joblib").exists()


def test_english_arabic_and_codes_encode_identically():
    arabic = {**ENGLISH, "gender": "انثى", "ai_study_frequency": "دائمًا", "motivation_effect": "تقلل الدافعية ",
              "over_reliance": "نعم", "ai_tools": "ChatGPT;Google Gemini;"}
    codes = {**ENGLISH, "gender": 0, "ai_study_frequency": 4, "motivation_effect": 0, "over_reliance": 2}
    a, b, c = encode_answers(ENGLISH), encode_answers(arabic), encode_answers(codes)
    pd.testing.assert_frame_equal(a, b)
    pd.testing.assert_frame_equal(a, c)
    assert list(a.columns) == FEATURE_ORDER
    row = a.iloc[0]
    assert row["uses_chatgpt"] == row["uses_gemini"] == 1 and row["uses_claude"] == 0
    assert row["learned_prompting"] == 0 and row["gave_advice"] == 0


def test_encoding_matches_training_pipeline_columns():
    X, _ = load_dataset(load_config())
    assert list(X.columns) == FEATURE_ORDER


def test_invalid_and_missing_answers_are_reported():
    bad = {**ENGLISH, "major": "Astrology"}
    del bad["gender"]
    with pytest.raises(InputError) as exc:
        encode_answers(bad)
    fields = {e["field"] for e in exc.value.errors}
    assert fields == {"major", "gender"}
    assert "Engineering & Tech" in next(e for e in exc.value.errors if e["field"] == "major")["allowed"]


def test_exactly_two_api_endpoints():
    api = sorted((r.path, sorted(r.methods)) for r in app.routes
                 if getattr(r, "path", "").startswith("/api/") and getattr(r, "include_in_schema", False))
    assert api == [("/api/dashboard", ["GET"]), ("/api/predict", ["POST"])]


@pytest.mark.skipif(not model_ready, reason="run `uv run dropout-risk` first")
def test_predict_endpoint():
    r = client.post("/api/predict", json=ENGLISH)
    assert r.status_code == 200
    body = r.json()
    assert 0 <= body["drop_probability"] <= 1 and body["model"] == "Logistic Regression"
    assert body["prediction"] in {"Drop", "No drop"} and body["risk_level"] in {"low", "medium", "high"}
    assert len(body["processed_input"]) == len(FEATURE_ORDER)
    assert body["factors_increasing_risk"] or body["factors_decreasing_risk"]

    safe = {**ENGLISH, "analytical_skills_effect": "Positive", "motivation_effect": "Increases", "over_reliance": "No",
            "submitted_full_project": "No", "flagged_by_professor": "No", "professor_was_right": "Never flagged",
            "ai_study_frequency": "Sometimes", "reviews_content": "Always", "independent_learning": "Yes"}
    assert client.post("/api/predict", json=safe).json()["drop_probability"] < body["drop_probability"]


def test_predict_rejects_bad_input():
    r = client.post("/api/predict", json={**ENGLISH, "study_year": "10th year"})
    assert r.status_code == 422 and r.json()["detail"][0]["field"] == "study_year"
    assert client.post("/api/predict", json={**ENGLISH, "unexpected": 1}).status_code == 422


def test_dashboard_endpoint_and_filters():
    d = client.get("/api/dashboard").json()
    assert d["summary"]["students"] == 800
    assert {s["title"] for s in d["sections"]} >= {"Demographics", "Learning impact", "Academic integrity"}
    f = client.get("/api/dashboard", params={"major": 2}).json()
    assert f["summary"]["students"] < 800 and f["filters"]["applied"] == {"major": 2}
    assert client.get("/api/dashboard", params={"major": 9}).status_code == 422


def test_dashboard_jordan_and_groups():
    d = client.get("/api/dashboard").json()
    j = d["jordan"]
    assert set(j) == {"university_type", "residence", "heatmaps"}  # survey data only
    sc = j["university_type"]["scorecard"]
    assert [g["label"] for g in sc["groups"]] == ["Public", "Private"]
    assert sum(g["n"] for g in sc["groups"]) == d["summary"]["students"]
    assert all(len(m["values"]) == 2 and all(0 <= v <= 1 for v in m["values"]) for m in sc["metrics"])
    assert "Capital" in [g["label"] for g in j["residence"]["scorecard"]["groups"]]
    assert len(j["heatmaps"]) == 4 and set(d["groups"]) == {"major", "study_year", "degree_level", "is_male"}


def test_ui_and_dashboard_never_mention_oversampling():
    page = client.get("/").text + client.get("/static/app.js").text
    payload = client.get("/api/dashboard").text
    for text in (page.lower(), payload.lower()):
        assert "smote" not in text and "synthetic" not in text and "augment" not in text
    assert "__FORM_SCHEMA__" not in page
