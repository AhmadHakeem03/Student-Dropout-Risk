"""Request/response models for the endpoints whose shape clients most depend on."""

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    answers: dict[str, int] = Field(
        default_factory=dict,
        description="Survey answer codes keyed by question name (see GET /meta). "
                    "Missing questions default to the most common answer.",
        examples=[{"over_reliance": 2, "motivation_effect": 0, "ai_study_frequency": 4}],
    )


class Driver(BaseModel):
    feature: str
    question: str
    current: str
    suggested: str
    probability_if_changed: float
    reduction: float


class PredictResponse(BaseModel):
    probability: float
    band: str
    risk_bands: dict[str, float]
    answers_used: dict[str, int]
    model: str
    what_would_reduce_risk: list[Driver]


class BreakdownAnswer(BaseModel):
    code: int
    label: str
    n: int
    drop: int
    drop_share: float | None
    pct_of_rows: float | None
    lift: float | None


class Breakdown(BaseModel):
    feature: str
    title: str
    group: str
    description: str
    overall_drop_share: float | None
    rows_total: int
    answers: list[BreakdownAnswer]
