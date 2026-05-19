"""Step 1: PRD → TestSpec."""

from __future__ import annotations

from ..events import EventBus
from ..llm import structured
from ..models import TestSpec
from ..prompts import ANALYST_SYSTEM


def analyze(prd_text: str, app_url: str, bus: EventBus) -> TestSpec:
    bus.emit("analyst", "Reading PRD and extracting functional requirements…")
    user = (
        f"App URL provided by user (use this if PRD omits one): {app_url}\n\n"
        f"PRD:\n{prd_text}"
    )
    spec = structured(ANALYST_SYSTEM, user, TestSpec)
    if not spec.app_url:
        spec.app_url = app_url
    bus.emit(
        "analyst",
        f"Identified {len(spec.user_flows)} user flow(s) and "
        f"{len(spec.acceptance_criteria)} acceptance criterion/criteria.",
        level="success",
    )
    if spec.notes:
        bus.emit("analyst", f"Ambiguities flagged: {spec.notes}", level="warn")
    return spec
