"""Versioned deterministic QuickScreen recommendation policy."""

from job_hunter.domain.screening import QuickScreenRecommendation, ScreenReasonCode

QUICK_SCREEN_POLICY_VERSION = "quick-screen-v1"


def _matches_any(value: str, candidates: tuple[str, ...]) -> bool:
    normalized = value.casefold()
    return any(candidate.casefold() in normalized for candidate in candidates)


def recommend_quick_screen(
    *,
    title: str,
    city: str,
    requirement_texts: tuple[str, ...],
    target_role_keywords: tuple[str, ...],
    skill_keywords: tuple[str, ...],
    preferred_cities: tuple[str, ...],
) -> tuple[QuickScreenRecommendation, tuple[ScreenReasonCode, ...]]:
    if preferred_cities and not _matches_any(city, preferred_cities):
        return (
            QuickScreenRecommendation.SCREEN_OUT,
            (ScreenReasonCode.CITY_OUTSIDE_PREFERENCE,),
        )
    title_matches = _matches_any(title, target_role_keywords)
    skill_matches = _matches_any(" ".join(requirement_texts), skill_keywords)
    if title_matches and skill_matches:
        return (
            QuickScreenRecommendation.SCREEN_IN,
            (ScreenReasonCode.TARGET_ROLE_MATCH, ScreenReasonCode.SKILL_OVERLAP),
        )
    return QuickScreenRecommendation.UNCERTAIN, (ScreenReasonCode.INSUFFICIENT_SIGNAL,)
