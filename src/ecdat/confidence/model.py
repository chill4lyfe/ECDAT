from ecdat.domain.enums import ConfidenceLevel
from ecdat.domain.models import Confidence


def confidence_from_score(score: float, *reasons: str) -> Confidence:
    score = max(0.0, min(1.0, score))
    if score >= 0.85:
        level = ConfidenceLevel.HIGH
    elif score >= 0.55:
        level = ConfidenceLevel.MEDIUM
    else:
        level = ConfidenceLevel.LOW
    return Confidence(level=level, score=score, reasons=tuple(reasons))
