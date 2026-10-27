"""Human-readable data dictionary for the dashboards: question titles, answer labels, groups.

Codes match `dropout_risk.data`. `actionable` marks answers an institution can influence
(used by the risk simulator to suggest what would lower a student's risk).
"""

from dataclasses import dataclass, field

FREQUENCY = {0: "Never", 1: "Rarely", 2: "Sometimes", 3: "Often", 4: "Always"}
YES_NO = {0: "No", 1: "Yes"}
NO_PARTLY_YES = {0: "No", 1: "Somewhat", 2: "Yes"}
NO_SOMETIMES_YES = {0: "No", 1: "Sometimes", 2: "Yes"}

DEMOGRAPHICS = "Demographics"
AI_USAGE = "AI usage"
LEARNING = "Learning impact"
INTEGRITY = "Academic integrity"
LITERACY = "AI literacy"
INDICES = "Indices"
GROUPS = [DEMOGRAPHICS, AI_USAGE, LEARNING, INTEGRITY, LITERACY]


@dataclass(frozen=True)
class Feature:
    name: str
    title: str
    group: str
    answers: dict[int, str] = field(default_factory=dict)
    actionable: bool = True
    description: str = ""

    def label(self, code: int) -> str:
        return self.answers.get(int(code), str(code))


_BASE = [
    Feature("is_male", "Gender", DEMOGRAPHICS, {0: "Female", 1: "Male"}, actionable=False),
    Feature("major", "Major", DEMOGRAPHICS,
            {0: "Engineering & Tech", 1: "Science", 2: "Medical", 3: "Humanities", 4: "Other"},
            actionable=False),
    Feature("degree_level", "Degree", DEMOGRAPHICS,
            {0: "Diploma", 1: "Bachelor", 2: "Master", 3: "PhD"}, actionable=False),
    Feature("study_year", "Study year", DEMOGRAPHICS,
            {1: "1st year", 2: "2nd year", 3: "3rd year", 4: "4th year", 5: "5th year +"},
            actionable=False),
    Feature("residence_urbanity", "Residence", DEMOGRAPHICS,
            {0: "Village", 1: "District (liwa)", 2: "Governorate", 3: "Capital"}, actionable=False),
    Feature("is_private_university", "University type", DEMOGRAPHICS,
            {0: "Public", 1: "Private"}, actionable=False),

    Feature("ever_used_ai", "Has used AI text tools", AI_USAGE, YES_NO, actionable=False),
    Feature("ai_study_frequency", "AI use for studying", AI_USAGE, FREQUENCY),
    Feature("ai_replaces_research", "AI replaces traditional research", AI_USAGE, FREQUENCY),
    Feature("ai_replaces_search_engines", "AI replaces search engines & books", AI_USAGE,
            {0: "Never", 1: "Rarely", 2: "Sometimes", 4: "Always"}),
    Feature("uses_chatgpt", "Uses ChatGPT", AI_USAGE, YES_NO, actionable=False),
    Feature("uses_gemini", "Uses Google Gemini", AI_USAGE, YES_NO, actionable=False),
    Feature("uses_claude", "Uses Claude", AI_USAGE, YES_NO, actionable=False),
    Feature("uses_copilot", "Uses Microsoft Copilot", AI_USAGE, YES_NO, actionable=False),
    Feature("uses_other_tool", "Uses other AI tools", AI_USAGE, YES_NO, actionable=False),

    Feature("analytical_skills_effect", "Effect of AI on analytical skills", LEARNING,
            {0: "Negative", 1: "No effect", 2: "Positive"}),
    Feature("independent_learning", "AI helps independent learning", LEARNING, NO_PARTLY_YES),
    Feature("motivation_effect", "Effect of AI on study motivation", LEARNING,
            {0: "Reduces", 1: "No effect", 2: "Increases"}),
    Feature("over_reliance", "Relies on AI instead of own thinking", LEARNING, NO_SOMETIMES_YES),
    Feature("saves_time", "AI saves study time", LEARNING, {0: "No", 1: "Somewhat", 2: "Greatly"}),
    Feature("ai_improved_education", "AI has improved education", LEARNING, NO_PARTLY_YES),

    Feature("ai_cheating_view", "Considers AI use in assignments cheating", INTEGRITY,
            {0: "No", 1: "Depends on use", 2: "Yes"}),
    Feature("submitted_full_project", "Submitted a full AI-generated project", INTEGRITY, YES_NO),
    Feature("reviews_content", "Reviews AI content and sources", INTEGRITY,
            {0: "Never", 1: "Sometimes", 2: "Always"}),
    Feature("content_errors", "Found errors in AI content", INTEGRITY,
            {0: "Never", 1: "Rarely", 2: "Sometimes", 3: "Often"}),
    Feature("used_ai_in_exam", "Used AI in an in-class exam", INTEGRITY, YES_NO),
    Feature("flagged_by_professor", "Flagged by a professor for AI use", INTEGRITY, YES_NO),
    Feature("professor_was_right", "Professor's flag was justified", INTEGRITY,
            {0: "Never flagged", 1: "No", 2: "Partly", 3: "Yes"}),

    Feature("detector_knowledge", "Knows how AI detectors work", LITERACY,
            {0: "Weak", 1: "Average", 2: "Good", 3: "Excellent"}),
    Feature("easy_to_detect", "Thinks AI use is easy for staff to detect", LITERACY, NO_SOMETIMES_YES),
    Feature("gave_advice", "Gave advice on positive AI use", LITERACY, YES_NO),
    Feature("learned_prompting", "Has learned prompt writing", LITERACY,
            {0: "No", 1: "Yes", 2: "Unclear"}),
]

# engineered indices (see dropout_risk.features.ENGINEERED_FEATURES); answers = their value range
_INDICES = [
    Feature("ai_dependency_index", "AI dependency index", INDICES, {i: str(i) for i in range(11)},
            description="study frequency + over-reliance + AI replacing research (0–10)"),
    Feature("integrity_risk_count", "Integrity incidents", INDICES, {i: str(i) for i in range(4)},
            description="full AI project + AI in exam + flagged by professor (0–3)"),
    Feature("negative_impact_count", "Negative learning effects", INDICES, {i: str(i) for i in range(4)},
            description="negative analytical effect + reduced motivation + no independent learning (0–3)"),
    Feature("ai_search_substitution", "AI search substitution", INDICES, {i: str(i) for i in range(9)},
            description="AI replaces research + AI replaces search engines (0–8)"),
    Feature("perceived_benefit", "Perceived AI benefit", INDICES, {i: str(i) for i in range(5)},
            description="saves time + improved education (0–4)"),
    Feature("ai_literacy", "AI literacy score", INDICES, {i: str(i) for i in range(6)},
            description="detector knowledge + learned prompting + gave advice (0–5)"),
    Feature("detection_awareness", "Detection awareness", INDICES, {i: str(i) for i in range(6)},
            description="detector knowledge + thinks AI use is easy to detect (0–5)"),
    Feature("n_ai_tools", "Number of AI tools used", INDICES, {i: str(i) for i in range(6)},
            description="count of AI tools selected (0–5)"),
    Feature("is_senior", "Senior student (4th year +)", INDICES, YES_NO),
]

BASE_FEATURES: dict[str, Feature] = {f.name: f for f in _BASE}
INDEX_FEATURES: dict[str, Feature] = {f.name: f for f in _INDICES}
ALL_FEATURES: dict[str, Feature] = BASE_FEATURES | INDEX_FEATURES
TOOL_FEATURES = ["uses_chatgpt", "uses_gemini", "uses_claude", "uses_copilot", "uses_other_tool"]
SEGMENT_FILTERS = ["major", "study_year", "is_male", "is_private_university"]
CLASS_LABELS = {0: "No drop", 1: "Drop"}
