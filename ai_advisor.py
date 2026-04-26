# Feature 1: RAG — Retrieval-Augmented Generation
# Requires: ANTHROPIC_API_KEY environment variable
#
# Retrieves breed-specific care facts from docs/pet_care_kb.json before
# calling Claude, so suggestions are grounded in validated veterinary knowledge
# rather than relying solely on the model's parametric memory.

from __future__ import annotations

import json
from pathlib import Path

import anthropic

_KB_PATH = Path(__file__).parent / "docs" / "pet_care_kb.json"


def retrieve_care_facts(species: str, breed: str) -> list[str]:
    """Return general + breed-specific care facts from the local knowledge base.

    Returns an empty list (never raises) when the KB file is missing or the
    species/breed combination has no entry.
    """
    try:
        kb: dict = json.loads(_KB_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    species_data: dict = kb.get(species.lower(), {})
    general: list[str] = species_data.get("general", [])
    breed_specific: list[str] = species_data.get(breed.lower(), [])
    return general + breed_specific


def suggest_tasks_for_pet(
    species: str,
    breed: str,
    age_years: float,
    weight_kg: float,
) -> str:
    """Call Claude with retrieved care facts and return a raw JSON string.

    The returned string is a JSON array of task objects with keys:
    name, category, duration_minutes, priority, is_required, frequency, notes.

    Raises:
        anthropic.APIError: if the API call fails.
        Any exception from retrieve_care_facts is suppressed (facts become empty).
    """
    facts = retrieve_care_facts(species, breed)
    if facts:
        context = "\n".join(f"- {f}" for f in facts)
    else:
        context = "No breed-specific facts found — apply general best practices."

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=(
            "You are a veterinary care assistant embedded in the PawPal+ scheduling app. "
            "Based on the pet profile and validated care facts provided, suggest daily care tasks. "
            "Return ONLY a valid JSON array — no markdown fences, no explanation. "
            "Each object must have exactly these keys: "
            "name (string), "
            "category (one of: exercise / nutrition / medical / grooming / enrichment), "
            "duration_minutes (integer), "
            "priority (integer 1–5, where 5 is critical), "
            "is_required (boolean), "
            "frequency (one of: daily / twice_daily / weekly), "
            "notes (HH:MM 24-hour start time string, e.g. '07:00')."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Pet profile:\n"
                    f"- Species: {species}\n"
                    f"- Breed: {breed}\n"
                    f"- Age: {age_years} years\n"
                    f"- Weight: {weight_kg} kg\n\n"
                    f"Validated care facts from knowledge base:\n{context}\n\n"
                    f"Suggest 4–6 appropriate daily care tasks for this pet. "
                    f"Return only the JSON array."
                ),
            }
        ],
    )
    return message.content[0].text
