from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import combinations
from pathlib import Path
from uuid import uuid4
import json

# Built once at import time; reused by every CareTask.next_occurrence() call.
_FREQUENCY_DELTA: dict[str, timedelta] = {
    "daily":       timedelta(days=1),
    "twice_daily": timedelta(hours=12),
    "weekly":      timedelta(weeks=1),
}

# Maps the numeric priority field (1–5) to a human-readable label with emoji.
# 1–2 → Low, 3 → Medium, 4 → High, 5 → Critical.
# Used by CareTask.priority_label and by the Streamlit color-coding logic.
PRIORITY_META: dict[int, tuple[str, str]] = {
    1: ("🟢", "Low"),
    2: ("🟢", "Low"),
    3: ("🟡", "Medium"),
    4: ("🔴", "High"),
    5: ("🚨", "Critical"),
}

# Background colours (CSS hex) matched to each tier — consumed by app.py pandas styling.
PRIORITY_BG: dict[str, str] = {
    "Low":      "#d4edda",  # soft green
    "Medium":   "#fff3cd",  # soft amber
    "High":     "#f8d7da",  # soft red
    "Critical": "#f5c6cb",  # deeper red
}

# Emoji icons for each task category — used in both CLI (main.py) and Streamlit (app.py).
CATEGORY_EMOJI: dict[str, str] = {
    "exercise":   "🏃",
    "nutrition":  "🍖",
    "medical":    "💊",
    "grooming":   "✂️",
    "enrichment": "🧸",
}

# Short human-readable labels for frequency values.
FREQUENCY_LABEL: dict[str, str] = {
    "daily":       "Daily",
    "twice_daily": "2×/day",
    "weekly":      "Weekly",
}


@dataclass
class CareTask:
    name: str
    category: str  # "exercise" | "nutrition" | "medical" | "grooming" | "enrichment"
    duration_minutes: int
    priority: int  # 1 (low) → 5 (critical)
    is_required: bool
    frequency: str  # "daily" | "twice_daily" | "weekly"
    notes: str = ""
    completed: bool = False
    scheduled_date: str = field(default_factory=lambda: date.today().isoformat())
    id: str = field(default_factory=lambda: str(uuid4()))

    def mark_complete(self) -> None:
        """Mark this task as completed."""
        self.completed = True

    def next_occurrence(self) -> CareTask | None:
        """Return a new CareTask scheduled for the next occurrence based on this task's frequency.

        Looks up the time delta from the module-level _FREQUENCY_DELTA constant and
        adds it to scheduled_date. The returned task is a fresh instance with a new id
        so it can be tracked independently.

        Returns:
            A new CareTask with scheduled_date advanced by the frequency delta,
            or None if the frequency value is not recognised as recurring.
        """
        _delta = _FREQUENCY_DELTA.get(self.frequency)
        if _delta is None:
            return None
        next_date = date.fromisoformat(self.scheduled_date) + _delta
        return CareTask(
            name=self.name,
            category=self.category,
            duration_minutes=self.duration_minutes,
            priority=self.priority,
            is_required=self.is_required,
            frequency=self.frequency,
            notes=self.notes,
            scheduled_date=next_date.isoformat(),
        )

    @property
    def priority_label(self) -> str:
        """Return the emoji + tier name for this task's numeric priority.

        Looks up PRIORITY_META using the integer priority field and joins the
        two-element tuple into a display string (e.g. '🔴 High').
        Falls back to the raw number if the value is out of range.
        """
        meta = PRIORITY_META.get(self.priority)
        if meta is None:
            return str(self.priority)
        emoji, label = meta
        return f"{emoji} {label}"

    def is_skippable(self) -> bool:
        """Return True if the task is optional and can be skipped."""
        return not self.is_required

    def to_dict(self) -> dict:
        """Serialize the task to a plain dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "duration_minutes": self.duration_minutes,
            "priority": self.priority,
            "is_required": self.is_required,
            "frequency": self.frequency,
            "notes": self.notes,
        }


@dataclass
class Vet:
    name: str
    clinic_name: str
    phone: str
    email: str
    recommended_tasks: list[CareTask] = field(default_factory=list)

    def add_recommendation(self, task: CareTask) -> None:
        """Add a care task to this vet's list of recommendations."""
        self.recommended_tasks.append(task)

    def get_recommendations(self) -> list[CareTask]:
        """Return all tasks recommended by this vet."""
        return list(self.recommended_tasks)


@dataclass
class Pet:
    name: str
    species: str
    breed: str
    age_years: float
    weight_kg: float
    medical_notes: str = ""
    vet: Vet | None = None
    care_tasks: list[CareTask] = field(default_factory=list)

    def add_task(self, task: CareTask) -> None:
        """Append a care task to this pet's task list."""
        self.care_tasks.append(task)

    def remove_task(self, task_id: str) -> None:
        """Remove a task from this pet's care list by its unique id.

        Rebuilds care_tasks excluding the matching task. Silently does nothing
        if no task with the given id exists.

        Args:
            task_id: The UUID string of the task to remove.
        """
        self.care_tasks = [t for t in self.care_tasks if t.id != task_id]

    def get_tasks_by_priority(self) -> list[CareTask]:
        """Return a sorted copy of care tasks from highest to lowest priority.

        Does not modify the original care_tasks list.

        Returns:
            A new list of CareTask objects ordered by priority descending (5 → 1).
        """
        return sorted(self.care_tasks, key=lambda t: t.priority, reverse=True)

    def get_required_tasks(self) -> list[CareTask]:
        """Return only the tasks that are marked as required for this pet.

        Returns:
            A list of CareTask objects where is_required is True.
            Returns an empty list if no required tasks exist.
        """
        return [t for t in self.care_tasks if t.is_required]

    def sync_vet_tasks(self) -> None:
        """Merge vet-recommended tasks into care_tasks, skipping any already present.

        Compares by task id to avoid duplicates. Does nothing if no vet is assigned.
        """
        if self.vet is None:
            return
        existing_ids = {t.id for t in self.care_tasks}
        for task in self.vet.recommended_tasks:
            if task.id not in existing_ids:
                self.care_tasks.append(task)


@dataclass
class Owner:
    name: str
    available_time_minutes: int
    preferences: list[str] = field(default_factory=list)
    pets: list[Pet] = field(default_factory=list)

    def add_pet(self, pet: Pet) -> None:
        """Register a pet under this owner."""
        self.pets.append(pet)

    def remove_pet(self, pet_name: str) -> None:
        """Remove a pet from this owner's list by name."""
        self.pets = [p for p in self.pets if p.name != pet_name]

    def get_tasks_by_pet(self, pet_name: str) -> list[CareTask]:
        """Return a copy of all care tasks belonging to the named pet.

        Uses next() to find the first pet whose name matches, then returns
        a shallow copy of that pet's care_tasks list.

        Args:
            pet_name: The exact name of the pet to look up (case-sensitive).

        Returns:
            A list of CareTask objects for the matched pet,
            or an empty list if no pet with that name is registered.
        """
        pet = next((p for p in self.pets if p.name == pet_name), None)
        return list(pet.care_tasks) if pet else []

    def save_to_json(self, path: str | Path) -> None:
        """Serialize this Owner (including all pets and their tasks) to a JSON file.

        Uses OwnerSchema from schemas.py (imported lazily to avoid circular
        imports at module load time). The file is written atomically by
        serializing to a string first, then writing in one call.

        Args:
            path: Destination file path. Parent directories must already exist.
        """
        from schemas import OwnerSchema  # lazy import — avoids circular dependency
        data = OwnerSchema().dump(self)
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load_from_json(cls, path: str | Path) -> Owner:
        """Deserialize an Owner from a JSON file produced by save_to_json.

        Uses OwnerSchema.load() which calls @post_load hooks on every nested
        schema, so the return value is a fully reconstructed Owner with live
        Pet and CareTask instances — not raw dicts.

        Args:
            path: Path to an existing JSON file.

        Returns:
            A fully populated Owner instance.

        Raises:
            FileNotFoundError: if path does not exist.
            marshmallow.ValidationError: if the JSON fails schema validation.
        """
        from schemas import OwnerSchema  # lazy import — avoids circular dependency
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return OwnerSchema().load(raw)


@dataclass
class Schedule:
    date: str  # ISO format: "2026-03-28"
    owner: Owner
    pet: Pet
    tasks: list[CareTask] = field(default_factory=list)

    def add_task(self, task: CareTask) -> None:
        """Add a care task to this schedule."""
        self.tasks.append(task)

    def remove_task(self, task_id: str) -> None:
        """Remove a task by its unique id."""
        self.tasks = [t for t in self.tasks if t.id != task_id]

    def get_total_duration(self) -> int:
        """Return the sum of all task durations in minutes."""
        return sum(t.duration_minutes for t in self.tasks)

    def fits_in_budget(self) -> bool:
        """Check whether total task duration fits within owner's available time."""
        return self.get_total_duration() <= self.owner.available_time_minutes

    def sort_by_priority(self) -> None:
        """Sort the schedule's task list in-place from highest to lowest priority.

        Mutates self.tasks directly using list.sort() with priority as the key.
        Tasks with equal priority retain their relative order (stable sort).
        """
        self.tasks.sort(key=lambda task: task.priority, reverse=True)

    def sort_by_time(self) -> None:
        """Sort the schedule's task list in-place by start time in HH:MM format.

        Delegates time parsing to _to_minutes(). Tasks without a valid HH:MM
        value in notes are treated as time 0 (midnight) and sorted first.
        """
        self.tasks.sort(key=lambda task: self._to_minutes(task.notes) or 0)

    def sort_by_priority_then_time(self) -> None:
        """Sort tasks in-place by priority descending, then by start time ascending.

        Uses a compound key: (-priority, start_minutes). Negating priority makes
        higher values sort first while keeping Python's default ascending sort
        direction for the time component. Tasks with no parseable HH:MM time are
        placed at the end of their priority group (they receive float('inf') as
        their time key so they naturally sink to the bottom within the group).

        This is strictly stronger than sort_by_priority() alone: tasks at the
        same urgency level are further ordered chronologically so the rendered
        schedule reads like a real day plan.
        """
        self.tasks.sort(
            key=lambda t: (-t.priority, self._to_minutes(t.notes) or float("inf"))
        )

    def mark_task_complete(self, task_id: str) -> CareTask | None:
        """Mark a task as done and automatically append its next occurrence to the schedule.

        Finds the task by id, calls mark_complete() on it, then calls
        next_occurrence() to generate the following instance. If the task
        recurs, the new instance is appended to self.tasks immediately.

        Args:
            task_id: The UUID string of the task to complete.

        Returns:
            The newly created next-occurrence CareTask if the task recurs,
            or None if the task id was not found or the task does not recur.
        """
        for task in self.tasks:
            if task.id == task_id:
                task.mark_complete()
                next_task = task.next_occurrence()
                if next_task is not None:
                    self.tasks.append(next_task)
                return next_task
        return None

    @staticmethod
    def _to_minutes(time_str: str) -> int | None:
        """Convert an 'HH:MM' string to total minutes since midnight.

        Used as the sort key for sort_by_time() and as the interval
        start point for get_conflicts().

        Args:
            time_str: A time string in 'HH:MM' 24-hour format (e.g. '07:30').

        Returns:
            An integer representing minutes since midnight (e.g. 450 for '07:30'),
            or None if the string is missing, empty, or not in HH:MM format.
        """
        try:
            h, m = time_str.split(":")
            return int(h) * 60 + int(m)
        except (ValueError, AttributeError):
            return None

    def get_conflicts(self) -> list[str]:
        """Detect and return warning messages for all overlapping task time windows.

        Builds a list of (task, start, end) tuples for every task that has a
        valid HH:MM time in notes, then checks every unique pair using
        itertools.combinations. Two tasks conflict when one starts before the
        other ends: start_A < end_B and start_B < end_A.

        Returns:
            A list of human-readable warning strings, one per conflicting pair.
            Returns an empty list when no conflicts are detected.
        """
        timed = [
            (task, s, s + task.duration_minutes)
            for task in self.tasks
            if (s := self._to_minutes(task.notes)) is not None
        ]
        return [
            f"CONFLICT [{self.pet.name}]  "
            f"'{a.name}' ({a.notes}, {a.duration_minutes} min)  overlaps  "
            f"'{b.name}' ({b.notes}, {b.duration_minutes} min)"
            for (a, a_start, a_end), (b, b_start, b_end) in combinations(timed, 2)
            if a_start < b_end and b_start < a_end
        ]

    def find_next_available_slot(self, duration_minutes: int, earliest_start: str = "07:00") -> str | None:
        """Return the earliest HH:MM gap in the day that fits duration_minutes.

        Algorithm (timeline sweep):
        1. Collect all timed tasks as (start, end) intervals; ignore untimed tasks.
        2. Sort intervals by start time and merge any overlapping/adjacent blocks
           into a flat list of occupied bands.
        3. Probe the gaps between consecutive bands (and before the first band)
           starting from earliest_start. The first gap whose length ≥ duration_minutes
           is returned as "HH:MM".
        4. If no gap is found before minute 1440 (midnight), return None.

        Args:
            duration_minutes: Minimum number of consecutive free minutes needed.
            earliest_start: The earliest time to consider, as "HH:MM" (default "07:00").

        Returns:
            The slot start time as "HH:MM", or None if no slot exists today.
        """
        floor = self._to_minutes(earliest_start) or 0
        end_of_day = 24 * 60  # 1440

        # Build sorted occupied intervals from timed tasks
        intervals: list[tuple[int, int]] = sorted(
            (s, s + t.duration_minutes)
            for t in self.tasks
            if (s := self._to_minutes(t.notes)) is not None
        )

        # Merge overlapping / adjacent intervals
        merged: list[tuple[int, int]] = []
        for start, end in intervals:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))

        # Probe gaps: before first block, between blocks, after last block
        probe = floor
        boundaries = [(end_of_day, end_of_day)]  # sentinel at end-of-day
        for band_start, band_end in (merged + boundaries):
            gap = band_start - probe
            if gap >= duration_minutes:
                h, m = divmod(probe, 60)
                return f"{h:02d}:{m:02d}"
            probe = max(probe, band_end)
            if probe >= end_of_day:
                break

        return None

    def filter_tasks(self, *, completed: bool | None = None, pet_name: str | None = None) -> list[CareTask]:
        """Return a filtered subset of this schedule's tasks in a single pass.

        Both filters are optional. Passing None for a parameter disables that
        filter entirely. Both conditions are combined with AND, so only tasks
        that satisfy every active filter are included.

        Args:
            completed: If True, return only completed tasks. If False, return
                only incomplete tasks. If None, completion status is ignored.
            pet_name: If provided, return tasks only when the schedule's pet
                name matches exactly. If None, pet name is not checked.

        Returns:
            A new list of CareTask objects matching all active filters.
            Returns an empty list if no tasks match.
        """
        return [
            t for t in self.tasks
            if (completed is None or t.completed == completed)
            and (pet_name is None or self.pet.name == pet_name)
        ]


@dataclass
class Plan:
    schedule: Schedule
    reasoning: str = ""
    skipped_tasks: list[CareTask] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def generate(cls, owner: Owner, pet: Pet, date: str) -> Plan:
        """
        Core scheduling logic:
        1. Sync vet-recommended tasks into pet.care_tasks.
        2. Always include required tasks first (regardless of time budget).
        3. Fill remaining time with optional tasks sorted by priority (high → low).
        4. Record skipped tasks and emit warnings for any skipped required tasks.
        """
        pet.sync_vet_tasks()

        required = [t for t in pet.care_tasks if t.is_required]
        optional = sorted(
            [t for t in pet.care_tasks if not t.is_required],
            key=lambda t: t.priority,
            reverse=True,
        )

        schedule = Schedule(date=date, owner=owner, pet=pet, tasks=list(required))
        budget_used = sum(t.duration_minutes for t in required)
        skipped: list[CareTask] = []
        warnings: list[str] = []

        if budget_used > owner.available_time_minutes:
            warnings.append(
                f"Required tasks ({budget_used} min) exceed the available time budget "
                f"({owner.available_time_minutes} min)."
            )

        for task in optional:
            if budget_used + task.duration_minutes <= owner.available_time_minutes:
                schedule.tasks.append(task)
                budget_used += task.duration_minutes
            else:
                skipped.append(task)

        return cls(schedule=schedule, reasoning="", skipped_tasks=skipped, warnings=warnings)

    def get_summary(self) -> str:
        """Return a human-readable summary of the plan and its scheduled tasks."""
        sched = self.schedule
        total = sum(t.duration_minutes for t in sched.tasks)
        lines = [
            f"Plan for {sched.pet.name} on {sched.date}",
            f"{len(sched.tasks)} tasks scheduled, {len(self.skipped_tasks)} skipped",
            f"Total time: {total} min / {sched.owner.available_time_minutes} min available",
        ]
        for w in self.warnings:
            lines.append(f"⚠️  {w}")
        return "\n".join(lines)

    def get_warnings(self) -> list[str]:
        """Return any warnings generated during plan creation (e.g. skipped required tasks)."""
        return self.warnings
