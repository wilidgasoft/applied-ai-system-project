# PawPal+ AI Features — Implementation Plan

This document describes how to implement four advanced AI capabilities in the PawPal+ pet care scheduling app. Each section includes the architectural approach, the files to create or modify, the required dependencies, and a ready-to-use agent prompt that can be executed directly to implement that feature.

---

## Table of Contents

1. [RAG — Retrieval-Augmented Generation](#1-rag--retrieval-augmented-generation)
2. [Agentic Workflow — Self-Correcting Plan Generator](#2-agentic-workflow--self-correcting-plan-generator)
3. [Fine-Tuned / Specialized Model — Veterinary AI Advisor](#3-fine-tuned--specialized-model--veterinary-ai-advisor)
4. [Reliability & Testing System — AI Consistency Evaluator](#4-reliability--testing-system--ai-consistency-evaluator)

---

## 1. RAG — Retrieval-Augmented Generation

### What It Means for PawPal+

When a user registers a pet (species + breed), the system retrieves relevant care facts from a local knowledge base before generating task suggestions. Instead of Claude guessing what a Golden Retriever needs, it first looks up validated care data and includes it in the prompt context.

### Architecture

```
User adds pet (species: Dog, breed: Golden Retriever)
        │
        ▼
  retrieve_care_facts(species, breed)
        │  searches pet_care_kb.json by keyword
        ▼
  Relevant facts returned as context
        │
        ▼
  Claude API called with facts + pet profile
        │
        ▼
  Suggested CareTask list returned to user
```

### Files to Create / Modify

| File | Action | Purpose |
|------|--------|---------|
| `docs/pet_care_kb.json` | Create | Knowledge base: species/breed → care facts |
| `ai_advisor.py` | Create | RAG retrieval logic + Claude API call |
| `app.py` | Modify | Add "Suggest Tasks (AI)" button in the Add Pet section |
| `requirements.txt` | Modify | Add `anthropic` |

### Knowledge Base Structure (`pet_care_kb.json`)

```json
{
  "dog": {
    "general": [
      "Dogs require fresh water available at all times.",
      "Annual vet checkups are recommended for healthy adult dogs.",
      "Dogs need daily exercise to maintain a healthy weight."
    ],
    "golden retriever": [
      "Golden Retrievers need 60–90 minutes of exercise daily.",
      "Their dense coat requires brushing 2–3 times per week.",
      "They are prone to hip dysplasia — avoid high-impact exercise in puppies."
    ],
    "chihuahua": [
      "Chihuahuas need 20–30 minutes of light exercise per day.",
      "Their small size makes them sensitive to cold — consider a coat in winter.",
      "Dental hygiene is critical; brush teeth 3 times per week."
    ]
  },
  "cat": {
    "general": [
      "Cats need a clean litter box scooped daily.",
      "Annual vet visits are recommended for healthy adult cats.",
      "Cats benefit from environmental enrichment like puzzle feeders."
    ],
    "persian": [
      "Persian cats require daily coat brushing to prevent matting.",
      "Their flat face makes them prone to respiratory issues — monitor breathing.",
      "Eye discharge should be cleaned gently every day."
    ]
  }
}
```

### Implementation Logic (`ai_advisor.py`)

```python
import json
from pathlib import Path
import anthropic

_KB_PATH = Path("docs/pet_care_kb.json")

def retrieve_care_facts(species: str, breed: str) -> list[str]:
    kb = json.loads(_KB_PATH.read_text())
    species_data = kb.get(species.lower(), {})
    general = species_data.get("general", [])
    breed_specific = species_data.get(breed.lower(), [])
    return general + breed_specific

def suggest_tasks_for_pet(species: str, breed: str, age_years: float, weight_kg: float) -> str:
    facts = retrieve_care_facts(species, breed)
    context = "\n".join(f"- {f}" for f in facts) if facts else "No specific facts found."

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=(
            "You are a veterinary care assistant for the PawPal+ app. "
            "Based on the pet profile and care facts provided, suggest a list of daily care tasks. "
            "Return ONLY a JSON array of objects with keys: name, category, duration_minutes, priority (1-5), "
            "is_required (bool), frequency (daily/twice_daily/weekly), notes (HH:MM start time)."
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Pet profile:\n"
                f"- Species: {species}\n"
                f"- Breed: {breed}\n"
                f"- Age: {age_years} years\n"
                f"- Weight: {weight_kg} kg\n\n"
                f"Relevant care facts:\n{context}\n\n"
                f"Suggest 4–6 appropriate care tasks for this pet."
            )
        }]
    )
    return message.content[0].text
```

### Agent Prompt

```
You are implementing a RAG (Retrieval-Augmented Generation) feature for the PawPal+ app.
The project is a Python/Streamlit pet care scheduler located in the current directory.
The main logic is in pawpal_system.py and the UI is in app.py.

Your task:

1. Create the file `docs/pet_care_kb.json` with a knowledge base of pet care facts.
   Structure it as: { "dog": { "general": [...], "golden retriever": [...], ... }, "cat": { ... } }
   Include at least 3 general facts per species and 3 breed-specific facts for:
   dogs: golden retriever, labrador, chihuahua, german shepherd
   cats: persian, siamese, maine coon

2. Create the file `ai_advisor.py` with two functions:
   - retrieve_care_facts(species: str, breed: str) -> list[str]
     Loads pet_care_kb.json, returns general + breed-specific facts for that species/breed combo.
     Returns an empty list (not an error) if no match is found.
   - suggest_tasks_for_pet(species, breed, age_years, weight_kg) -> str
     Calls the Anthropic Claude API (model: claude-sonnet-4-6).
     Builds a prompt that includes the retrieved facts as context.
     System prompt: "You are a veterinary care assistant for PawPal+..."
     Returns the raw JSON string from Claude (a list of task objects).

3. Modify `app.py`:
   - After the "Add Pet" expander section (around line 130), add a new expander called
     "🤖 AI Task Suggestions" that:
     a. Has a selectbox to choose a pet from owner.pets
     b. Has a button "Get AI Suggestions"
     c. Calls suggest_tasks_for_pet() and parses the returned JSON
     d. Displays the suggestions in a st.dataframe
     e. Has an "Add All to Schedule" button that creates CareTask objects and calls pet.add_task()

4. Add `anthropic` to requirements.txt if not already present.

5. Add ANTHROPIC_API_KEY to .gitignore if not already there.

Do not modify any existing classes in pawpal_system.py. Only add to app.py and create new files.
Make sure all JSON parsing has try/except so the UI never crashes on a malformed API response.
```

---

## 2. Agentic Workflow — Self-Correcting Plan Generator

### What It Means for PawPal+

`Plan.generate()` is currently a stub. This feature implements it as a multi-step agentic loop:
1. **Plan** — build an initial schedule respecting required tasks and time budget
2. **Check** — detect conflicts using `get_conflicts()`
3. **Fix** — if conflicts exist, use `find_next_available_slot()` to reassign start times
4. **Repeat** — up to 3 iterations until no conflicts remain or max iterations hit

The agent also writes human-readable reasoning into `Plan.reasoning` explaining its decisions.

### Architecture

```
Plan.generate(owner, pet, date)
        │
        ▼
  Step 1: Sync vet tasks → pet.sync_vet_tasks()
        │
        ▼
  Step 2: Separate required vs optional tasks
  Always add required tasks first (regardless of budget)
        │
        ▼
  Step 3: Fill remaining time with optional tasks (sorted by priority)
        │
        ▼
  Step 4: Call Claude to generate reasoning text
        │
        ▼
  Step 5: get_conflicts() → any conflicts?
     YES ──► find_next_available_slot() for each conflict
             reassign start times in task.notes
             loop back to Step 5 (max 3 iterations)
     NO  ──► return final Plan
```

### Files to Create / Modify

| File | Action | Purpose |
|------|--------|---------|
| `plan_agent.py` | Create | Agentic loop logic separate from core domain model |
| `pawpal_system.py` | Modify | Implement `Plan.generate()` and `Plan.get_summary()` stubs |
| `app.py` | Modify | Replace raw schedule generation with `Plan.generate()` call |
| `requirements.txt` | Modify | Add `anthropic` |

### Agentic Loop Design (`plan_agent.py`)

```python
import anthropic
import json
from pawpal_system import Owner, Pet, Plan, Schedule, CareTask

MAX_ITERATIONS = 3

def generate_plan_with_agent(owner: Owner, pet: Pet, date: str) -> Plan:
    client = anthropic.Anthropic()

    # Step 1: Build initial schedule
    pet.sync_vet_tasks()
    required = [t for t in pet.care_tasks if t.is_required]
    optional = sorted(
        [t for t in pet.care_tasks if not t.is_required],
        key=lambda t: t.priority, reverse=True
    )

    schedule = Schedule(date=date, owner=owner, pet=pet, tasks=list(required))
    budget_used = sum(t.duration_minutes for t in required)
    skipped = []

    for task in optional:
        if budget_used + task.duration_minutes <= owner.available_time_minutes:
            schedule.tasks.append(task)
            budget_used += task.duration_minutes
        else:
            skipped.append(task)

    # Step 2: Agentic conflict-resolution loop
    warnings = []
    for iteration in range(MAX_ITERATIONS):
        conflicts = schedule.get_conflicts()
        if not conflicts:
            break
        warnings.extend(conflicts)
        for conflict_msg in conflicts:
            # Find a free slot and reassign the lower-priority conflicting task
            slot = schedule.find_next_available_slot(30)
            if slot:
                # Reassign the last conflicting task's start time
                _reassign_conflict(schedule, conflict_msg, slot)

    # Step 3: Ask Claude for reasoning
    task_summary = "\n".join(
        f"- {t.name} ({t.category}, {t.duration_minutes} min, priority {t.priority})"
        for t in schedule.tasks
    )
    skipped_summary = ", ".join(t.name for t in skipped) or "none"

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=(
            "You are PawPal+, a pet care scheduling assistant. "
            "Write a friendly 2-3 sentence explanation of the generated schedule. "
            "Mention why required tasks were prioritized and what was skipped if anything."
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Pet: {pet.name} ({pet.species}, {pet.breed})\n"
                f"Owner available time: {owner.available_time_minutes} min\n"
                f"Scheduled tasks:\n{task_summary}\n"
                f"Skipped optional tasks: {skipped_summary}"
            )
        }]
    )
    reasoning = response.content[0].text

    plan = Plan(schedule=schedule, reasoning=reasoning,
                skipped_tasks=skipped, warnings=warnings)
    return plan


def _reassign_conflict(schedule: Schedule, conflict_msg: str, new_slot: str) -> None:
    # Extract task names from conflict message and push the second one to the new slot
    for task in reversed(schedule.tasks):
        if task.name in conflict_msg and task.notes != new_slot:
            task.notes = new_slot
            break
```

### Agent Prompt

```
You are implementing an Agentic Workflow feature for the PawPal+ app.
The project is a Python/Streamlit pet care scheduler. Key files:
- pawpal_system.py: domain model (CareTask, Pet, Owner, Schedule, Plan classes)
- app.py: Streamlit UI
- Plan.generate() at line ~477 in pawpal_system.py is currently a stub (just `pass`)

Your task:

1. Implement `Plan.generate(owner, pet, date)` in pawpal_system.py.
   Follow the docstring that is already there:
   - Call pet.sync_vet_tasks() first
   - Always include required tasks (is_required=True) regardless of time budget
   - Fill remaining time (owner.available_time_minutes) with optional tasks sorted by priority desc
   - Record skipped tasks in self.skipped_tasks
   - Add a warning string for each skipped required task (there should be none, but guard anyway)
   Do NOT call the Claude API from inside Plan.generate() — keep the domain model API-free.

2. Implement `Plan.get_summary()` in pawpal_system.py.
   Return a multiline string:
   - Line 1: "Plan for [pet.name] on [date]"
   - Line 2: "[N] tasks scheduled, [M] skipped"
   - Line 3: "Total time: [X] min / [budget] min available"
   - Line 4+: one line per warning if any

3. Implement `Plan.get_warnings()` — simply return self.warnings.

4. Create `plan_agent.py` with a function:
   generate_plan_reasoning(plan: Plan) -> str
   This function takes a completed Plan object and calls the Anthropic Claude API
   (model: claude-sonnet-4-6) to generate a friendly 2-3 sentence explanation
   of the schedule decisions. It receives the scheduled tasks, skipped tasks,
   and pet profile as context in the prompt.
   Return the reasoning string.

5. Create `conflict_resolver.py` with a function:
   resolve_conflicts(schedule: Schedule, max_iterations: int = 3) -> list[str]
   This function runs a loop up to max_iterations times:
   - Call schedule.get_conflicts()
   - If no conflicts, break and return []
   - For each conflict, call schedule.find_next_available_slot(duration) to find a free slot
   - Reassign the lower-priority conflicting task's notes field to that slot
   - Return a list of warning strings for any conflicts that could not be resolved

6. Modify `app.py` in the "Generate Schedule" button section (around line 260):
   - After building the schedule, call resolve_conflicts(schedule) from conflict_resolver.py
   - After generating the plan, call generate_plan_reasoning(plan) from plan_agent.py
   - Display plan.reasoning in a st.info() box below the schedule table
   - Display plan.get_summary() in a st.caption()

Keep all Claude API calls in the new files (plan_agent.py, conflict_resolver.py).
Never put API calls inside pawpal_system.py domain classes.
Add ANTHROPIC_API_KEY instructions as a comment at the top of plan_agent.py.
```

---

## 3. Fine-Tuned / Specialized Model — Veterinary AI Advisor

### What It Means for PawPal+

Instead of a generic AI response, the system uses a carefully crafted system prompt that makes Claude behave as a board-certified veterinary advisor with specific constraints (never recommend skipping required tasks, always flag age-related risks, use plain language). This is the "fine-tuning through prompting" approach — appropriate when you don't have training data for a true fine-tune.

### Architecture

```
User clicks "Ask the Vet AI"
        │
        ▼
  vet_advisor.py: build_vet_system_prompt(pet) → detailed system prompt
        │
        ▼
  Claude API called with veterinary persona + pet context
        │
        ▼
  Response shown in chat interface (st.chat_message)
        │
        ▼
  Conversation history stored in st.session_state
```

### System Prompt Design

The key insight is that the system prompt encodes veterinary rules as hard constraints:

```
You are Dr. PawPal, a board-certified veterinary advisor embedded in the PawPal+ app.

RULES YOU ALWAYS FOLLOW:
1. Never recommend skipping a task marked as required=True.
2. Always flag any task involving a pet over 8 years old that includes high-impact exercise.
3. Medical and nutrition tasks always take priority over enrichment and grooming tasks.
4. If a user's available time is less than the sum of required tasks, say so explicitly.
5. Respond in plain, friendly language — no jargon. Maximum 3 sentences per response.
6. If unsure about a medical condition, always recommend consulting a real veterinarian.

CURRENT PET CONTEXT:
- Name: {name}
- Species: {species}
- Breed: {breed}
- Age: {age_years} years
- Weight: {weight_kg} kg
- Medical notes: {medical_notes}
```

### Files to Create / Modify

| File | Action | Purpose |
|------|--------|---------|
| `vet_advisor.py` | Create | System prompt builder + Claude chat interface |
| `app.py` | Modify | Add "Ask the Vet AI" chat tab |
| `requirements.txt` | Modify | Add `anthropic` |

### Agent Prompt

```
You are implementing a Specialized Model feature for the PawPal+ app.
The app is a Python/Streamlit pet care scheduler. The UI is in app.py.
The domain model (Pet, CareTask, etc.) is in pawpal_system.py.

Your task:

1. Create `vet_advisor.py` with the following:

   a. Function build_vet_system_prompt(pet: Pet) -> str
      Returns a detailed system prompt that:
      - Gives Claude the persona of "Dr. PawPal, a veterinary care advisor"
      - Embeds the pet's profile (species, breed, age, weight, medical_notes) as context
      - Includes these hard rules as numbered constraints:
        * Never recommend skipping required tasks
        * Flag high-impact exercise for pets over 8 years old
        * Medical/nutrition tasks take priority over grooming/enrichment
        * Always recommend a real vet for medical symptoms
        * Keep answers to 2-3 sentences max, in plain language
      - Lists the pet's current care tasks as a summary

   b. Function ask_vet(pet: Pet, user_message: str, history: list[dict]) -> str
      - Calls the Anthropic Claude API (model: claude-sonnet-4-6)
      - Uses build_vet_system_prompt(pet) as the system prompt
      - Passes the full conversation history (list of {role, content} dicts)
      - Appends the new user_message to the history before calling
      - Returns the assistant's text response
      - Uses max_tokens=512

2. Modify `app.py` to add a new section after the schedule section:
   Add a st.header("🩺 Ask the Vet AI") section that:
   - Has a selectbox to choose which pet to ask about
   - Displays conversation history from st.session_state["vet_chat_history"]
     using st.chat_message("user") and st.chat_message("assistant")
   - Has a st.chat_input("Ask Dr. PawPal...") input
   - On submit: calls ask_vet(selected_pet, user_message, history) from vet_advisor.py
   - Appends both the user message and AI response to session_state history
   - Uses st.rerun() to refresh the chat display
   - Has a "Clear chat" button that resets the history

3. The chat history in session_state should be a list of {"role": "user"/"assistant", "content": "..."} dicts.
   Initialize it as [] if not present.

4. Add `anthropic` to requirements.txt if not already present.

Make sure the chat input gracefully handles the case where no pets have been added yet
(show st.warning instead of crashing).
```

---

## 4. Reliability & Testing System — AI Consistency Evaluator

### What It Means for PawPal+

A script that automatically tests whether the AI-generated plans and suggestions are consistent, correct, and follow the rules. It runs the same scenario multiple times and checks for variance, then reports a consistency score. This is especially important because the AI features from sections 1–3 make non-deterministic choices.

### What It Tests

| Test | Pass Condition |
|------|---------------|
| Required tasks always included | 100% of generated plans include all `is_required=True` tasks |
| No budget overrun on required | Required tasks alone never exceed `available_time_minutes` |
| Conflict detection accuracy | `get_conflicts()` correctly identifies known overlaps (deterministic) |
| AI reasoning relevance | Claude's reasoning mentions the pet's name and at least one task |
| Suggestion parse reliability | AI task suggestions parse as valid JSON 9/10 times |
| Response consistency | Running the same prompt 3x produces task lists with >80% name overlap |

### Architecture

```
eval_runner.py
    │
    ├── run_deterministic_tests()   ← pure logic, no API calls
    │       Schedule, Plan, conflict detection
    │
    ├── run_ai_consistency_tests()  ← calls Claude API N times
    │       same prompt → compare outputs → score overlap
    │
    └── generate_report()           ← writes eval_report.md
```

### Files to Create / Modify

| File | Action | Purpose |
|------|--------|---------|
| `eval_runner.py` | Create | Full evaluation suite |
| `eval_report.md` | Auto-generated | Human-readable results (gitignored) |
| `.gitignore` | Modify | Ignore `eval_report.md` |

### Agent Prompt

```
You are implementing a Reliability & Testing System for the PawPal+ app.
The project is a Python/Streamlit pet care scheduler.
The domain model is in pawpal_system.py. AI features may be in ai_advisor.py, plan_agent.py,
vet_advisor.py (these may or may not exist yet — handle ImportError gracefully).

Your task: create `eval_runner.py` that can be run as `python eval_runner.py`

The file must contain these sections:

─── SECTION 1: Deterministic Tests (no API calls) ───────────────────────────────

1. test_required_tasks_always_included()
   Create a Pet with 3 required tasks and 2 optional tasks.
   Set owner.available_time_minutes low enough that not all optional tasks fit.
   Call Plan.generate(owner, pet, date).
   Assert that all required tasks appear in plan.schedule.tasks.
   Return ("PASS", details) or ("FAIL", details).

2. test_no_conflicts_in_generated_plan()
   Create a schedule with 4 tasks whose HH:MM times do not overlap.
   Assert schedule.get_conflicts() returns [].
   Add two tasks that DO overlap.
   Assert schedule.get_conflicts() returns exactly 1 conflict string.
   Return ("PASS", details) or ("FAIL", details).

3. test_next_occurrence_recurrence()
   Create a daily CareTask. Call mark_task_complete() via Schedule.
   Assert the next occurrence has completed=False and a later scheduled_date.
   Return ("PASS", details) or ("FAIL", details).

4. test_budget_respected_for_optional()
   Create 5 optional tasks of 30 min each (total 150 min).
   Set available_time_minutes=60.
   Generate plan. Assert total scheduled time <= 60 min.
   Return ("PASS", details) or ("FAIL", details).

─── SECTION 2: AI Consistency Tests (require API) ───────────────────────────────

5. test_ai_suggestion_parses_as_json()
   Try to import suggest_tasks_for_pet from ai_advisor (skip if not found).
   Call it once with a fixed pet profile (Dog, Golden Retriever, 3 years, 25 kg).
   Try json.loads() on the result.
   Assert it is a list of dicts each containing keys: name, category, duration_minutes, priority.
   Return ("PASS", details), ("FAIL", details), or ("SKIP", "ai_advisor not found").

6. test_ai_reasoning_mentions_pet()
   Try to import generate_plan_reasoning from plan_agent (skip if not found).
   Build a plan with 2 tasks and call generate_plan_reasoning(plan).
   Assert the returned string contains the pet's name.
   Assert len(response) > 50 (not an empty response).
   Return ("PASS", details), ("FAIL", details), or ("SKIP", "plan_agent not found").

7. test_ai_suggestion_consistency()
   Try to import suggest_tasks_for_pet from ai_advisor (skip if not found).
   Call it 3 times with identical inputs (Dog, Labrador, 2 years, 30 kg).
   Parse each response as JSON and collect all task names.
   Find the intersection of task names across all 3 responses.
   Assert overlap >= 50% of the union (at least half the tasks are consistent).
   Return ("PASS", f"overlap={pct:.0%}"), ("FAIL", ...), or ("SKIP", ...).

─── SECTION 3: Report Generator ────────────────────────────────────────────────

8. generate_report(results: list[tuple[str, str, str]]) -> str
   results is a list of (test_name, status, details) tuples.
   Returns a markdown string:
   - Title: "# PawPal+ AI Reliability Report"
   - Date: today's date
   - Summary table: | Test | Status | Details |
   - Overall score: "X / Y tests passed"
   - Section for FAILED tests with details

─── MAIN ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    Run all tests, collect results, call generate_report(), print to console,
    and also write to eval_report.md.
    Exit with code 0 if all non-skipped tests pass, exit code 1 otherwise.

Important notes:
- Never crash on ImportError for optional AI modules — use try/except and return SKIP
- Never crash on API errors — catch anthropic.APIError and return FAIL with the error message
- Plan.generate() may still be a stub (pass) — if it returns None, mark that test as SKIP
- Each test function must be fully self-contained (creates its own fixtures, no shared state)
- Print a progress line before each test: "Running: test_name..."
```

---

## Dependencies Summary

Add these to `requirements.txt`:

```
anthropic>=0.40.0
```

Set the API key as an environment variable before running:

```bash
export ANTHROPIC_API_KEY="your-key-here"
```

Or create a `.env` file (make sure it is in `.gitignore`):

```
ANTHROPIC_API_KEY=your-key-here
```

---

## Implementation Order (Recommended)

If implementing all four features, this order minimizes rework:

1. **Feature 4 first** — the eval runner catches regressions as you build the others
2. **Feature 2** — implement `Plan.generate()` (the most impactful stub to fill)
3. **Feature 1** — add RAG suggestions to enrich the data flowing into the plan
4. **Feature 3** — the chat interface builds on the working plan and task data

---

## Quick Reference — Key Existing Methods

These methods in [pawpal_system.py](../pawpal_system.py) are already implemented and should be reused by all new features:

| Method | Location | Use In |
|--------|----------|--------|
| `Schedule.get_conflicts()` | `Schedule` class | Features 2, 4 |
| `Schedule.find_next_available_slot()` | `Schedule` class | Feature 2 |
| `Schedule.sort_by_priority_then_time()` | `Schedule` class | Feature 2 |
| `Pet.sync_vet_tasks()` | `Pet` class | Feature 2 |
| `CareTask.next_occurrence()` | `CareTask` class | Feature 4 |
| `Owner.save_to_json()` / `load_from_json()` | `Owner` class | All features |
