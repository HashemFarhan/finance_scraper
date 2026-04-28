from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


DecisionAction = Literal["form_visible", "click", "none"]


@dataclass
class ScreenshotArtifact:
    path: str
    kind: str
    index: int
    url: str
    scroll_y: int | None = None


@dataclass
class NavigationDecision:
    action: DecisionAction
    text: str | None = None
    reason: str = ""
    confidence: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClickResult:
    success: bool
    text: str | None = None
    method: str | None = None
    error: str | None = None


@dataclass
class StepRecord:
    index: int
    url: str
    action: str
    target: str | None = None
    reason: str = ""
    success: bool = False
    error: str | None = None
    screenshots: list[str] = field(default_factory=list)


@dataclass
class FormCandidate:
    kind: str
    label: str
    selector: str
    score: int
    reason: str
    text: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    input_count: int = 0
    submit_button_count: int = 0


@dataclass
class FormDetectionResult:
    found: bool
    input_count: int = 0
    submit_button_count: int = 0
    form_count: int = 0
    evidence: list[str] = field(default_factory=list)
    candidates: list[FormCandidate] = field(default_factory=list)
    primary_candidate: FormCandidate | None = None


@dataclass
class ConsentExtraction:
    submit_language: str | None = None
    evidence: list[str] = field(default_factory=list)


@dataclass
class PolicyLinks:
    terms_url: str | None = None
    privacy_url: str | None = None
    evidence: list[dict[str, str]] = field(default_factory=list)


@dataclass
class PolicyDocument:
    url: str | None
    text: str | None = None
    error: str | None = None


@dataclass
class ComplianceResult:
    form_found: bool
    final_url: str
    steps: list[StepRecord]
    screenshots: list[str]
    submit_language: str | None = None
    consent_evidence: list[str] = field(default_factory=list)
    terms_url: str | None = None
    privacy_url: str | None = None
    terms_text: str | None = None
    privacy_text: str | None = None
    link_evidence: list[dict[str, str]] = field(default_factory=list)
    form_evidence: list[str] = field(default_factory=list)
    form_candidates: list[FormCandidate] = field(default_factory=list)
    primary_form_candidate: FormCandidate | None = None
    llm_form_assessment: dict[str, Any] = field(default_factory=dict)
    llm_button_candidates: list[dict[str, Any]] = field(default_factory=list)
    decision_source: str | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
