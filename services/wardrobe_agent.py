"""
services/wardrobe_agent.py

LangGraph-powered wardrobe recommendation agent.
Fetches the authenticated user's garments from SQLite, checks the weather,
then asks Gemini to pick the best outfit combination for the occasion.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from apis.api_clients import HKBUAPIClient, WeatherAPI
from database import Garment, SessionLocal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class WardrobeState(TypedDict):
    user_id: int
    occasion: str                    # e.g. "casual", "formal", "outdoor"
    garments: List[Dict]             # loaded from DB
    weather_advice: str
    recommended_ids: List[int]       # garment IDs chosen by AI
    primary_tryon_id: Optional[int]  # the Top/Dress chosen for Nano Banana try-on
    reasoning: str                   # AI's explanation
    recommended_garments: List[Dict] # full garment dicts for frontend display


# ---------------------------------------------------------------------------
# JSON parsing helper
# ---------------------------------------------------------------------------

def _parse_json_safe(text: str) -> Dict[str, Any]:
    """
    Parse JSON from an LLM response, robustly stripping markdown code fences
    (e.g. ```json ... ``` or ``` ... ```) before calling json.loads().
    """
    text = text.strip()
    # Remove opening fence: ```json or ```
    text = re.sub(r"^```(?:json)?\s*", "", text)
    # Remove closing fence: ```
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    # Extract the outermost { ... } block as a safety net
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def load_wardrobe(state: WardrobeState) -> Dict:
    """Fetch the user's garments from SQLite and format them for the AI."""
    db = SessionLocal()
    try:
        rows = (
            db.query(Garment)
            .filter(Garment.user_id == state["user_id"])
            .order_by(Garment.created_at.desc())
            .all()
        )
        garments = [
            {
                "id": g.id,
                "label": g.label or "",
                "category": g.category or "Unknown",
                "color": g.color or "Unknown",
                "material": g.material or "Unknown",
                "image_url": f"/uploads/{Path(g.image_path).name}",
                "thumbnail_url": (
                    f"/thumbnails/{Path(g.thumbnail_path).name}"
                    if g.thumbnail_path else None
                ),
                "nobg_url": (
                    f"/uploads/{Path(g.nobg_path).name}"
                    if g.nobg_path else None
                ),
            }
            for g in rows
        ]
    finally:
        db.close()

    logger.info("Loaded %d garments for user %s", len(garments), state["user_id"])
    return {"garments": garments}


def get_weather(state: WardrobeState) -> Dict:
    """Fetch HKO 2-day weather forecast."""
    try:
        advice = WeatherAPI.get_hko_weather_forecast()
    except Exception:
        logger.exception("Weather fetch failed — using placeholder")
        advice = "Weather data unavailable."
    return {"weather_advice": advice}


def recommend_outfit(state: WardrobeState) -> Dict:
    """Ask Gemini to pick the best outfit combination from the user's wardrobe."""
    garments = state["garments"]

    if not garments:
        return {
            "recommended_ids": [],
            "primary_tryon_id": None,
            "reasoning": "Your wardrobe is empty. Please upload some garments first.",
            "recommended_garments": [],
        }

    # Format garment list for the prompt
    garment_lines = "\n".join(
        f"  [id={g['id']}] {g['category']} | {g['color']} | {g['material']}"
        + (f" | label: {g['label']}" if g["label"] else "")
        for g in garments
    )

    prompt = f"""You are a personal stylist AI. The user's wardrobe contains these items:

{garment_lines}

Occasion: {state['occasion']}
Weather: {state['weather_advice']}

Task:
1. Pick 2–4 garment IDs that form a complete, well-coordinated outfit suitable for the occasion and weather.
2. From the selected items, identify ONE "primary_tryon_id" — this MUST be a Top or Dress (the most visually impactful piece for virtual try-on via Nano Banana API).

Reply with ONLY raw JSON (no markdown, no code fences):
{{
  "recommended_ids": [<list of integer garment IDs>],
  "primary_tryon_id": <single integer garment ID that is a Top or Dress>,
  "reasoning": "<brief explanation of why this outfit works for the occasion and weather>"
}}"""

    api_client = HKBUAPIClient()
    raw = api_client.call_chatgpt([{"role": "user", "content": prompt}])

    try:
        tags = _parse_json_safe(raw)
    except Exception:
        logger.exception("Failed to parse recommendation JSON from: %s", raw[:300])
        tags = {}

    recommended_ids = [int(i) for i in tags.get("recommended_ids", [])]
    primary_tryon_id = tags.get("primary_tryon_id")
    if primary_tryon_id is not None:
        primary_tryon_id = int(primary_tryon_id)
    reasoning = tags.get("reasoning", "No reasoning provided.")

    # Map IDs back to full garment dicts
    garment_map = {g["id"]: g for g in garments}
    recommended_garments = [garment_map[gid] for gid in recommended_ids if gid in garment_map]

    # Ensure primary_tryon_id is actually in the recommended set
    if primary_tryon_id not in garment_map:
        primary_tryon_id = recommended_ids[0] if recommended_ids else None

    logger.info(
        "Recommendation for user %s: ids=%s primary=%s",
        state["user_id"], recommended_ids, primary_tryon_id,
    )
    return {
        "recommended_ids": recommended_ids,
        "primary_tryon_id": primary_tryon_id,
        "reasoning": reasoning,
        "recommended_garments": recommended_garments,
    }


# ---------------------------------------------------------------------------
# LangGraph workflow (compiled once at module load)
# ---------------------------------------------------------------------------

def _build_graph():
    graph = StateGraph(WardrobeState)
    graph.add_node("load_wardrobe", load_wardrobe)
    graph.add_node("get_weather", get_weather)
    graph.add_node("recommend_outfit", recommend_outfit)

    graph.set_entry_point("load_wardrobe")
    graph.add_edge("load_wardrobe", "get_weather")
    graph.add_edge("get_weather", "recommend_outfit")
    graph.add_edge("recommend_outfit", END)

    return graph.compile()


_workflow = _build_graph()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_wardrobe_recommendation(user_id: int, occasion: str = "casual") -> Dict[str, Any]:
    """
    Run the wardrobe recommendation agent for a given user.

    Returns a dict with:
      - recommended_garments: List[Dict]  full garment objects (id, category, color,
                                          material, image_url, thumbnail_url, nobg_url)
      - primary_tryon_id:     Optional[int]  the Top/Dress ID for Nano Banana try-on
      - reasoning:            str            AI's explanation
      - occasion:             str
      - weather_advice:       str
    """
    initial_state: WardrobeState = {
        "user_id": user_id,
        "occasion": occasion,
        "garments": [],
        "weather_advice": "",
        "recommended_ids": [],
        "primary_tryon_id": None,
        "reasoning": "",
        "recommended_garments": [],
    }

    final_state = _workflow.invoke(initial_state)

    return {
        "recommended_garments": final_state["recommended_garments"],
        "primary_tryon_id": final_state["primary_tryon_id"],
        "reasoning": final_state["reasoning"],
        "occasion": occasion,
        "weather_advice": final_state["weather_advice"],
    }
