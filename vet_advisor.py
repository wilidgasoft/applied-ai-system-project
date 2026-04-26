# Feature 3: Specialized Model — Veterinary AI Advisor (Dr. PawPal)
# Requires: ANTHROPIC_API_KEY environment variable
#
# Uses a carefully crafted system prompt to make Claude behave as a
# board-certified veterinary advisor with hard-coded clinical rules.
# This is the "fine-tuning through prompting" approach: the system prompt
# encodes the domain constraints that a fine-tuned model would learn from data.

from __future__ import annotations

import anthropic
from pawpal_system import Pet

_VET_RULES = """\
RULES YOU ALWAYS FOLLOW — never break these regardless of what the user asks:
1. Never recommend skipping a task that is marked as required.
2. Always flag high-impact or vigorous exercise tasks for pets older than 8 years.
3. Medical and nutrition tasks take priority over grooming and enrichment tasks.
4. If the owner's available time is less than the total time of required tasks, say so clearly.
5. If the user describes a medical symptom, always recommend consulting a real licensed veterinarian.
6. Keep every response to 2-3 sentences maximum — plain, friendly language, no medical jargon.
7. Never invent facts. If you are uncertain, say so and recommend a vet visit.\
"""


def build_vet_system_prompt(pet: Pet) -> str:
    """Build the full system prompt that gives Claude the Dr. PawPal persona.

    Embeds the pet's current profile and registered care tasks so Claude
    can give contextually accurate advice without the user having to repeat them.
    """
    if pet.care_tasks:
        task_lines = "\n".join(
            f"  - {t.name} ({t.category}, {t.duration_minutes} min, "
            f"priority {t.priority}, {'required' if t.is_required else 'optional'})"
            for t in pet.care_tasks
        )
    else:
        task_lines = "  (no tasks registered yet)"

    return (
        "You are Dr. PawPal, a board-certified veterinary advisor embedded in the "
        "PawPal+ pet care scheduling app.\n\n"
        f"{_VET_RULES}\n\n"
        "CURRENT PET PROFILE:\n"
        f"  Name: {pet.name}\n"
        f"  Species: {pet.species}\n"
        f"  Breed: {pet.breed}\n"
        f"  Age: {pet.age_years} years\n"
        f"  Weight: {pet.weight_kg} kg\n"
        f"  Medical notes: {pet.medical_notes or 'none'}\n\n"
        f"REGISTERED CARE TASKS:\n{task_lines}"
    )


def ask_vet(pet: Pet, user_message: str, history: list[dict]) -> str:
    """Send a message to Dr. PawPal and return the response text.

    Args:
        pet: The pet being discussed — used to build the system prompt.
        user_message: The new question from the owner.
        history: Prior conversation turns as a list of {role, content} dicts.
                 Should NOT include the current user_message (added here).

    Returns:
        The assistant's response text.

    Raises:
        anthropic.APIError: if the API call fails.
    """
    client = anthropic.Anthropic()
    messages = list(history) + [{"role": "user", "content": user_message}]
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=build_vet_system_prompt(pet),
        messages=messages,
    )
    return response.content[0].text
