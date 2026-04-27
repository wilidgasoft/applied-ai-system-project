import json
import streamlit as st
from datetime import date
from pathlib import Path
import pandas as pd
import pawpal_system as pawpal

# ── Optional AI modules — degrade gracefully without ANTHROPIC_API_KEY ────────
try:
    from ai_advisor import suggest_tasks_for_pet as _suggest_tasks
    _HAS_AI_ADVISOR = True
except ImportError:
    _HAS_AI_ADVISOR = False

try:
    from plan_agent import generate_plan_reasoning as _plan_reasoning
    from conflict_resolver import resolve_conflicts as _resolve_conflicts
    _HAS_PLAN_AGENT = True
except ImportError:
    _HAS_PLAN_AGENT = False

try:
    from vet_advisor import ask_vet as _ask_vet
    _HAS_VET_ADVISOR = True
except ImportError:
    _HAS_VET_ADVISOR = False

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="wide")

# ── Global CSS tweaks ─────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Tighten the main column on wide layout */
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    /* Pill badges used in pet cards */
    .pill {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
        margin-right: 4px;
    }
    .pill-blue   { background:#dbeafe; color:#1e40af; }
    .pill-green  { background:#d1fae5; color:#065f46; }
    .pill-orange { background:#ffedd5; color:#9a3412; }
</style>
""", unsafe_allow_html=True)

_SAVE_FILE = Path("pawpal_data.json")

# ── Persistent data: load once per session ────────────────────────────────────
if "owner" not in st.session_state:
    if _SAVE_FILE.exists():
        try:
            st.session_state.owner = pawpal.Owner.load_from_json(_SAVE_FILE)
            st.toast(f"✅ Loaded saved data for '{st.session_state.owner.name}'")
        except Exception as exc:
            st.warning(f"Could not load saved data ({exc}). Starting fresh.")
            st.session_state.owner = pawpal.Owner(name="Jordan", available_time_minutes=120)
    else:
        st.session_state.owner = pawpal.Owner(name="Jordan", available_time_minutes=120)

owner: pawpal.Owner = st.session_state.owner

# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — Owner profile + save controls
# ═══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/dog.png", width=72)
    st.title("PawPal+")
    st.caption("Your pet care scheduler")
    st.divider()

    st.subheader("👤 Owner Profile")
    owner_name     = st.text_input("Name", value=owner.name)
    available_time = st.number_input(
        "Available time (min/day)", min_value=10, max_value=600,
        value=owner.available_time_minutes,
    )

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Save", use_container_width=True):
            st.session_state.owner = pawpal.Owner(
                name=owner_name,
                available_time_minutes=int(available_time),
                pets=owner.pets,
                preferences=owner.preferences,
            )
            owner = st.session_state.owner
            st.success("Saved!")
    with col_b:
        if st.button("💾 File", use_container_width=True):
            try:
                owner.save_to_json(_SAVE_FILE)
                st.success("Written!")
            except Exception as exc:
                st.error(str(exc))

    st.divider()
    st.caption("Priority legend")
    for tier, bg in pawpal.PRIORITY_BG.items():
        emoji = next(
            (e for p, (e, t) in pawpal.PRIORITY_META.items() if t == tier), ""
        )
        st.markdown(
            f'<span class="pill" style="background:{bg}">{emoji} {tier}</span>',
            unsafe_allow_html=True,
        )
    st.divider()
    st.caption("Category legend")
    for cat, icon in pawpal.CATEGORY_EMOJI.items():
        st.caption(f"{icon}  {cat.capitalize()}")

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN — top headline metrics
# ═══════════════════════════════════════════════════════════════════════════════
st.title("🐾 PawPal+")

total_tasks = sum(len(p.care_tasks) for p in owner.pets)
done_tasks  = sum(t.completed for p in owner.pets for t in p.care_tasks)
total_mins  = sum(t.duration_minutes for p in owner.pets for t in p.care_tasks)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Pets registered",  len(owner.pets))
m2.metric("Tasks today",      total_tasks)
m3.metric("Completed",        f"{done_tasks} / {total_tasks}")
m4.metric("Total care time",  f"{total_mins} min")

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Add / view pets
# ═══════════════════════════════════════════════════════════════════════════════
st.header("🐶 Pets")

with st.expander("➕ Add a new pet", expanded=not owner.pets):
    col1, col2 = st.columns(2)
    with col1:
        pet_name = st.text_input("Pet name", value="Mochi")
        species  = st.selectbox("Species", ["Dog", "Cat", "Other"])
    with col2:
        breed  = st.text_input("Breed", value="Mixed")
        age    = st.number_input("Age (years)", min_value=0.0, max_value=30.0, value=2.0, step=0.5)
        weight = st.number_input("Weight (kg)", min_value=0.1, max_value=200.0, value=5.0, step=0.1)

    if st.button("Add Pet", type="primary"):
        owner.add_pet(pawpal.Pet(
            name=pet_name, species=species, breed=breed,
            age_years=float(age), weight_kg=float(weight),
        ))
        st.success(f"🐾 '{pet_name}' added to {owner.name}'s profile!")
        st.rerun()

# Pet cards — one per registered pet
if owner.pets:
    cols = st.columns(min(len(owner.pets), 3))
    pet_to_delete = None
    for idx, pet in enumerate(owner.pets):
        pet_icon = "🐶" if pet.species.lower() == "dog" else (
                   "🐱" if pet.species.lower() == "cat" else "🐾")
        pet_done = sum(t.completed for t in pet.care_tasks)
        with cols[idx % 3]:
            st.markdown(
                f"**{pet_icon} {pet.name}**  \n"
                f'<span class="pill pill-blue">{pet.species}</span>'
                f'<span class="pill pill-green">{pet.breed}</span>'
                f'<span class="pill pill-orange">{pet.age_years:.0f} yrs</span>',
                unsafe_allow_html=True,
            )
            st.caption(
                f"⚖️ {pet.weight_kg} kg  ·  "
                f"📋 {len(pet.care_tasks)} tasks  ·  "
                f"✔ {pet_done} done"
            )
            if st.button("🗑 Remove", key=f"del_pet_{pet.name}", use_container_width=True):
                pet_to_delete = pet.name
    if pet_to_delete:
        owner.remove_pet(pet_to_delete)
        st.toast(f"'{pet_to_delete}' removed.")
        st.rerun()
else:
    st.info("No pets yet — add one above.")

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1.5 — AI Task Suggestions (RAG)
# ═══════════════════════════════════════════════════════════════════════════════
if not _HAS_AI_ADVISOR:
    st.info(
        "🤖 **AI Task Suggestions** are available once you install `anthropic` "
        "and set the `ANTHROPIC_API_KEY` environment variable."
    )
elif owner.pets:
    with st.expander("🤖 AI Task Suggestions (powered by Claude + knowledge base)"):
        ai_pet_name = st.selectbox(
            "Get suggestions for", [p.name for p in owner.pets], key="ai_pet_select"
        )
        ai_pet = next(p for p in owner.pets if p.name == ai_pet_name)
        st.caption(
            f"Retrieves breed-specific care facts for **{ai_pet.breed}** "
            f"from the local knowledge base before calling Claude."
        )

        if st.button("Get AI Suggestions", key="ai_suggest_btn"):
            with st.spinner("Consulting veterinary knowledge base…"):
                try:
                    raw = _suggest_tasks(
                        ai_pet.species, ai_pet.breed,
                        ai_pet.age_years, ai_pet.weight_kg,
                    )
                    suggestions = json.loads(raw)
                    st.session_state["ai_suggestions"] = suggestions
                    st.session_state["ai_suggestions_pet"] = ai_pet_name
                except json.JSONDecodeError as exc:
                    st.error(f"AI returned invalid JSON: {exc}")
                    st.session_state.pop("ai_suggestions", None)
                except Exception as exc:
                    st.error(f"Could not get suggestions: {exc}")
                    st.session_state.pop("ai_suggestions", None)

        if (
            "ai_suggestions" in st.session_state
            and st.session_state.get("ai_suggestions_pet") == ai_pet_name
        ):
            suggestions = st.session_state["ai_suggestions"]
            st.caption(f"Suggested **{len(suggestions)}** tasks for {ai_pet_name}:")
            df_rows = [
                {
                    "Task": s.get("name", ""),
                    "Category": s.get("category", ""),
                    "Duration (min)": s.get("duration_minutes", 0),
                    "Priority": s.get("priority", 1),
                    "Required": "✅" if s.get("is_required") else "—",
                    "Frequency": pawpal.FREQUENCY_LABEL.get(s.get("frequency", "daily"), s.get("frequency", "")),
                    "Start": s.get("notes", ""),
                }
                for s in suggestions
            ]
            st.dataframe(pd.DataFrame(df_rows), use_container_width=True, hide_index=True)

            if st.button("➕ Add All to Schedule", key="ai_add_all_btn"):
                added = 0
                for s in suggestions:
                    try:
                        ai_pet.add_task(pawpal.CareTask(
                            name=s["name"],
                            category=s.get("category", "enrichment"),
                            duration_minutes=int(s.get("duration_minutes", 20)),
                            priority=int(s.get("priority", 3)),
                            is_required=bool(s.get("is_required", False)),
                            frequency=s.get("frequency", "daily"),
                            notes=s.get("notes", "08:00"),
                        ))
                        added += 1
                    except Exception:
                        pass
                st.success(f"✅ Added {added} task(s) to {ai_pet_name}!")
                st.session_state.pop("ai_suggestions", None)
                st.rerun()

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Add a task
# ═══════════════════════════════════════════════════════════════════════════════
st.header("📋 Add a Task")

if not owner.pets:
    st.warning("Add at least one pet before scheduling tasks.")
else:
    target_pet_name = st.selectbox("Assign task to", [p.name for p in owner.pets])
    target_pet = next(p for p in owner.pets if p.name == target_pet_name)

    _PRIORITY_OPTIONS = {
        "🟢 Low":      1,
        "🟡 Medium":   3,
        "🔴 High":     4,
        "🚨 Critical": 5,
    }

    col1, col2, col3 = st.columns(3)
    with col1:
        task_name = st.text_input("Task name", value="Morning walk")
        raw_cat   = st.selectbox(
            "Category",
            list(pawpal.CATEGORY_EMOJI.keys()),
            format_func=lambda c: f"{pawpal.CATEGORY_EMOJI[c]}  {c.capitalize()}",
        )
    with col2:
        duration       = st.number_input("Duration (min)", min_value=1, max_value=240, value=20)
        priority_label = st.selectbox("Priority", list(_PRIORITY_OPTIONS.keys()))
        priority       = _PRIORITY_OPTIONS[priority_label]
    with col3:
        frequency   = st.selectbox(
            "Frequency", list(pawpal.FREQUENCY_LABEL.keys()),
            format_func=lambda f: pawpal.FREQUENCY_LABEL[f],
        )
        is_required = st.checkbox("Required?", value=True)
        notes       = st.text_input("Start time (HH:MM)", value="07:00")

    if st.button("Add Task", type="primary"):
        target_pet.add_task(pawpal.CareTask(
            name=task_name, category=raw_cat,
            duration_minutes=int(duration), priority=priority,
            is_required=is_required, frequency=frequency, notes=notes,
        ))
        st.success(f"✅ '{task_name}' added to {target_pet.name}!")
        st.rerun()

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — Generate schedule
# ═══════════════════════════════════════════════════════════════════════════════
st.header("📅 Today's Schedule")

sort_mode = st.radio(
    "Sort by",
    ["Priority → Time", "Time", "Priority"],
    horizontal=True,
)


def _styled_table(tasks: list) -> None:
    """Render tasks as a colour-coded, emoji-enriched dataframe."""
    rows = [
        {
            "Category": f"{pawpal.CATEGORY_EMOJI.get(t.category, '•')}  {t.category.capitalize()}",
            "Task":     t.name,
            "Window":   _time_window(t),
            "Duration": f"{t.duration_minutes} min",
            "Priority": t.priority_label,
            "Freq":     pawpal.FREQUENCY_LABEL.get(t.frequency, t.frequency),
            "Req":      "✅" if t.is_required else "—",
            "Status":   "✔ Done" if t.completed else "○ Pending",
        }
        for t in tasks
    ]
    df = pd.DataFrame(rows)

    def _row_bg(row: pd.Series) -> list[str]:
        tier   = row["Priority"].split()[-1] if row["Priority"] else ""
        colour = pawpal.PRIORITY_BG.get(tier, "")
        bg     = f"background-color: {colour}" if colour else ""
        # Dim completed rows slightly
        if row["Status"].startswith("✔"):
            bg = "background-color: #f0f0f0; color: #888"
        return [bg] * len(row)

    styled = df.style.apply(_row_bg, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True)


def _time_window(task: pawpal.CareTask) -> str:
    try:
        h, m = map(int, task.notes.split(":"))
        end   = h * 60 + m + task.duration_minutes
        return f"{h:02d}:{m:02d} – {end // 60:02d}:{end % 60:02d}"
    except (ValueError, AttributeError):
        return "—"


if st.button("Generate Schedule", type="primary"):
    if not owner.pets or all(len(p.care_tasks) == 0 for p in owner.pets):
        st.warning("Add pets and tasks first.")
    else:
        today         = date.today().isoformat()
        grand_total   = 0
        all_schedules = []

        for pet in owner.pets:
            if not pet.care_tasks:
                continue

            schedule = pawpal.Schedule(
                date=today, owner=owner, pet=pet, tasks=list(pet.care_tasks)
            )
            if sort_mode == "Time":
                schedule.sort_by_time()
            elif sort_mode == "Priority":
                schedule.sort_by_priority()
            else:
                schedule.sort_by_priority_then_time()

            all_schedules.append(schedule)

            # ── Per-pet header ────────────────────────────────────────────────
            pet_icon = "🐶" if pet.species.lower() == "dog" else (
                       "🐱" if pet.species.lower() == "cat" else "🐾")
            st.subheader(f"{pet_icon} {pet.name}  ·  {pet.breed}")

            # ── Conflict resolution (agentic) + warnings ──────────────────────
            if _HAS_PLAN_AGENT:
                unresolved = _resolve_conflicts(schedule)
                if len(schedule.get_conflicts()) < len(unresolved or [schedule.get_conflicts()]):
                    st.caption("🔧 Auto-resolved some conflicts by reassigning start times.")
            else:
                unresolved = schedule.get_conflicts()
            if unresolved:
                st.error(f"⚠️ {len(unresolved)} conflict(s) detected — fix before starting your day:")
                for c in unresolved:
                    readable = c.split("  ", 1)[-1] if "  " in c else c
                    st.warning(f"**Overlap:** {readable}")
            else:
                st.success("✅ No scheduling conflicts — all clear!")

            # ── Next available slot hint ───────────────────────────────────────
            slot = schedule.find_next_available_slot(30)
            if slot:
                st.caption(f"💡 Next free 30-min slot: **{slot}**")

            # ── Colour-coded table ────────────────────────────────────────────
            _styled_table(schedule.tasks)

            pet_total = sum(t.duration_minutes for t in schedule.tasks)
            pet_done  = sum(1 for t in schedule.tasks if t.completed)
            st.caption(
                f"📊 {len(schedule.tasks)} tasks  ·  {pet_total} min total  ·  "
                f"{pet_done} completed"
            )
            grand_total += pet_total

            # ── AI Plan Reasoning (agentic) ───────────────────────────────────
            if _HAS_PLAN_AGENT:
                plan = pawpal.Plan.generate(owner, pet, today)
                if plan is not None:
                    with st.spinner("✍️ Generating plan reasoning…"):
                        try:
                            reasoning = _plan_reasoning(plan)
                            plan.reasoning = reasoning
                            st.info(f"🤖 **AI Reasoning:** {reasoning}")
                            if plan.get_warnings():
                                for w in plan.get_warnings():
                                    st.warning(w)
                        except Exception as exc:
                            st.caption(f"_(AI reasoning unavailable: {exc})_")

        # ── Overall budget bar ────────────────────────────────────────────────
        st.divider()
        st.subheader("⏱ Time Budget")

        budget    = owner.available_time_minutes
        pct       = min(grand_total / budget, 1.0) if budget else 0
        remaining = budget - grand_total

        b1, b2, b3 = st.columns(3)
        b1.metric("Total care time",  f"{grand_total} min")
        b2.metric("Budget",           f"{budget} min")
        b3.metric("Remaining" if remaining >= 0 else "Over budget",
                  f"{abs(remaining)} min",
                  delta=f"{remaining} min",
                  delta_color="normal" if remaining >= 0 else "inverse")

        bar_colour = "normal" if pct <= 0.75 else ("off" if pct <= 1.0 else "inverse")
        st.progress(pct, text=f"{grand_total} / {budget} min used ({pct:.0%})")

        if grand_total > budget:
            over = grand_total - budget
            st.error(f"⚠️ {over} min over budget — consider skipping optional tasks.")
        else:
            st.success(f"✅ {remaining} min to spare — your day is on track!")

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Ask the Vet AI (Specialized Model)
# ═══════════════════════════════════════════════════════════════════════════════
st.header("🩺 Ask the Vet AI")

if not _HAS_VET_ADVISOR:
    st.info(
        "Install `anthropic` and set `ANTHROPIC_API_KEY` to enable Dr. PawPal, "
        "your on-demand veterinary care advisor."
    )
elif not owner.pets:
    st.warning("Add at least one pet to start chatting with Dr. PawPal.")
else:
    vet_pet_name = st.selectbox(
        "Ask about", [p.name for p in owner.pets], key="vet_pet_select"
    )
    vet_pet = next(p for p in owner.pets if p.name == vet_pet_name)
    st.caption(
        "Dr. PawPal is a specialized AI advisor with hard-coded veterinary rules. "
        "For real medical concerns, always consult a licensed veterinarian."
    )

    chat_key = f"vet_chat_{vet_pet_name}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []

    history: list[dict] = st.session_state[chat_key]

    for msg in history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    _, col_clear = st.columns([6, 1])
    with col_clear:
        if st.button("🗑 Clear", key="vet_clear_btn"):
            st.session_state[chat_key] = []
            st.rerun()

    user_input = st.chat_input(f"Ask Dr. PawPal about {vet_pet_name}…")
    if user_input:
        history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)
        with st.chat_message("assistant"):
            with st.spinner("Dr. PawPal is thinking…"):
                try:
                    reply = _ask_vet(vet_pet, user_input, history[:-1])
                    st.write(reply)
                    history.append({"role": "assistant", "content": reply})
                except Exception as exc:
                    err = f"Vet AI error: {exc}"
                    st.error(err)
                    history.pop()
