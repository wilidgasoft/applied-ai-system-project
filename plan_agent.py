# Feature 2: Agentic Workflow — AI Plan Reasoning
# Requires: ANTHROPIC_API_KEY environment variable
#
# Takes a completed Plan object (built by Plan.generate()) and asks Claude
# to produce a friendly, human-readable explanation of the scheduling decisions.
# Kept separate from pawpal_system.py so the domain model stays API-free.

from __future__ import annotations

import anthropic
from pawpal_system import Plan


def generate_plan_reasoning(plan: Plan) -> str:
    """Ask Claude to explain the scheduling decisions in the given Plan.

    Includes the pet profile, all scheduled tasks, skipped tasks, and any
    warnings as context. Returns a 2-3 sentence friendly explanation.

    Raises:
        anthropic.APIError: if the API call fails.
    """
    sched = plan.schedule
    total_min = sum(t.duration_minutes for t in sched.tasks)

    task_lines = "\n".join(
        f"  - {t.name} ({t.category}, {t.duration_minutes} min, "
        f"priority {t.priority}, {'required' if t.is_required else 'optional'})"
        for t in sched.tasks
    ) or "  (none)"

    skipped_names = ", ".join(t.name for t in plan.skipped_tasks) or "none"
    warning_text = "; ".join(plan.warnings) or "none"

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=(
            "You are PawPal+, a friendly and encouraging pet care scheduling assistant. "
            "Write a warm, concise 2-3 sentence explanation of the generated schedule. "
            "Mention that required tasks were always included first, briefly note what was "
            "skipped if anything, and end with an encouraging note for the owner. "
            "Use plain language — no bullet points, no headers."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Pet: {sched.pet.name} "
                    f"({sched.pet.species}, {sched.pet.breed}, "
                    f"{sched.pet.age_years:.0f} yrs, {sched.pet.weight_kg} kg)\n"
                    f"Owner available time: {sched.owner.available_time_minutes} min\n"
                    f"Scheduled tasks ({len(sched.tasks)} total, {total_min} min):\n"
                    f"{task_lines}\n"
                    f"Skipped optional tasks: {skipped_names}\n"
                    f"Warnings: {warning_text}"
                ),
            }
        ],
    )
    return response.content[0].text
