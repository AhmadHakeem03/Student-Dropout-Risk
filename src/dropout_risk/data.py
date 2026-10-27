"""Load the raw survey and encode every answer as an integer code.

Raw headers are Arabic questions containing newlines and non-breaking spaces, so columns are
mapped by position and the layout is validated on load.
"""

import re
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

TARGET = "drop_label"

# --- answer scales -------------------------------------------------------------------------------
FREQUENCY = {"أبدًا": 0, "نادرًا": 1, "أحيانًا": 2, "غالبًا": 3, "كثيرًا": 3, "دائمًا": 4}
YES_NO = {"لا": 0, "نعم": 1}
NO_PARTLY_YES = {"لا": 0, "إلى حد ما": 1, "نعم": 2}
NO_SOMETIMES_YES = {"لا": 0, "أحيانًا": 1, "نعم": 2}

# position in the raw sheet -> (english name, answer mapping). Columns not listed are dropped:
# Id, start/end timestamps, email ("anonymous"), name (empty), and Drop_Risk_Score (the label is
# 1 exactly when this score is >= 5, so using it as a feature would leak the target). The AI-tools
# and free-text columns are handled by dedicated parsers below.
SURVEY_COLUMNS: dict[int, tuple[str, dict]] = {
    5: ("is_male", {"انثى": 0, "ذكر": 1}),
    6: ("major", {"تخصصات هندسية وتقنية": 0, "تخصصات علمية": 1, "تخصصات طبية": 2,
                  "تخصصات أدبية/إنسانية": 3, "أخرى": 4}),
    7: ("degree_level", {"دبلوم": 0, "بكالوريوس": 1, "ماجستير": 2, "دكتوراه": 3}),
    8: ("study_year", {"الأولى": 1, "الثانية": 2, "الثالثة": 3, "الرابعة": 4, "الخامسة فأعلى": 5}),
    9: ("residence_urbanity", {"قرية": 0, "لواء": 1, "محافظة": 2, "العاصمة": 3}),
    10: ("is_private_university", {"حكومية": 0, "خاصة": 1}),
    11: ("ever_used_ai", YES_NO),
    12: ("ai_study_frequency", FREQUENCY),
    13: ("ai_replaces_research", FREQUENCY),
    14: ("analytical_skills_effect", {"تأثرت بشكل سلبي": 0, "لم تتأثر": 1, "تأثرت بشكل إيجابي": 2}),
    15: ("independent_learning", NO_PARTLY_YES),
    16: ("motivation_effect", {"تقلل الدافعية": 0, "لا تؤثر": 1, "تزيد الدافعية": 2}),
    17: ("over_reliance", NO_SOMETIMES_YES),
    18: ("ai_cheating_view", {"لا": 0, "يعتمد على طريقة الاستخدام": 1, "نعم": 2}),
    19: ("submitted_full_project", YES_NO),
    20: ("reviews_content", {"لا": 0, "أحيانًا": 1, "دائمًا": 2}),
    21: ("content_errors", FREQUENCY),
    22: ("used_ai_in_exam", YES_NO),
    23: ("saves_time", {"لا": 0, "إلى حد ما": 1, "نعم بشكل كبير": 2}),
    24: ("flagged_by_professor", YES_NO),
    25: ("professor_was_right", {'أجبت السؤال السابق ب"لا"': 0, "لا": 1, "جزئيًا": 2, "نعم": 3}),
    26: ("detector_knowledge", {"ضعيفة": 0, "متوسطة": 1, "جيدة": 2, "ممتازة": 3}),
    27: ("easy_to_detect", NO_SOMETIMES_YES),
    29: ("ai_improved_education", NO_PARTLY_YES),
    30: ("ai_replaces_search_engines", FREQUENCY),
}
TOOLS_COL, ADVICE_COL, PROMPTING_COL = 28, 31, 32
LABEL_COL = 34

TOOL_FLAGS = {
    "uses_chatgpt": {"chatgpt"},
    "uses_gemini": {"google gemini"},
    "uses_claude": {"claude"},
    "uses_copilot": {"microsoft copilot"},
}
OTHER_TOOL_FLAG = "uses_other_tool"
TOOL_COLUMNS = [*TOOL_FLAGS, OTHER_TOOL_FLAG]

# nominal columns: one-hot encoded during feature engineering, never treated as ordered
NOMINAL_COLUMNS = {
    "major": [0, 1, 2, 3, 4],
    "learned_prompting": [0, 1, 2],  # 0 = no, 1 = yes, 2 = unclear / no real answer
    "professor_was_right": [0, 1, 2, 3],
}


def _clean(value) -> str:
    """Normalise whitespace/invisible characters in a raw answer."""
    text = "" if pd.isna(value) else str(value)
    text = text.replace("\xa0", " ").replace("‏", "").replace("‎", "")
    return re.sub(r"\s+", " ", text).strip()


def _map(series: pd.Series, mapping: dict, name: str) -> pd.Series:
    cleaned = series.map(_clean)
    unknown = sorted(set(cleaned) - set(mapping))
    if unknown:
        raise ValueError(f"Unmapped answers in '{name}': {unknown}. Extend the mapping in data.py.")
    return cleaned.map(mapping).astype(int)


def _parse_tools(series: pd.Series) -> pd.DataFrame:
    """Multi-select 'ChatGPT;Google Gemini;' -> one binary column per tool."""
    chosen = series.map(lambda v: {t.strip().lower() for t in _clean(v).split(";") if t.strip()})
    known = set().union(*TOOL_FLAGS.values())
    out = {flag: chosen.map(lambda s, names=names: int(bool(s & names)))
           for flag, names in TOOL_FLAGS.items()}
    out[OTHER_TOOL_FLAG] = chosen.map(lambda s: int(bool(s - known)))
    return pd.DataFrame(out, index=series.index)


_HAS_WORDS = re.compile(r"[A-Za-z؀-ۿ]{3,}")


def _parse_gave_advice(series: pd.Series) -> pd.Series:
    """Free-text tips question: 1 if the respondent wrote something real (not '.', '-', ...)."""
    return series.map(lambda v: int(bool(_HAS_WORDS.search(_clean(v))))).astype(int)


_YES = re.compile(r"^(نعم|اه|يس|yes|yed|sometimes yes|بحثت|حضرت|تعلمت|prompt)", re.IGNORECASE)
_NO = re.compile(r"^(لا|لأ|ل$|لم |ليس|no\b|0$)", re.IGNORECASE)


def _parse_learned_prompting(series: pd.Series) -> pd.Series:
    """Messy free-text yes/no about learning prompting -> 0 no, 1 yes, 2 unclear."""
    def code(v):
        text = _clean(v)
        if _NO.match(text):
            return 0
        if _YES.match(text):
            return 1
        return 2
    return series.map(code).astype(int)


def load_raw(path: str | Path, sheet: str = "Sheet1") -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet)
    if raw.shape[1] != 35 or not str(raw.columns[LABEL_COL]).startswith("Drop_Class_Label"):
        raise ValueError(f"Unexpected sheet layout: {raw.shape[1]} columns, last = {raw.columns[-1]!r}")
    return raw


def encode_survey(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Return (X_base, y). Every X_base column is an integer category code."""
    cols = raw.columns
    X = pd.DataFrame({name: _map(raw[cols[i]], mapping, name)
                      for i, (name, mapping) in SURVEY_COLUMNS.items()})
    X = X.join(_parse_tools(raw[cols[TOOLS_COL]]))
    X["gave_advice"] = _parse_gave_advice(raw[cols[ADVICE_COL]])
    X["learned_prompting"] = _parse_learned_prompting(raw[cols[PROMPTING_COL]])
    y = raw[cols[LABEL_COL]].astype(int).rename(TARGET)
    return X, y


def load_dataset(cfg: dict) -> tuple[pd.DataFrame, pd.Series]:
    return encode_survey(load_raw(cfg["data"]["raw_path"], cfg["data"]["sheet"]))


def split(X: pd.DataFrame, y: pd.Series, cfg: dict):
    """Stratified split of the real respondents. Must happen before any resampling."""
    return train_test_split(X, y, test_size=cfg["split"]["test_size"], stratify=y,
                            random_state=cfg["random_state"])
