# Model Card — PawPal+ AI System

## Project Identity

**Base project:** PawPal+ (Modules 1–3) — a Streamlit pet care scheduling app.
**Final project:** PawPal+ with four AI capabilities added: RAG task suggestions, agentic conflict resolution, a specialized veterinary advisor, and an automated reliability test suite.
**Model used:** `claude-sonnet-4-6` (Anthropic) via the Python SDK across all AI features.

---

## 1. Intended Use

**Primary use case:** Help pet owners plan daily care tasks by suggesting breed-appropriate routines, explaining scheduling decisions in plain language, and answering care questions through a conversational interface.

**Who it is for:** Individual pet owners managing one or more pets, especially those with busy schedules who need a prioritized daily plan they can trust.

**Out of scope:** This system is not a substitute for veterinary diagnosis or medical advice. The Vet AI advisor is explicitly constrained to always redirect medical symptoms to a licensed veterinarian.

---

## 2. AI Collaboration — How Claude Was Used

| Feature | Role of Claude | Human-written counterpart |
|---------|---------------|--------------------------|
| RAG Suggestions (`ai_advisor.py`) | Converts retrieved KB facts + pet profile into structured JSON task list | `retrieve_care_facts()` — pure Python KB lookup |
| Plan Reasoning (`plan_agent.py`) | Writes a 2-3 sentence plain-language explanation of the schedule | `Plan.generate()` — pure Python scheduling logic |
| Conflict Resolution (`conflict_resolver.py`) | None — this is fully algorithmic | `find_next_available_slot()`, `get_conflicts()` |
| Vet AI Chat (`vet_advisor.py`) | Answers owner questions in the Dr. PawPal persona | System prompt with 7 hard-coded clinical rules |
| Eval Runner (`eval_runner.py`) | Tested for JSON validity and response consistency | 4 deterministic tests require no API call |

**Key decision:** Claude was never given scheduling authority. All decisions about which tasks to include, skip, or reorder were made by deterministic Python code. Claude's role was limited to generating human-readable text and structured suggestions — outputs that are easy to review and verify.

---

## 3. AI Collaboration During Development

Claude (via Claude Code) was used throughout the development process for:

- **Generating test cases** — writing the 15-test pytest suite and the 7-test eval runner.
- **Implementing stub methods** — filling in `Plan.generate()`, `Schedule.add_task()`, and related methods from docstring descriptions.
- **Refactoring** — improving the conflict resolution loop and the system prompt structure.
- **Documentation** — drafting this model card and the implementation plan in `docs/`.

**One moment where AI suggestions were not accepted as-is:** The initial conflict resolver draft used a recursive approach that could infinite-loop if `find_next_available_slot()` returned a time already occupied by the same task being moved. This was caught during review and replaced with a simple bounded iteration loop (`for _ in range(max_iterations)`), which is safer and easier to reason about.

**Verification approach:** Every AI-generated method was validated against the existing test suite (`pytest`) before being kept. New behavior (e.g., `Plan.generate()`) was covered by new eval tests before trusting it.

---

## 4. Known Biases and Limitations

**Knowledge base bias:** The `docs/pet_care_kb.json` file was written manually and covers only 8 dog breeds and 4 cat breeds. Pets outside these breeds receive only general species-level facts, which may result in less tailored suggestions.

**Model knowledge cutoff:** Claude's training data has a cutoff of August 2025. Veterinary best practices that changed after that date will not be reflected in responses.

**Language and cultural bias:** The knowledge base and all prompts are written in English. The app has no localization support.

**Prompt-based specialization vs. fine-tuning:** The Dr. PawPal persona relies entirely on a system prompt to enforce clinical rules. A truly fine-tuned model would be more robust; the prompt approach can be overridden by sufficiently unusual user inputs.

**Consistency variance:** Across three identical API calls with the same pet profile, the AI suggestion consistency test shows 50–80% task-name overlap. Claude varies phrasing between runs, so task intent is consistent but exact names differ — this matters when comparing outputs programmatically.

**No persistent memory:** The Vet AI chat history resets on page reload. There is no cross-session context, so the advisor cannot track a pet's health trajectory over time.

---

## 5. Testing Results

### Deterministic Tests (no API key required)

| Test | Result | Notes |
|------|--------|-------|
| Required tasks always included in plan | ✅ PASS | Works even when budget is tight |
| Conflict detection accuracy | ✅ PASS | 0 false positives; overlaps correctly flagged |
| Daily task recurrence (next occurrence) | ✅ PASS | New UUID, correct date, `completed=False` |
| Budget respected for optional tasks | ✅ PASS | Never exceeds `available_time_minutes` |

All 15 original unit tests continue to pass after adding the AI layer.

### AI Consistency Tests (require `ANTHROPIC_API_KEY`)

| Test | Result | Notes |
|------|--------|-------|
| AI suggestions parse as valid JSON | ✅ PASS | All required keys present |
| Plan reasoning mentions pet name | ✅ PASS | Response > 50 chars, name always present |
| Suggestion consistency across 3 runs | ⚠️ VARIABLE | 50–80% overlap; task intent consistent, names vary |

### What Worked Well

- Keeping the domain model API-free made all core scheduling logic trivially testable without mocking.
- The 7 hard-coded rules in the Vet AI system prompt produced highly predictable behavior.
- The RAG retrieval grounded suggestions in validated facts, reducing hallucinated or generic advice.

### What Didn't / Areas for Improvement

- AI consistency test is brittle — name-based comparison penalizes valid paraphrasing. A semantic similarity check (e.g., embedding cosine similarity) would be a better metric.
- `eval_runner.py` AI tests fail with a clear error message when no API key is set, but they show as FAIL rather than SKIP. Detecting the missing key and returning SKIP would be cleaner.
- The conflict resolver occasionally moves a task to a slot that conflicts with another newly moved task in the same iteration, requiring the next iteration to fix it. A smarter algorithm would sort all conflicts by priority before reassigning.

---

## 6. Reflection

**What this project taught about AI and problem-solving:**

The most important lesson was that **the hardest part of building an AI system is deciding what the AI should NOT do.** Every feature required a deliberate boundary: Claude explains the schedule, but Python makes it. Claude suggests tasks, but the user adds them. Claude answers care questions, but real symptoms go to a real vet. Drawing those boundaries early made the system more trustworthy and much easier to test.

The second lesson was that **reliability is a design choice, not a property of the model.** Claude is capable and generally accurate, but "generally accurate" is not good enough for something as consequential as a pet's medication schedule. Building the eval runner before trusting the AI features — running the same scenario multiple times and measuring consistency — changed how the AI outputs were used: as suggestions to review, not decisions to execute.

Finally, working iteratively with Claude Code on this project reinforced that **AI pair programming works best when the human holds the design intent.** Claude can fill in methods, generate tests, and write documentation faster than any human, but it does not know which trade-offs matter for this specific project. Keeping that judgment human-side, and using AI for execution, produced better results than either approach alone.
