"""
services/wardrobe_agent.py

LangGraph-powered wardrobe recommendation agent.
Fetches the authenticated user's garments from SQLite, checks the weather,
then asks Gemini to generate 3 distinct outfit combinations for the occasion.
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
    occasion: str
    garments: List[Dict]             # loaded from DB
    weather_advice: str
    outfit_combinations: List[Dict]  # array of 3 outfit combos


# ---------------------------------------------------------------------------
# JSON parsing helper — handles arrays AND objects, strips markdown fences
# ---------------------------------------------------------------------------

def _parse_json_safe(text: str) -> Any:
    """
    Parse JSON from an LLM response, robustly stripping markdown code fences
    (e.g. ```json...``` or ```...```) before calling json.loads().
    Handles both top-level arrays ([...]) and objects ({...}).
    """
    text = text.strip()
    # Strip opening fence: ```json or ```
    text = re.sub(r"^```(?:json)?\s*", "", text)
    # Strip closing fence
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # Try to extract the outermost JSON structure (array preferred, then object)
    for open_c, close_c in [("[", "]"), ("{", "}")]:
        start = text.find(open_c)
        end = text.rfind(close_c)
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    # Last resort: parse the whole stripped string
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
    """Ask Gemini to generate 3 distinct outfit combinations from the wardrobe."""
    garments = state["garments"]

    if not garments:
        return {"outfit_combinations": []}

    garment_lines = "\n".join(
        f"  [id={g['id']}] {g['category']} | {g['color']} | {g['material']}"
        + (f" | label: {g['label']}" if g["label"] else "")
        for g in garments
    )

    prompt = f"""You are a personal stylist AI. The user's wardrobe contains these items:

{garment_lines}

Occasion: {state['occasion']}
Weather: {state['weather_advice']}

Task: Generate EXACTLY 3 DISTINCT outfit combinations. Each must use different garments where possible.
For each combination:
1. Pick 2-4 garment IDs that form a complete, well-coordinated outfit for the occasion and weather.
2. Identify ONE "primary_tryon_id" that MUST be a Top or Dress — this is used for virtual try-on via Nano Banana.

Reply with ONLY a raw JSON array (no markdown, no code fences):
[
  {{"combination_id": 1, "recommended_ids": [<int>, ...], "primary_tryon_id": <int>, "reasoning": "<why this works>"}},
  {{"combination_id": 2, "recommended_ids": [<int>, ...], "primary_tryon_id": <int>, "reasoning": "<why this works>"}},
  {{"combination_id": 3, "recommended_ids": [<int>, ...], "primary_tryon_id": <int>, "reasoning": "<why this works>"}}
]"""

    api_client = HKBUAPIClient()
    raw = api_client.call_chatgpt([{"role": "user", "content": prompt}], model="qwen-plus", temperature=0.7)

    try:
        combinations = _parse_json_safe(raw)
        if not isinstance(combinations, list):
            combinations = [combinations]
    except Exception:
        logger.exception("Failed to parse outfit combinations from: %s", raw[:300])
        combinations = []

    garment_map = {g["id"]: g for g in garments}
    outfit_combinations: List[Dict] = []

    for combo in combinations[:3]:
        try:
            recommended_ids = [int(i) for i in combo.get("recommended_ids", [])]
            primary_tryon_id = combo.get("primary_tryon_id")
            if primary_tryon_id is not None:
                primary_tryon_id = int(primary_tryon_id)
            # Fall back to first recommended ID if primary is invalid
            if primary_tryon_id not in garment_map and recommended_ids:
                primary_tryon_id = recommended_ids[0]

            outfit_combinations.append({
                "combination_id": combo.get("combination_id", len(outfit_combinations) + 1),
                "reasoning": combo.get("reasoning", ""),
                "primary_tryon_id": primary_tryon_id,
                "garments": [
                    garment_map[gid] for gid in recommended_ids if gid in garment_map
                ],
            })
        except Exception:
            logger.exception("Skipping malformed combination: %s", combo)

    logger.info(
        "Generated %d outfit combinations for user %s",
        len(outfit_combinations), state["user_id"],
    )
    return {"outfit_combinations": outfit_combinations}


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

    Returns:
      {
        "outfit_combinations": [
          {
            "combination_id": int,
            "reasoning": str,
            "primary_tryon_id": int | None,   # Top/Dress for Nano Banana try-on
            "garments": [                      # full garment objects for frontend
              {id, category, color, material, image_url, thumbnail_url, nobg_url}
            ]
          },
          ...  # up to 3 combos
        ],
        "weather_advice": str,
        "occasion": str,
      }
    """
    initial_state: WardrobeState = {
        "user_id": user_id,
        "occasion": occasion,
        "garments": [],
        "weather_advice": "",
        "outfit_combinations": [],
    }

    final_state = _workflow.invoke(initial_state)

    return {
        "outfit_combinations": final_state["outfit_combinations"],
        "weather_advice": final_state["weather_advice"],
        "occasion": occasion,
    }
