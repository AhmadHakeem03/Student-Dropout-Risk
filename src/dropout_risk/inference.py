"""Turn one student's raw survey answers into model features and score them with the
Logistic Regression model.

Answers are processed exactly like the training data (`dropout_risk.data`):
- single-choice questions accept the English label ("Often"), the original Arabic answer ("غالبًا")
  or the integer code (3); text is normalised (case, whitespace, invisible characters) first
- the AI-tools question is a multi-select ("ChatGPT;Claude" or a list) -> one flag per tool
- the two free-text questions go through the same parsers as the survey text
The model pipeline then engineers features, selects them, scales them and predicts.
"""

from functools import cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .dashboard.catalog import ALL_FEATURES, BASE_FEATURES
from .data import (
    SURVEY_COLUMNS, TOOL_COLUMNS, _clean, _parse_gave_advice, _parse_learned_prompting, _parse_tools,
)

# public field name -> model feature name (fields not listed use the feature name itself)
FIELD_ALIASES = {
    "gender": "is_male",
    "degree": "degree_level",
    "residence": "residence_urbanity",
    "university_type": "is_private_university",
}
CHOICE_FIELDS = [
    ({v: k for k, v in FIELD_ALIASES.items()}.get(name, name), name) for name, _ in SURVEY_COLUMNS.values()
]
FEATURE_ORDER = [name for name, _ in SURVEY_COLUMNS.values()] + TOOL_COLUMNS + ["gave_advice", "learned_prompting"]
TOOL_OPTIONS = ["ChatGPT", "Google Gemini", "Claude", "Microsoft Copilot", "Other"]
_TOOL_ALIASES = {"gemini": "Google Gemini", "copilot": "Microsoft Copilot", "chat gpt": "ChatGPT"}


class InputError(ValueError):
    """Invalid survey answers. `errors` is a list of {field, message, allowed?}."""

    def __init__(self, errors: list[dict]):
        super().__init__("; ".join(f"{e['field']}: {e['message']}" for e in errors))
        self.errors = errors


def _norm(value) -> str:
    return _clean(value).lower()


# extra accepted spellings (short forms and earlier labels)
EXTRA_ALIASES = {
    "residence_urbanity": {"district": 1, "liwa": 1},
}


@cache
def _lookup(feature: str) -> dict[str, int]:
    """All accepted spellings of every answer to one question -> answer code."""
    arabic = next(m for name, m in SURVEY_COLUMNS.values() if name == feature)
    out = {_norm(text): code for text, code in arabic.items()} | EXTRA_ALIASES.get(feature, {})
    for code, label in BASE_FEATURES[feature].answers.items():
        out[_norm(label)] = code
        out[str(code)] = code
    return out


def encode_answers(answers: dict) -> pd.DataFrame:
    """Validate and encode one student's answers into the model's base-feature row."""
    errors, row = [], {}
    for field, feature in CHOICE_FIELDS:
        value = answers.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append({"field": field, "message": "answer is required",
                           "allowed": list(BASE_FEATURES[feature].answers.values())})
            continue
        key = str(int(value)) if isinstance(value, (int, np.integer)) and not isinstance(value, bool) else _norm(value)
        code = _lookup(feature).get(key)
        if code is None:
            errors.append({"field": field, "message": f"unknown answer {value!r}",
                           "allowed": list(BASE_FEATURES[feature].answers.values())})
        else:
            row[feature] = code

    tools = answers.get("ai_tools") or []
    if isinstance(tools, str):
        tools = tools.split(";")
    tools = [_TOOL_ALIASES.get(_norm(t), _clean(t)) for t in tools if _clean(t)]
    row |= _parse_tools(pd.Series([";".join(tools)])).iloc[0].astype(int).to_dict()
    row["gave_advice"] = int(_parse_gave_advice(pd.Series([answers.get("advice") or ""])).iloc[0])
    row["learned_prompting"] = int(_parse_learned_prompting(pd.Series([answers.get("learned_prompting") or ""])).iloc[0])

    if errors:
        raise InputError(errors)
    return pd.DataFrame([row])[FEATURE_ORDER]


def _describe(feature: str, value) -> str:
    """Readable text for an engineered/selected model feature and its value for this student."""
    if feature in ALL_FEATURES:
        f = ALL_FEATURES[feature]
        return f"{f.title}: {f.label(int(value))}"
    base, _, code = feature.rpartition("_")  # one-hot columns, e.g. professor_was_right_2
    if base in ALL_FEATURES and code.isdigit():
        f = ALL_FEATURES[base]
        return f"{f.title}: {'' if value else 'not '}{f.label(int(code))}"
    return f"{feature.replace('_', ' ')}: {value}"


class LogisticRegressionPredictor:
    """Wraps the trained Logistic Regression pipeline (outputs/models/logistic_regression.joblib)."""

    def __init__(self, model_path: str | Path, risk_bands: dict[str, float]):
        self.path = Path(model_path)
        if not self.path.exists():
            raise FileNotFoundError(f"{self.path} not found. Train the models first: uv run dropout-risk")
        self.pipeline = joblib.load(self.path)
        if type(self.pipeline.named_steps["model"]).__name__ != "LogisticRegression":
            raise TypeError(f"{self.path} does not contain a Logistic Regression model")
        self.risk_bands = risk_bands

    def _band(self, p: float) -> str:
        return "high" if p >= self.risk_bands["high"] else "medium" if p >= self.risk_bands["medium"] else "low"

    def predict(self, answers: dict, top_k: int = 5) -> dict:
        X = encode_answers(answers)
        steps = self.pipeline.named_steps
        Z = steps["select"].transform(steps["engineer"].transform(X))
        scaled = steps["scale"].transform(Z)[0]
        lr = steps["model"]
        contributions = lr.coef_[0] * scaled  # each feature's push on the log-odds of dropping
        proba = float(self.pipeline.predict_proba(X)[0, 1])
        factors = sorted(
            ({"factor": _describe(name, Z.iloc[0][name]), "feature": name, "impact": round(float(c), 3)}
             for name, c in zip(Z.columns, contributions)),
            key=lambda d: -abs(d["impact"]))
        return {
            "prediction": "Drop" if proba >= 0.5 else "No drop",
            "drop_probability": round(proba, 4),
            "risk_level": self._band(proba),
            "decision_threshold": 0.5,
            "model": "Logistic Regression",
            "factors_increasing_risk": [f for f in factors if f["impact"] > 0][:top_k],
            "factors_decreasing_risk": [f for f in factors if f["impact"] < 0][:top_k],
            "processed_input": {k: int(v) for k, v in X.iloc[0].items()},
        }


def form_schema() -> list[dict]:
    """Question list for building an input form (English labels)."""
    questions = [{"field": field, "title": BASE_FEATURES[feature].title, "group": BASE_FEATURES[feature].group,
                  "type": "choice", "options": list(BASE_FEATURES[feature].answers.values())}
                 for field, feature in CHOICE_FIELDS]
    questions.append({"field": "ai_tools", "title": "AI tools used", "group": "AI usage",
                      "type": "multi", "options": TOOL_OPTIONS})
    questions.append({"field": "learned_prompting", "title": "Has learned prompt writing", "group": "AI literacy",
                      "type": "choice", "options": ["Yes", "No", "Not sure"], "optional": True})
    questions.append({"field": "advice", "title": "Advice for using AI positively (free text)",
                      "group": "AI literacy", "type": "text", "optional": True})
    return questions
