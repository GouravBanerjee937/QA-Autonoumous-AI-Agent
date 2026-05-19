"""Step 1.5: TestSpec → Questions the user must answer before we proceed."""

from __future__ import annotations

from ..events import EventBus
from ..llm import structured
from ..models import Questions, TestSpec
from ..prompts import INQUIRER_SYSTEM


def inquire(spec: TestSpec, bus: EventBus) -> Questions:
    bus.emit("inquirer", "Checking what concrete values are missing from the PRD…")
    questions = structured(INQUIRER_SYSTEM, spec.model_dump_json(indent=2), Questions)
    if not questions.items:
        bus.emit("inquirer", "Spec is complete. No questions for you.", level="success")
    else:
        bus.emit(
            "inquirer",
            f"Need {len(questions.items)} value(s) from you before continuing.",
            level="warn",
        )
        for q in questions.items:
            bus.emit("inquirer", f"  • {q.key} — {q.prompt}")
    return questions
