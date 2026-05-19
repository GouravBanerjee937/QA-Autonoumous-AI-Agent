"""Step 8: render a final Markdown report with embedded screenshot references."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..events import EventBus
from ..models import RunResults, TestPlan, TestSpec


def report(
    spec: TestSpec,
    plan: TestPlan,
    results: RunResults,
    reports_dir: Path,
    bus: EventBus,
) -> str:
    reports_dir.mkdir(parents=True, exist_ok=True)
    titles = {tc.id: tc.title for tc in plan.test_cases}
    total = len(results.results)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = []
    lines.append(f"# QA Report — {spec.app_name}")
    lines.append("")
    lines.append(f"_Generated {timestamp}_  ·  App URL: {spec.app_url}")
    lines.append("")
    lines.append(f"**{results.passed}/{total} passed** ({results.failed} failed)")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append("| ID | Title | Status | Duration |")
    lines.append("|---|---|---|---|")
    for r in results.results:
        icon = {"passed": "✅", "failed": "❌", "error": "⚠️"}[r.status]
        lines.append(
            f"| `{r.test_case_id}` | {titles.get(r.test_case_id, '')} "
            f"| {icon} {r.status} | {r.duration_s:.2f}s |"
        )

    lines.append("")
    lines.append("## Visual evidence")
    lines.append("")
    for r in results.results:
        icon = {"passed": "✅", "failed": "❌", "error": "⚠️"}[r.status]
        lines.append(f"\n### {icon} `{r.test_case_id}` — {titles.get(r.test_case_id, '')}")
        lines.append("")
        if r.artifacts.screenshots:
            for shot in r.artifacts.screenshots:
                rel = _relative_to(shot, reports_dir)
                label = Path(shot).stem
                lines.append(f"![{label}]({rel})")
                lines.append("")
        else:
            lines.append("_No screenshots captured._")
            lines.append("")
        if r.failure_message:
            lines.append("**Failure:**")
            lines.append("")
            lines.append("```")
            lines.append(r.failure_message[:1500])
            lines.append("```")
            lines.append("")
        if r.artifacts.trace_path:
            rel_trace = _relative_to(r.artifacts.trace_path, reports_dir)
            lines.append(f"Replay: `playwright show-trace {rel_trace}`")
            lines.append("")

    if spec.notes:
        lines.append("## Analyst notes on the PRD")
        lines.append("")
        lines.append(f"> {spec.notes}")

    markdown = "\n".join(lines)
    out = reports_dir / "final_qa_report.md"
    out.write_text(markdown, encoding="utf-8")
    bus.emit("reporter", f"Wrote {out}", level="success")
    return markdown


def _relative_to(path: str, base: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(base.resolve()))
    except ValueError:
        return path
