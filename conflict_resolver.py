# Feature 2: Agentic Workflow — Conflict Resolution Loop
#
# Attempts to automatically fix scheduling conflicts by reassigning the
# lower-priority task in each conflicting pair to the next available free slot.
# Runs up to max_iterations times so the agent can self-correct iteratively.
# No API calls — pure domain logic using existing Schedule methods.

from __future__ import annotations

from pawpal_system import CareTask, Schedule

_MAX_ITERATIONS = 3


def resolve_conflicts(
    schedule: Schedule,
    max_iterations: int = _MAX_ITERATIONS,
) -> list[str]:
    """Attempt to resolve all scheduling conflicts in-place by reassigning tasks.

    For each conflict, the lower-priority task is moved to the earliest available
    free slot of sufficient length. The loop repeats up to max_iterations times.

    Args:
        schedule: The Schedule to modify in-place.
        max_iterations: Maximum number of fix-attempt rounds (default 3).

    Returns:
        A list of conflict strings that could NOT be resolved after all iterations.
        An empty list means the schedule is conflict-free.
    """
    for _ in range(max_iterations):
        conflicts = schedule.get_conflicts()
        if not conflicts:
            return []

        for conflict_msg in conflicts:
            victim = _lower_priority_task(schedule, conflict_msg)
            if victim is None:
                continue
            new_slot = schedule.find_next_available_slot(
                victim.duration_minutes,
                earliest_start="07:00",
            )
            if new_slot:
                victim.notes = new_slot

    # Return whatever remains unresolved after all iterations
    return schedule.get_conflicts()


def _lower_priority_task(schedule: Schedule, conflict_msg: str) -> CareTask | None:
    """Return the lower-priority task mentioned in a conflict warning string."""
    candidates = [t for t in schedule.tasks if t.name in conflict_msg]
    if len(candidates) < 2:
        return None
    # min priority number = lower urgency = the one we move
    return min(candidates, key=lambda t: t.priority)
