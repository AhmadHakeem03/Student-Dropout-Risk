import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dropout_risk.config import load_config
from dropout_risk.dashboard import include_dashboards


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    include_dashboards(app, api_prefix="/custom/api", ui_prefix="/custom/ui")  # non-default prefixes on purpose
    return TestClient(app)


@pytest.fixture(scope="module")
def model_ready():
    return (load_config()["output_dir"] / "best_model.joblib").exists()


def test_ui_is_served_with_injected_paths(client):
    r = client.get("/custom/ui/")
    assert r.status_code == 200
    assert 'content="/custom/api"' in r.text and "/custom/ui/static/js/app.js" in r.text
    assert client.get("/custom/ui/static/js/app.js").status_code == 200


def test_meta_lists_sources_and_features(client):
    m = client.get("/custom/api/meta").json()
    assert {s["id"] for s in m["sources"]} == {"augmented", "synthetic", "original"}
    rows = {s["id"]: s["rows"] for s in m["sources"]}
    assert rows["original"] == 183 and rows["augmented"] == 800
    assert "drop_risk_score" not in {f["name"] for f in m["features"]}


def test_kpis_default_source_is_augmented_and_balanced(client):
    k = client.get("/custom/api/kpis").json()
    assert k["rows"] == 800 and k["drop_share"] == 0.5


def test_breakdown_counts_add_up_and_filters_apply(client):
    bd = client.get("/custom/api/breakdown/major", params={"source": "original"}).json()
    assert sum(a["n"] for a in bd["answers"]) == bd["rows_total"] == 183
    filtered = client.get("/custom/api/breakdown/study_year",
                          params={"source": "original", "f": ["major:0", "major:1"]}).json()
    assert filtered["rows_total"] == 145  # engineering (115) + science (30)


@pytest.mark.parametrize("path,params", [
    ("/breakdown/not_a_question", {}),
    ("/kpis", {"source": "nope"}),
    ("/kpis", {"f": "major"}),
])
def test_bad_input_returns_422(client, path, params):
    assert client.get("/custom/api" + path, params=params).status_code == 422


def test_risk_signals_are_ranked_and_respect_min_n(client):
    s = client.get("/custom/api/risk-signals", params={"source": "original", "min_n": 15}).json()
    lifts = [r["lift"] for r in s["risk"]]
    assert lifts == sorted(lifts, reverse=True) and all(r["n"] >= 15 for r in s["risk"] + s["protective"])


def test_crosstab_tools_profile_quality(client):
    ct = client.get("/custom/api/crosstab", params={"row": "major", "col": "study_year"}).json()
    assert len(ct["drop_share"]) == len(ct["row_labels"])
    assert len(client.get("/custom/api/tools").json()["tools"]) == 5
    prof = client.get("/custom/api/profile/ai_dependency_index").json()
    assert all(abs(sum(s["shares"]) - 1) < 1e-3 for s in prof["series"])
    q = client.get("/custom/api/data-quality").json()
    assert q["rows_real"] + q["rows_synthetic"] == 800


def test_dataset_export_csv_and_json(client):
    r = client.get("/custom/api/dataset", params={"source": "original", "format": "csv"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert len(r.text.strip().splitlines()) == 184
    rows = client.get("/custom/api/dataset", params={"source": "original", "f": "is_male:1"}).json()
    assert rows and all(r["is_male"] == "Male" for r in rows)


def test_predict_watchlist_performance(client, model_ready):
    if not model_ready:
        pytest.skip("run `uv run dropout-risk` first")
    low = client.post("/custom/api/predict", json={"answers": {}}).json()
    high = client.post("/custom/api/predict", json={"answers": {
        "analytical_skills_effect": 0, "motivation_effect": 0, "over_reliance": 2,
        "flagged_by_professor": 1, "submitted_full_project": 1, "used_ai_in_exam": 1}}).json()
    assert 0 <= low["probability"] <= 1 and high["probability"] > low["probability"]
    assert high["band"] == "high" and high["what_would_reduce_risk"]
    assert client.post("/custom/api/predict", json={"answers": {"over_reliance": 9}}).status_code == 422

    wl = client.get("/custom/api/watchlist", params={"limit": 10}).json()
    probs = [s["probability"] for s in wl["students"]]
    assert probs == sorted(probs, reverse=True) and sum(wl["band_counts"].values()) == 183

    perf = client.get("/custom/api/model/performance").json()
    assert len(perf["models"]) == 5 and all("roc" in m for m in perf["models"])
    assert client.get("/custom/api/model/importance").json()["permutation"]
