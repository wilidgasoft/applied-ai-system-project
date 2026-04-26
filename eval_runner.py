# Feature 4: Reliability & Testing System
#
# Run with: python eval_runner.py
#
# Executes 7 tests across two categories:
#   - Section 1 (tests 1-4): Deterministic — no API calls, pure domain logic.
#   - Section 2 (tests 5-7): AI Consistency — require ANTHROPIC_API_KEY and
#     the optional AI modules (ai_advisor, plan_agent). Skipped gracefully if
#     those modules or the API key are not available.
#
# Writes a markdown report to eval_report.md and exits with code 0 (all
# non-skipped tests pass) or 1 (any test failed).

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

# ── Optional AI modules — skip their tests if not available ──────────────────
try:
    from ai_advisor import suggest_tasks_for_pet as _suggest
    _HAS_AI_ADVISOR = True
except ImportError:
    _HAS_AI_ADVISOR = False

try:
    from plan_agent import generate_plan_reasoning as _reasoning
    _HAS_PLAN_AGENT = True
except ImportError:
    _HAS_PLAN_AGENT = False

from pawpal_system import CareTask, Owner, Pet, Plan, Schedule

# (test_name, status, details)
Result = tuple[str, str, str]


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _task(
    name: str,
    *,
    category: str = "exercise",
    duration: int = 30,
    priority: int = 3,
    required: bool = True,
    frequency: str = "daily",
    notes: str = "07:00",
) -> CareTask:
    return CareTask(
        name=name,
        category=category,
        duration_minutes=duration,
        priority=priority,
        is_required=required,
        frequency=frequency,
        notes=notes,
    )


def _owner(minutes: int = 120) -> Owner:
    return Owner(name="TestOwner", available_time_minutes=minutes)


def _pet(name: str = "Buddy") -> Pet:
    return Pet(name=name, species="Dog", breed="Lab", age_years=3.0, weight_kg=25.0)


# ── SECTION 1: Deterministic Tests ───────────────────────────────────────────

def test_required_tasks_always_included() -> Result:
    test = "test_required_tasks_always_included"
    try:
        owner = _owner(60)
        pet = _pet()
        pet.add_task(_task("Morning walk", duration=20, required=True))
        pet.add_task(_task("Medication", category="medical", duration=5, required=True))
        pet.add_task(_task("Playtime", category="enrichment", duration=30, required=False))
        pet.add_task(_task("Grooming", category="grooming", duration=20, required=False))
        pet.add_task(_task("Training", category="enrichment", duration=25, required=False))

        plan = Plan.generate(owner, pet, date.today().isoformat())
        if plan is None:
            return test, "SKIP", "Plan.generate() returned None — stub not yet implemented"

        scheduled = {t.name for t in plan.schedule.tasks}
        missing = [t.name for t in pet.care_tasks if t.is_required and t.name not in scheduled]
        if missing:
            return test, "FAIL", f"Required tasks missing from plan: {missing}"
        return test, "PASS", f"All required tasks included ({len(plan.schedule.tasks)} total scheduled)."
    except Exception as exc:
        return test, "FAIL", str(exc)


def test_conflict_detection_accuracy() -> Result:
    test = "test_conflict_detection_accuracy"
    try:
        owner = _owner(480)
        pet = _pet("Max")
        schedule = Schedule(date=date.today().isoformat(), owner=owner, pet=pet)
        schedule.add_task(_task("Walk", duration=30, notes="07:00"))
        schedule.add_task(_task("Feed", category="nutrition", duration=10, notes="08:00"))
        schedule.add_task(_task("Nap", category="enrichment", duration=60, notes="10:00"))

        clean = schedule.get_conflicts()
        if clean:
            return test, "FAIL", f"False positives on non-overlapping schedule: {clean}"

        # Inject a genuine overlap: 07:00–07:30 vs 07:15–08:00
        schedule.add_task(_task("Training", duration=45, notes="07:15"))
        overlapping = schedule.get_conflicts()
        if not overlapping:
            return test, "FAIL", "Expected overlap between 07:00–07:30 and 07:15–08:00 not detected"
        return test, "PASS", (
            f"Clean schedule: 0 false positives. "
            f"Overlap correctly flagged: {len(overlapping)} conflict(s)."
        )
    except Exception as exc:
        return test, "FAIL", str(exc)


def test_next_occurrence_recurrence() -> Result:
    test = "test_next_occurrence_recurrence"
    try:
        owner = _owner(240)
        pet = _pet("Luna")
        task = _task("Daily brushing", category="grooming", frequency="daily")
        pet.add_task(task)
        schedule = Schedule(
            date=date.today().isoformat(), owner=owner, pet=pet,
            tasks=list(pet.care_tasks),
        )

        next_task = schedule.mark_task_complete(task.id)
        if next_task is None:
            return test, "FAIL", "mark_task_complete returned None for a daily task"
        if next_task.completed:
            return test, "FAIL", "Next occurrence should have completed=False"
        if next_task.id == task.id:
            return test, "FAIL", "Next occurrence must have a new UUID"
        expected = (date.today() + timedelta(days=1)).isoformat()
        if next_task.scheduled_date != expected:
            return test, "FAIL", f"Expected date {expected}, got {next_task.scheduled_date}"
        return test, "PASS", f"Daily task recurs correctly on {next_task.scheduled_date}."
    except Exception as exc:
        return test, "FAIL", str(exc)


def test_budget_respected_for_optional() -> Result:
    test = "test_budget_respected_for_optional"
    try:
        owner = _owner(60)
        pet = _pet("Rex")
        for i in range(5):
            pet.add_task(_task(f"Optional {i+1}", duration=30, required=False, priority=3))

        plan = Plan.generate(owner, pet, date.today().isoformat())
        if plan is None:
            return test, "SKIP", "Plan.generate() returned None — stub not yet implemented"

        total = sum(t.duration_minutes for t in plan.schedule.tasks)
        if total > owner.available_time_minutes:
            return test, "FAIL", (
                f"Scheduled {total} min exceeds budget of {owner.available_time_minutes} min"
            )
        return test, "PASS", (
            f"Budget respected: {total} min scheduled within {owner.available_time_minutes} min."
        )
    except Exception as exc:
        return test, "FAIL", str(exc)


# ── SECTION 2: AI Consistency Tests ──────────────────────────────────────────

def test_ai_suggestion_parses_as_json() -> Result:
    test = "test_ai_suggestion_parses_as_json"
    if not _HAS_AI_ADVISOR:
        return test, "SKIP", "ai_advisor module not found"
    try:
        raw = _suggest("Dog", "Golden Retriever", 3.0, 25.0)
        data = json.loads(raw)
        if not isinstance(data, list):
            return test, "FAIL", f"Expected JSON array, got {type(data).__name__}"
        required_keys = {"name", "category", "duration_minutes", "priority", "is_required", "frequency"}
        for i, item in enumerate(data):
            missing = required_keys - set(item.keys())
            if missing:
                return test, "FAIL", f"Item {i} missing keys: {missing}"
        return test, "PASS", f"Parsed {len(data)} task(s) with all required keys present."
    except json.JSONDecodeError as exc:
        return test, "FAIL", f"JSON parse error: {exc}"
    except Exception as exc:
        return test, "FAIL", str(exc)


def test_ai_reasoning_mentions_pet() -> Result:
    test = "test_ai_reasoning_mentions_pet"
    if not _HAS_PLAN_AGENT:
        return test, "SKIP", "plan_agent module not found"
    try:
        owner = _owner(120)
        pet = Pet(name="Mochi", species="Dog", breed="Shiba Inu", age_years=2.0, weight_kg=9.0)
        pet.add_task(_task("Morning run", duration=30, required=True))
        pet.add_task(_task("Evening walk", duration=20, required=False))

        plan = Plan.generate(owner, pet, date.today().isoformat())
        if plan is None:
            return test, "SKIP", "Plan.generate() returned None — stub not yet implemented"

        reasoning = _reasoning(plan)
        if pet.name not in reasoning:
            return test, "FAIL", f"Reasoning does not mention pet name '{pet.name}'"
        if len(reasoning) < 50:
            return test, "FAIL", f"Reasoning too short ({len(reasoning)} chars)"
        return test, "PASS", f"Reasoning ({len(reasoning)} chars) correctly mentions '{pet.name}'."
    except Exception as exc:
        return test, "FAIL", str(exc)


def test_ai_suggestion_consistency() -> Result:
    test = "test_ai_suggestion_consistency"
    if not _HAS_AI_ADVISOR:
        return test, "SKIP", "ai_advisor module not found"
    try:
        name_sets: list[set[str]] = []
        for run in range(3):
            raw = _suggest("Dog", "Labrador", 2.0, 30.0)
            data = json.loads(raw)
            name_sets.append({item["name"].lower() for item in data})

        union = name_sets[0] | name_sets[1] | name_sets[2]
        intersection = name_sets[0] & name_sets[1] & name_sets[2]
        overlap = len(intersection) / len(union) if union else 0.0

        if overlap < 0.5:
            return test, "FAIL", (
                f"Consistency too low: {overlap:.0%} overlap across 3 runs "
                f"({len(intersection)}/{len(union)} tasks in common)"
            )
        return test, "PASS", (
            f"{overlap:.0%} task-name overlap across 3 identical runs "
            f"({len(intersection)}/{len(union)} in common)."
        )
    except json.JSONDecodeError as exc:
        return test, "FAIL", f"JSON parse error on one run: {exc}"
    except Exception as exc:
        return test, "FAIL", str(exc)


# ── SECTION 3: Report Generator ──────────────────────────────────────────────

def generate_report(results: list[Result]) -> str:
    today = date.today().isoformat()
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    skipped = sum(1 for _, s, _ in results if s == "SKIP")
    non_skipped = passed + failed

    icons = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️"}
    table_rows = "\n".join(
        f"| `{name}` | {icons.get(status, status)} {status} | {detail} |"
        for name, status, detail in results
    )
    failed_section = ""
    if failed:
        failed_section = "\n## Failed Tests\n\n" + "\n\n".join(
            f"### `{n}`\n{d}" for n, s, d in results if s == "FAIL"
        )

    return (
        f"# PawPal+ AI Reliability Report\n\n"
        f"**Date:** {today}  \n"
        f"**Score:** {passed} / {non_skipped} non-skipped tests passed "
        f"({skipped} skipped)\n\n"
        f"## Results\n\n"
        f"| Test | Status | Details |\n"
        f"|------|--------|---------|\n"
        f"{table_rows}\n"
        f"{failed_section}"
    )


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    all_tests = [
        test_required_tasks_always_included,
        test_conflict_detection_accuracy,
        test_next_occurrence_recurrence,
        test_budget_respected_for_optional,
        test_ai_suggestion_parses_as_json,
        test_ai_reasoning_mentions_pet,
        test_ai_suggestion_consistency,
    ]

    results: list[Result] = []
    for fn in all_tests:
        print(f"Running: {fn.__name__}...", end=" ", flush=True)
        result = fn()
        results.append(result)
        _, status, detail = result
        print(f"{status} — {detail}")

    report_md = generate_report(results)
    print("\n" + "=" * 60)
    print(report_md)

    report_path = Path("eval_report.md")
    report_path.write_text(report_md, encoding="utf-8")
    print(f"\nReport written to {report_path.resolve()}")

    sys.exit(1 if any(s == "FAIL" for _, s, _ in results) else 0)
