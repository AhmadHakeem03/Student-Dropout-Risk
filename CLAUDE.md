# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

This project predicts student **dropout risk** from an Arabic-language survey about how university
students use generative-AI text tools. The data is `data/The effect of using AI.xlsx`, sheet
`Sheet1`: 183 respondents and 35 columns. The target is `Drop_Class_Label` (1 = drop, 27% of
respondents).

It has three parts, all in one uv project (Python 3.12, package `dropout_risk` in `src/`):

1. **Training pipeline** (`uv run dropout-risk`). It:
   - encodes the survey
   - makes a stratified train/test split
   - oversamples with **SMOTEN** inside an imblearn pipeline
   - engineers features, then selects them
   - tunes five models: Logistic Regression, Decision Tree, Random Forest, CatBoost and XGBoost
   - picks the best by **CV F1**

   It writes `outputs/`. The current winner is Logistic Regression; `outputs/report.md` holds
   the numbers.
2. **`app.py` (root)**: the main web app. It has exactly two API endpoints:
   - `POST /api/predict` uses the Logistic Regression model.
   - `GET /api/dashboard` returns the dashboard data.

   The brand-styled UI in `web/` is served at `/`.
3. **`dropout_risk.dashboard`**: a separate, pluggable multi-endpoint dashboard API plus ten
   dashboards. Add it to any app with `include_dashboards(app, api_prefix, ui_prefix)`, or run it
   standalone with `uv run dropout-dashboard`.

## Commands

```powershell
uv sync                                    # install deps
uv run dropout-risk                        # train + evaluate -> outputs/ (~2 min)
uv run python scripts/generate_synthetic_data.py   # write data/processed/*.csv
uv run python app.py                       # web app: http://127.0.0.1:8000/ (API docs at /docs)
uv run uvicorn app:app --reload --port 8010
uv run dropout-dashboard                   # dashboard package: http://127.0.0.1:8000/dashboards/
uv run pytest                              # all tests
uv run pytest tests/test_app.py::test_predict_endpoint   # single test
uv run jupyter nbconvert --to notebook --execute --inplace notebooks/01_synthetic_data_smote.ipynb
```

Windows specifics:
- **Locked scripts:** if `uv run` fails with "failed to remove … dropout-dashboard.exe" (or
  `dropout-risk.exe`), that console script is still running. Use `uv run --no-sync …` or stop it.
- **Arabic output:** set `$env:PYTHONIOENCODING="utf-8"` before printing Arabic to the console.
- **Shared port:** both web apps default to port 8000 (`config.yaml → dashboard.port`), so run
  only one at a time.

There is no linter or formatter configured.

## Architecture: how the pieces connect

- **Artifacts are the contract between training and serving.** Both web layers read files instead
  of training anything:
  - `data/processed/*.csv` is written by `synthetic.write_processed_datasets`. `DashboardService`
    regenerates these files automatically if they're missing.
  - `outputs/models/<model>.joblib`, `outputs/best_model.joblib`, `outputs/model_results.csv`,
    `permutation_importance.csv` and `feature_selection.csv` are written by `main.py`. Without
    them, the model endpoints return 503.

  Retraining changes what the apps serve. Results are deterministic via `random_state`.
- **Saved pipelines take encoded base features.** Each pipeline is an imblearn `Pipeline`:
  `smoten → engineer (FunctionTransformer) → select (ColumnSelector) → [scale] → model`. Its input
  is the 32 integer-coded base columns produced by `data.encode_survey`, in
  `inference.FEATURE_ORDER`. SMOTEN only acts during `fit`. Engineering and selection happen inside
  the pipeline, so never pass engineered features in.
- **Answer codes are defined in two places that must stay in sync:**
  - `data.SURVEY_COLUMNS` maps the raw Arabic answers to codes. It is position-based, because the
    Arabic headers contain newlines and non-breaking spaces; the layout is validated on load.
  - `dashboard/catalog.py` maps codes to English titles and labels, plus groups and an
    `actionable` flag.

  `inference.py` builds its accepted-answer lookups from both: English label, Arabic answer, or
  code. Adding or changing a question means editing both files.
- **`DashboardService` (`dashboard/service.py`) holds all analytics**, in pandas only. `app.py` and
  the dashboard package's `routes.py` are thin wrappers over it. Routes map `ValueError` → 422 and
  `NotReadyError` → 503. Data sources are `augmented` (real training rows + SMOTEN rows, 800),
  `synthetic` and `original` (183).
- **`inference.LogisticRegressionPredictor`** explains each prediction with per-feature log-odds
  contributions (`coef_ × scaled value`). The LR probabilities saturate near 0 or 1. The UI shows
  ">99.9%", and the dashboard simulator ranks changes by log-odds, not probability.

## Rules (several are enforced by tests)

- Use only the user's survey data. Never add outside data (national statistics, web sources,
  reference figures) to dashboards, labels or payloads.

- `Drop_Risk_Score` is never a feature. The label is 1 exactly when it is ≥ 5 (target leakage).
- Split **before** resampling. The test set is never resampled and is used once for the final
  report. Model selection uses CV scores only.
- Use SMOTEN, not SMOTE. Base features are category codes, and interpolating them invents answers
  that don't exist. Feature engineering is row-wise and stateless, and runs after SMOTEN. Feature
  selection is fitted on real training rows only.
- Unknown survey answers raise an error. Extend the mapping dicts; never coerce silently.
- `app.py` has **exactly two** `/api/*` endpoints. The form schema reaches the UI through
  `__FORM_SCHEMA__` injection into `web/index.html`, not through an endpoint.
- The `app.py` UI and the `/api/dashboard` payload must **never** mention SMOTE, synthetic or
  augmented data. The dashboards there use the augmented set (50/50 by construction), so present
  drop shares relative to the average line.
- In the dashboard package's JS, never hard-code API paths: use `static/js/api.js` (the base is
  injected via `<meta name="api-base">`).
- Treat `Drop_Class_Label` as real observed data in all code, comments and docs. Don't describe it
  as rule-based or a proxy.

## Styling: the two UIs use different palettes on purpose

- `web/` (app.py) uses only the brand palette: `#DBCC23` accent (= drop/risk), `#20211D` ink,
  `#F7F6F0` page, `#FFFFFF` surface and `#74756C` muted (= no drop / below average). Other
  colours are transparent tints of these.
- `dashboard/static/` uses CSS tokens from the dataviz reference palette, with light and dark
  themes. "No drop" is blue, "Drop" is orange, and risk bands are status colours, always shown
  with an icon and a label.

Both UIs load a vendored Plotly 2.35.3 (`web/vendor/`, `dashboard/static/vendor/`), so they work
offline. Don't switch back to a CDN: cdnjs's 2.35.2 `plotly.min.js` returns 404, and that once left
every chart blank. Charts sit in auto-fit grids that are filled card by card, so `draw()` observes
each chart and re-lays out its **width only** (`Plotly.relayout(el, {width})`). `Plots.resize`
would collapse the explicit heights.
