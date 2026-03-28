from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict

from langgraph.graph import END, StateGraph

from apis.api_clients import HKBUAPIClient, WeatherAPI
from database import Garment, SessionLocal, UserFeedback, UserProfile

logger = logging.getLogger(__name__)

LLM_MODEL = "qwen-plus"
WARDROBE_SHORTLIST_LIMIT = 24
RICHWEAR_SHORTLIST_LIMIT = 18
RICHWEAR_PROMPT_LIMIT = 12

_TOP_KEYWORDS = {"top", "shirt", "blouse", "t-shirt", "tshirt", "sweater", "hoodie", "tank", "dress", "polo", "vest", "cardigan", "crop", "blazer", "coat"}
_BOTTOM_KEYWORDS = {"bottom", "pant", "trouser", "skirt", "shorts", "jeans", "legging", "chino"}
_DRESS_KEYWORDS = {"dress", "jumpsuit", "romper", "overall"}


class WardrobeState(TypedDict):
    user_id: int
    occasion: str
    include_samples: bool
    user_profile: Dict[str, Any]
    garments: List[Dict[str, Any]]
    candidate_garments: List[Dict[str, Any]]
    weather_advice: str
    preference_profile: Dict[str, Any]
    saved_profile: Dict[str, Any]
    sample_outfits: List[Dict[str, Any]]
    retrieval_profile: Dict[str, Any]
    outfit_combinations: List[Dict[str, Any]]
    retry_count: int
    manager_feedback: str
    manager_decision: str


def _parse_json_safe(text: str) -> Any:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    for open_c, close_c in [("[", "]"), ("{", "}")]:
        start = text.find(open_c)
        end = text.rfind(close_c)
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
    return json.loads(text)


def _extract_temperature_range(weather_text: str) -> Tuple[Optional[int], Optional[int]]:
    match = re.search(r"(\d+)\s*-\s*(\d+)\s*c", weather_text.lower())
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _derive_weather_signals(weather_text: str) -> Set[str]:
    lowered = weather_text.lower()
    _, max_temp = _extract_temperature_range(lowered)
    signals: Set[str] = set()
    if max_temp is not None:
        if max_temp >= 28:
            signals.add("hot")
        elif max_temp <= 18:
            signals.add("cold")
    if any(term in lowered for term in ["rain", "shower", "storm", "thunderstorm"]):
        signals.add("rain")
    if any(term in lowered for term in ["wind", "breeze", "gust"]):
        signals.add("wind")
    if any(term in lowered for term in ["sunny", "fine", "clear"]):
        signals.add("sunny")
    return signals


def _build_retrieval_profile(occasion: str, user_profile: Dict[str, Any], saved_profile: Dict[str, Any], preference_profile: Dict[str, Any], weather_text: str) -> Dict[str, Any]:
    return {
        "occasion": occasion,
        "occasion_type": user_profile.get("occasion_type", "casual"),
        "formality_level": int(user_profile.get("formality_level", 2) or 2),
        "style_keywords": user_profile.get("style_keywords", []),
        "saved_styles": saved_profile.get("preferred_styles", []),
        "saved_colors": saved_profile.get("preferred_colors", []),
        "saved_patterns": saved_profile.get("preferred_patterns", []),
        "favorite_brands": saved_profile.get("favorite_brands", ""),
        "weather_signals": sorted(_derive_weather_signals(weather_text)),
        "feedback_colors": preference_profile.get("preferred_colors", []),
        "feedback_categories": preference_profile.get("preferred_categories", []),
    }


def _score_garment_for_prompt(garment: Dict[str, Any], retrieval_profile: Dict[str, Any], preference_profile: Dict[str, Any]) -> Tuple[int, List[str]]:
    score = 0
    reasons: List[str] = []
    category = (garment.get("category") or "").lower()
    color = (garment.get("color") or "").lower()
    material = (garment.get("material") or "").lower()
    label = (garment.get("label") or "").lower()

    preferred_colors = {value.lower() for value in retrieval_profile.get("saved_colors", [])}
    feedback_colors = {value.lower() for value in preference_profile.get("preferred_colors", [])}
    preferred_categories = {value.lower() for value in preference_profile.get("preferred_categories", [])}
    style_terms = {value.lower() for value in retrieval_profile.get("style_keywords", []) + retrieval_profile.get("saved_styles", [])}
    weather_signals = set(retrieval_profile.get("weather_signals", []))

    if color in preferred_colors:
        score += 10
        reasons.append("saved-color")
    if color in feedback_colors:
        score += 8
        reasons.append("feedback-color")
    if preferred_categories and any(term in category for term in preferred_categories):
        score += 7
        reasons.append("feedback-category")
    if style_terms and any(term in f"{category} {label}" for term in style_terms):
        score += 6
        reasons.append("style-fit")
    if int(retrieval_profile.get("formality_level", 2) or 2) >= 4 and any(term in category for term in ["blazer", "dress", "shirt", "trouser", "coat"]):
        score += 5
        reasons.append("formal-fit")
    if "cold" in weather_signals and any(term in f"{category} {material}" for term in ["jacket", "coat", "knit", "wool", "hoodie"]):
        score += 5
        reasons.append("cold-weather")
    if "hot" in weather_signals and any(term in f"{category} {material}" for term in ["shirt", "shorts", "dress", "linen", "cotton"]):
        score += 5
        reasons.append("hot-weather")
    if "rain" in weather_signals and any(term in category for term in ["jacket", "coat", "boots"]):
        score += 4
        reasons.append("rain-ready")
    return score, reasons


def _rank_garments_for_prompt(
    garments: List[Dict[str, Any]],
    retrieval_profile: Dict[str, Any],
    preference_profile: Dict[str, Any],
    limit: Optional[int] = WARDROBE_SHORTLIST_LIMIT,
) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for garment in garments:
        score, reasons = _score_garment_for_prompt(garment, retrieval_profile, preference_profile)
        enriched = dict(garment)
        enriched["match_score"] = score
        enriched["match_reasons"] = reasons
        ranked.append(enriched)
    ranked.sort(key=lambda item: item.get("match_score", 0), reverse=True)
    return ranked if limit is None else ranked[:limit]


def _category_matches(garment: Dict[str, Any], keywords: Set[str]) -> bool:
    category = (garment.get("category") or "").lower()
    return any(keyword in category for keyword in keywords)


def _has_bottom(garments: List[Dict[str, Any]]) -> bool:
    return any(_category_matches(garment, _BOTTOM_KEYWORDS) for garment in garments)


def _has_dress(garments: List[Dict[str, Any]]) -> bool:
    return any(_category_matches(garment, _DRESS_KEYWORDS) for garment in garments)


def _has_viable_wardrobe_combo(garments: List[Dict[str, Any]]) -> bool:
    return _has_dress(garments) or (_has_top(garments) and _has_bottom(garments))


def _ensure_viable_shortlist(
    ranked_garments: List[Dict[str, Any]],
    limit: int = WARDROBE_SHORTLIST_LIMIT,
) -> List[Dict[str, Any]]:
    shortlist: List[Dict[str, Any]] = []
    seen_ids: Set[int] = set()

    def add_garment(garment: Optional[Dict[str, Any]]) -> None:
        if not garment:
            return
        garment_id = garment.get("id")
        if garment_id is None or garment_id in seen_ids or len(shortlist) >= limit:
            return
        shortlist.append(garment)
        seen_ids.add(garment_id)

    seed_limit = max(limit - 2, 1)
    for garment in ranked_garments:
        add_garment(garment)
        if len(shortlist) >= seed_limit:
            break

    if _has_viable_wardrobe_combo(shortlist):
        for garment in ranked_garments:
            add_garment(garment)
            if len(shortlist) >= limit:
                break
        return shortlist

    if not _has_dress(shortlist):
        add_garment(next((garment for garment in ranked_garments if _has_dress([garment])), None))
    if not _has_top(shortlist):
        add_garment(next((garment for garment in ranked_garments if _has_top([garment])), None))
    if not _has_bottom(shortlist):
        add_garment(next((garment for garment in ranked_garments if _has_bottom([garment])), None))

    for garment in ranked_garments:
        add_garment(garment)
        if len(shortlist) >= limit:
            break

    return shortlist


def _has_top(garments: List[Dict[str, Any]]) -> bool:
    return any(_category_matches(garment, _TOP_KEYWORDS) for garment in garments)


def _has_bottom_or_dress(garments: List[Dict[str, Any]]) -> bool:
    return _has_bottom(garments) or _has_dress(garments)


def _choose_primary_tryon(garments: List[Dict[str, Any]]) -> Optional[int]:
    for garment in garments:
        category = (garment.get("category") or "").lower()
        if any(keyword in category for keyword in _TOP_KEYWORDS.union(_DRESS_KEYWORDS)):
            return garment.get("id")
    return garments[0].get("id") if garments else None


def _fallback_sample_combinations(samples: List[Dict[str, Any]], occasion: str) -> List[Dict[str, Any]]:
    combos: List[Dict[str, Any]] = []
    for idx, sample in enumerate(samples[:3], start=1):
        reason = ", ".join(sample.get("match_reasons", [])[:3]) or "profile fit"
        combos.append({
            "combination_id": idx,
            "reasoning": f"Fallback RichWear pick for {occasion} ({reason}).",
            "primary_tryon_id": None,
            "is_sample": True,
            "sample_image_url": sample["image_url"],
            "sample_labels": sample["noisy_labels"],
            "sample_hashtags": sample["hashtags"],
            "sample_brands": sample["brands"],
            "garments": [],
        })
    return combos


def _fallback_wardrobe_combinations(candidate_garments: List[Dict[str, Any]], all_garments: List[Dict[str, Any]], occasion: str) -> List[Dict[str, Any]]:
    garment_map = {garment["id"]: garment for garment in all_garments}
    dresses = [g for g in candidate_garments if any(keyword in (g.get("category") or "").lower() for keyword in _DRESS_KEYWORDS)]
    tops = [g for g in candidate_garments if any(keyword in (g.get("category") or "").lower() for keyword in _TOP_KEYWORDS)]
    bottoms = [g for g in candidate_garments if any(keyword in (g.get("category") or "").lower() for keyword in _BOTTOM_KEYWORDS)]
    raw_combos: List[List[Dict[str, Any]]] = [[dress] for dress in dresses[:2]]
    for top in tops:
        for bottom in bottoms:
            if top["id"] == bottom["id"]:
                continue
            raw_combos.append([top, bottom])
            if len(raw_combos) >= 6:
                break
        if len(raw_combos) >= 6:
            break
    fallback: List[Dict[str, Any]] = []
    seen_sets: Set[Tuple[int, ...]] = set()
    for idx, combo in enumerate(raw_combos, start=1):
        ids = tuple(sorted(item["id"] for item in combo))
        if ids in seen_sets:
            continue
        seen_sets.add(ids)
        garments = [garment_map[item_id] for item_id in ids if item_id in garment_map]
        if not garments:
            continue
        fallback.append({
            "combination_id": idx,
            "reasoning": f"Fallback wardrobe match for {occasion}, selected from the shortlist.",
            "primary_tryon_id": _choose_primary_tryon(garments),
            "garments": garments,
        })
        if len(fallback) >= 3:
            break
    return fallback


def _fallback_sparse_wardrobe_combinations(candidate_garments: List[Dict[str, Any]], occasion: str) -> List[Dict[str, Any]]:
    fallback: List[Dict[str, Any]] = []
    for idx, garment in enumerate(candidate_garments[:3], start=1):
        fallback.append({
            "combination_id": idx,
            "guardrail": True,
            "reasoning": (
                f"Showing your strongest available piece for {occasion}. "
                "Add one more matching item to unlock fuller outfit recommendations."
            ),
            "primary_tryon_id": garment.get("id"),
            "garments": [garment],
        })
    return fallback


def user_profiler(state: WardrobeState) -> Dict[str, Any]:
    print("\n" + "=" * 50)
    print("[USER PROFILER AGENT] Analyzing occasion...")
    print("=" * 50)
    api = HKBUAPIClient()
    prompt = f"""You are a fashion occasion analyst.
Parse the user's request into JSON.

Occasion: "{state['occasion']}"

Return ONLY raw JSON:
{{"occasion_type":"casual|formal|business|party|date|outdoor|sports|wedding","formality_level":1,"time_of_day":"morning|afternoon|evening|any","weather_sensitive":true,"style_keywords":["keyword1","keyword2"]}}"""
    raw = api.call_chatgpt([{"role": "user", "content": prompt}], model=LLM_MODEL, temperature=0.3)
    try:
        profile = _parse_json_safe(raw)
        if not isinstance(profile, dict):
            raise ValueError("Not a dict")
    except Exception:
        logger.warning("Failed to parse user profile, using defaults")
        profile = {"occasion_type": "casual", "formality_level": 2, "time_of_day": "any", "weather_sensitive": True, "style_keywords": [state["occasion"]]}
    print(f"  [PROFILER] Output: {profile}")
    return {"user_profile": profile}


def _load_wardrobe(user_id: int) -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        rows = db.query(Garment).filter(Garment.user_id == user_id).order_by(Garment.created_at.desc()).all()
        return [{
            "id": garment.id,
            "label": garment.label or "",
            "category": garment.category or "Unknown",
            "color": garment.color or "Unknown",
            "material": garment.material or "Unknown",
            "image_url": f"/uploads/{Path(garment.image_path).name}",
            "thumbnail_url": f"/thumbnails/{Path(garment.thumbnail_path).name}" if garment.thumbnail_path else None,
            "nobg_url": f"/uploads/{Path(garment.nobg_path).name}" if garment.nobg_path else None,
        } for garment in rows]
    finally:
        db.close()


def _get_weather() -> str:
    try:
        return WeatherAPI.get_hko_weather_forecast()
    except Exception:
        logger.exception("Weather fetch failed")
        return "Weather data unavailable."


def _load_preferences(user_id: int) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        rows = db.query(UserFeedback).filter(UserFeedback.user_id == user_id).order_by(UserFeedback.created_at.desc()).limit(50).all()
        if not rows:
            return {"liked_garment_ids": [], "disliked_garment_ids": [], "preferred_colors": [], "preferred_categories": [], "avoided_colors": [], "feedback_count": 0}
        liked_ids: List[int] = []
        disliked_ids: List[int] = []
        for row in rows:
            ids = json.loads(row.garment_ids)
            if row.liked:
                liked_ids.extend(ids)
            else:
                disliked_ids.extend(ids)
        all_ids = set(liked_ids + disliked_ids)
        garment_rows = db.query(Garment).filter(Garment.id.in_(all_ids)).all() if all_ids else []
        garment_map = {garment.id: garment for garment in garment_rows}
        liked_colors = Counter()
        liked_categories = Counter()
        disliked_colors = Counter()
        for garment_id in liked_ids:
            garment = garment_map.get(garment_id)
            if garment and garment.color:
                liked_colors[garment.color.lower()] += 1
            if garment and garment.category:
                liked_categories[garment.category.lower()] += 1
        for garment_id in disliked_ids:
            garment = garment_map.get(garment_id)
            if garment and garment.color:
                disliked_colors[garment.color.lower()] += 1
        return {
            "liked_garment_ids": list(set(liked_ids)),
            "disliked_garment_ids": list(set(disliked_ids)),
            "preferred_colors": [color for color, _ in liked_colors.most_common(5)],
            "preferred_categories": [category for category, _ in liked_categories.most_common(5)],
            "avoided_colors": [color for color, _ in disliked_colors.most_common(3)],
            "feedback_count": len(rows),
        }
    except Exception:
        logger.exception("Failed to load preferences")
        return {"liked_garment_ids": [], "disliked_garment_ids": [], "preferred_colors": [], "preferred_categories": [], "avoided_colors": [], "feedback_count": 0}
    finally:
        db.close()


def _load_user_profile(user_id: int) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if not profile:
            return {}
        result: Dict[str, Any] = {}
        if profile.display_name:
            result["display_name"] = profile.display_name
        if profile.gender:
            result["gender"] = profile.gender
        if profile.height_cm:
            result["height_cm"] = profile.height_cm
        if profile.weight_kg:
            result["weight_kg"] = profile.weight_kg
        if profile.skin_tone:
            result["skin_tone"] = profile.skin_tone
        if profile.preferred_styles:
            result["preferred_styles"] = json.loads(profile.preferred_styles)
        if profile.preferred_colors:
            result["preferred_colors"] = json.loads(profile.preferred_colors)
        if profile.preferred_patterns:
            result["preferred_patterns"] = json.loads(profile.preferred_patterns)
        if profile.budget_range:
            result["budget_range"] = profile.budget_range
        if profile.favorite_brands:
            result["favorite_brands"] = profile.favorite_brands
        return result
    except Exception:
        logger.exception("Failed to load user profile")
        return {}
    finally:
        db.close()


def gather_context(state: WardrobeState) -> Dict[str, Any]:
    print("\n" + "=" * 50)
    print("[GATHER CONTEXT] Loading wardrobe, weather, preferences & profile (parallel)...")
    print("=" * 50)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_wardrobe = executor.submit(_load_wardrobe, state["user_id"])
        future_weather = executor.submit(_get_weather)
        future_preferences = executor.submit(_load_preferences, state["user_id"])
        future_profile = executor.submit(_load_user_profile, state["user_id"])
        garments = future_wardrobe.result()
        weather = future_weather.result()
        preference_profile = future_preferences.result()
        saved_profile = future_profile.result()

    retrieval_profile = _build_retrieval_profile(state["occasion"], state.get("user_profile", {}), saved_profile, preference_profile, weather)
    ranked_garments = _rank_garments_for_prompt(garments, retrieval_profile, preference_profile, limit=None)
    candidate_garments = _ensure_viable_shortlist(ranked_garments, limit=WARDROBE_SHORTLIST_LIMIT)
    print(f"  [CONTEXT] Wardrobe: {len(garments)} garments")
    print(f"  [CONTEXT] Wardrobe shortlist: {len(candidate_garments)} items")
    print(f"  [CONTEXT] Weather: {weather[:60]}...")
    print(f"  [CONTEXT] Preferences: {preference_profile['feedback_count']} feedback entries")
    print(f"  [CONTEXT] Profile: {len(saved_profile)} fields set")

    sample_outfits: List[Dict[str, Any]] = []
    if state.get("include_samples"):
        from services.richwear_search import search_richwear_samples
        sample_outfits = search_richwear_samples(
            gender=saved_profile.get("gender"),
            colors=saved_profile.get("preferred_colors", []),
            styles=(saved_profile.get("preferred_styles", []) or []) + (state.get("user_profile", {}).get("style_keywords", []) or []),
            weather_context=weather,
            occasion=state["occasion"],
            preferred_patterns=saved_profile.get("preferred_patterns", []),
            favorite_brands=saved_profile.get("favorite_brands"),
            feedback_profile=preference_profile,
            limit=64,
            shortlist_limit=RICHWEAR_SHORTLIST_LIMIT,
        )
        print(f"  [CONTEXT] RichWear shortlist: {len(sample_outfits)} matches")

    return {
        "garments": garments,
        "candidate_garments": candidate_garments,
        "weather_advice": weather,
        "preference_profile": preference_profile,
        "saved_profile": saved_profile,
        "sample_outfits": sample_outfits,
        "retrieval_profile": retrieval_profile,
    }


def aesthetic_stylist(state: WardrobeState) -> Dict[str, Any]:
    print("\n" + "=" * 50)
    print("[AESTHETIC STYLIST AGENT] Building outfit combinations...")
    print("=" * 50)
    garments = state["garments"]
    candidate_garments = state.get("candidate_garments", garments) or garments
    samples = state.get("sample_outfits", [])
    profile = state.get("user_profile", {})
    preferences = state.get("preference_profile", {})
    saved_profile = state.get("saved_profile", {})
    retrieval_profile = state.get("retrieval_profile", {})
    feedback = state.get("manager_feedback", "")

    garment_lines = ""
    if candidate_garments:
        garment_lines = "Wardrobe shortlist (use ONLY these ids):\n" + "\n".join(
            f"  [id={garment['id']}] {garment['category']} | {garment['color']} | {garment['material']}"
            + (f" | label={garment['label']}" if garment["label"] else "")
            + (f" | score={garment['match_score']}" if garment.get("match_score") is not None else "")
            + (f" | match={', '.join(garment.get('match_reasons', [])[:2])}" if garment.get("match_reasons") else "")
            for garment in candidate_garments
        )

    sample_map = {sample["index"]: sample for sample in samples}
    prompt_samples = samples[:RICHWEAR_PROMPT_LIMIT]
    sample_context = ""
    if prompt_samples:
        sample_context = "RichWear personalized shortlist:\n" + "\n".join(
            f"  [sample_id={sample['index']}] labels={', '.join(sample['noisy_labels'][:6])} | score={sample.get('match_score', 0)}"
            + (f" | brands={', '.join(sample['brands'][:2])}" if sample["brands"] else "")
            + (f" | why={', '.join(sample.get('match_reasons', [])[:3])}" if sample.get("match_reasons") else "")
            for sample in prompt_samples
        )

    saved_profile_context = {
        "gender": saved_profile.get("gender"),
        "skin_tone": saved_profile.get("skin_tone"),
        "preferred_styles": saved_profile.get("preferred_styles", []),
        "preferred_colors": saved_profile.get("preferred_colors", []),
        "preferred_patterns": saved_profile.get("preferred_patterns", []),
        "favorite_brands": saved_profile.get("favorite_brands"),
    }
    preference_context = {
        "feedback_count": preferences.get("feedback_count", 0),
        "preferred_colors": preferences.get("preferred_colors", []),
        "avoided_colors": preferences.get("avoided_colors", []),
        "preferred_categories": preferences.get("preferred_categories", []),
    }
    repair_instruction = f"\nPrevious validation feedback: {feedback}\nRepair the issues instead of inventing new ids.\n" if feedback else ""

    has_enough_wardrobe = _has_viable_wardrobe_combo(candidate_garments)
    if not has_enough_wardrobe and not samples:
        logger.warning("No RichWear samples available; returning sparse wardrobe guardrail recommendations")
        return {
            "outfit_combinations": _fallback_sparse_wardrobe_combinations(candidate_garments, state["occasion"])
        }

    if has_enough_wardrobe:
        prompt = f"""You are the Aesthetic Stylist agent.
Produce 3 strong outfit combinations from the wardrobe shortlist.

Structured user profile:
{json.dumps(profile, ensure_ascii=False)}

Saved profile:
{json.dumps(saved_profile_context, ensure_ascii=False)}

Feedback profile:
{json.dumps(preference_context, ensure_ascii=False)}

Retrieval profile:
{json.dumps(retrieval_profile, ensure_ascii=False)}

Weather:
{state['weather_advice']}

{garment_lines}

{sample_context if sample_context else "No RichWear references available."}
{repair_instruction}

Rules:
1. Use ONLY wardrobe ids that appear in the shortlist.
2. Generate EXACTLY 3 DISTINCT combinations.
3. Each combination must use 1-4 garment ids.
4. Each combination must include either a top+bottom or a dress/jumpsuit/romper.
5. primary_tryon_id must be one of the recommended_ids and should be a top or dress when possible.
6. Reasoning must mention weather fit or style fit in one short sentence.

Return ONLY raw JSON:
[{{"combination_id":1,"recommended_ids":[1,2],"primary_tryon_id":1,"reasoning":"..."}},{{"combination_id":2,"recommended_ids":[3,4],"primary_tryon_id":3,"reasoning":"..."}},{{"combination_id":3,"recommended_ids":[5,6],"primary_tryon_id":5,"reasoning":"..."}}]"""
    else:
        prompt = f"""You are the Aesthetic Stylist agent for sample-based recommendations.
Select from the personalized RichWear shortlist below.

Structured user profile:
{json.dumps(profile, ensure_ascii=False)}

Saved profile:
{json.dumps(saved_profile_context, ensure_ascii=False)}

Feedback profile:
{json.dumps(preference_context, ensure_ascii=False)}

Retrieval profile:
{json.dumps(retrieval_profile, ensure_ascii=False)}

Weather:
{state['weather_advice']}

{sample_context if sample_context else "No RichWear references available."}
{repair_instruction}

Rules:
1. Select EXACTLY 3 DIFFERENT sample_id values from the shortlist.
2. Prefer higher-score samples that align with weather and profile context.
3. Each reasoning must mention at least two of: style fit, color fit, weather fit, brand/aesthetic fit.

Return ONLY raw JSON:
[{{"combination_id":1,"sample_id":101,"reasoning":"..."}},{{"combination_id":2,"sample_id":202,"reasoning":"..."}},{{"combination_id":3,"sample_id":303,"reasoning":"..."}}]"""

    print(
        f"  [STYLIST] Mode: {'wardrobe' if has_enough_wardrobe else 'sample'}"
        f" | Wardrobe: {len(garments)} | Candidates: {len(candidate_garments)} | Samples: {len(samples)}"
    )
    api = HKBUAPIClient()
    raw = api.call_chatgpt([{"role": "user", "content": prompt}], model=LLM_MODEL, temperature=0.7)
    try:
        combinations = _parse_json_safe(raw)
        if not isinstance(combinations, list):
            combinations = [combinations]
    except Exception:
        logger.exception("Failed to parse outfit combinations: %s", raw[:300])
        combinations = []

    outfit_combinations: List[Dict[str, Any]] = []
    if has_enough_wardrobe:
        garment_map = {garment["id"]: garment for garment in garments}
        for combo in combinations[:3]:
            try:
                recommended_ids = [int(value) for value in combo.get("recommended_ids", [])]
                mapped_garments = [garment_map[garment_id] for garment_id in recommended_ids if garment_id in garment_map]
                if not mapped_garments:
                    continue
                primary_tryon_id = combo.get("primary_tryon_id")
                if primary_tryon_id is not None:
                    primary_tryon_id = int(primary_tryon_id)
                if primary_tryon_id not in {garment["id"] for garment in mapped_garments}:
                    primary_tryon_id = _choose_primary_tryon(mapped_garments)
                outfit_combinations.append({
                    "combination_id": combo.get("combination_id", len(outfit_combinations) + 1),
                    "reasoning": combo.get("reasoning", "") or "Selected from the strongest shortlist candidates for this occasion and weather.",
                    "primary_tryon_id": primary_tryon_id,
                    "garments": mapped_garments,
                })
            except Exception:
                logger.exception("Skipping malformed combination: %s", combo)
        if not outfit_combinations:
            logger.warning("Stylist returned no valid wardrobe combos, using deterministic fallback")
            outfit_combinations = _fallback_wardrobe_combinations(candidate_garments, garments, state["occasion"])
    else:
        for combo in combinations[:3]:
            try:
                sample_id = int(combo.get("sample_id", -1))
                sample = sample_map.get(sample_id)
                if not sample:
                    logger.warning("Stylist returned unknown sample_id=%s", sample_id)
                    continue
                outfit_combinations.append({
                    "combination_id": combo.get("combination_id", len(outfit_combinations) + 1),
                    "reasoning": combo.get("reasoning", "") or "Selected from the highest-scoring RichWear references for this profile.",
                    "primary_tryon_id": None,
                    "is_sample": True,
                    "sample_image_url": sample["image_url"],
                    "sample_labels": sample["noisy_labels"],
                    "sample_hashtags": sample["hashtags"],
                    "sample_brands": sample["brands"],
                    "garments": [],
                })
            except Exception:
                logger.exception("Skipping malformed sample combination: %s", combo)
        if not outfit_combinations:
            logger.warning("Stylist returned no valid sample combos, using deterministic fallback")
            outfit_combinations = _fallback_sample_combinations(samples, state["occasion"])

    print(f"  [STYLIST] Generated {len(outfit_combinations)} outfit combinations")
    return {"outfit_combinations": outfit_combinations}


def manager(state: WardrobeState) -> Dict[str, Any]:
    print("\n" + "=" * 50)
    print("[MANAGER AGENT] Validating outfit quality...")
    print("=" * 50)
    combos = state.get("outfit_combinations", [])
    retry_count = state.get("retry_count", 0)
    viable_wardrobe = _has_viable_wardrobe_combo(state.get("candidate_garments", []) or state.get("garments", []))
    sample_mode = bool(combos and combos[0].get("is_sample"))
    if not combos:
        sample_mode = bool(state.get("include_samples") and not viable_wardrobe)
    fallback_combos = (
        _fallback_sample_combinations(state.get("sample_outfits", []), state["occasion"])
        if sample_mode
        else _fallback_wardrobe_combinations(
            state.get("candidate_garments", []),
            state.get("garments", []),
            state["occasion"],
        )
    )
    if sample_mode and not fallback_combos:
        fallback_combos = _fallback_sparse_wardrobe_combinations(
            state.get("candidate_garments", []) or state.get("garments", []),
            state["occasion"],
        )
    issues: List[str] = []
    if len(combos) < 3:
        issues.append(f"Only {len(combos)} combinations were generated; need 3.")

    if sample_mode:
        seen_samples: Set[str] = set()
        for combo in combos:
            combination_id = combo.get("combination_id", "?")
            sample_image_url = combo.get("sample_image_url")
            if not sample_image_url:
                issues.append(f"Combo {combination_id}: missing sample_image_url.")
                continue
            if sample_image_url in seen_samples:
                issues.append(f"Combo {combination_id}: duplicates another sample recommendation.")
            seen_samples.add(sample_image_url)
            if not combo.get("reasoning"):
                issues.append(f"Combo {combination_id}: missing reasoning.")
    else:
        seen_sets: Set[frozenset[int]] = set()
        for combo in combos:
            garments = combo.get("garments", [])
            combination_id = combo.get("combination_id", "?")
            if not garments:
                issues.append(f"Combo {combination_id}: no garments mapped.")
                continue
            if not combo.get("guardrail") and not _has_viable_wardrobe_combo(garments):
                issues.append(f"Combo {combination_id}: missing a top+bottom or dress.")
            id_set = frozenset(garment["id"] for garment in garments)
            if id_set in seen_sets:
                issues.append(f"Combo {combination_id}: duplicates another combination.")
            seen_sets.add(id_set)
            primary_tryon_id = combo.get("primary_tryon_id")
            if primary_tryon_id is None:
                issues.append(f"Combo {combination_id}: missing primary_tryon_id.")
            elif primary_tryon_id not in {garment['id'] for garment in garments}:
                issues.append(f"Combo {combination_id}: primary_tryon_id is not in the garment list.")

    if issues:
        feedback = "Issues found: " + "; ".join(issues)
        if retry_count >= 2:
            if fallback_combos:
                print(f"  [MANAGER] FINISH - Falling back to deterministic {'sample' if sample_mode else 'wardrobe'} combos")
                return {
                    "outfit_combinations": fallback_combos,
                    "manager_decision": "FINISH",
                    "manager_feedback": feedback,
                    "retry_count": retry_count,
                }
            print(f"  [MANAGER] FINISH - Retry budget exhausted with unresolved issues: {feedback}")
            return {"manager_decision": "FINISH", "manager_feedback": feedback, "retry_count": retry_count}
        print(f"  [MANAGER] CONTINUE - {feedback}")
        return {"manager_decision": "CONTINUE", "manager_feedback": feedback, "retry_count": retry_count + 1}
    print("  [MANAGER] FINISH - All combos validated successfully")
    return {"manager_decision": "FINISH", "manager_feedback": "", "retry_count": retry_count}


def synthesizer(state: WardrobeState) -> Dict[str, Any]:
    print("\n" + "=" * 50)
    print("[SYNTHESIZER AGENT] Polishing final recommendations...")
    print("=" * 50)
    combos = state.get("outfit_combinations", [])
    if not combos:
        return {"outfit_combinations": []}
    if combos[0].get("is_sample"):
        return {"outfit_combinations": combos}
    weather = state.get("weather_advice", "")
    preferences = state.get("preference_profile", {})
    retrieval_profile = state.get("retrieval_profile", {})
    combo_summary = []
    for combo in combos:
        pieces = ", ".join(f"{garment['category']} ({garment['color']})" for garment in combo.get("garments", []))
        combo_summary.append(f"Combo {combo['combination_id']}: {pieces}. Draft reasoning: {combo.get('reasoning', '')}")
    prompt = f"""You are the Synthesizer agent for a fashion recommendation workflow.
Rewrite the reasoning for each outfit so it sounds polished and personalized.

Weather:
{weather}

Preference profile:
{json.dumps(preferences, ensure_ascii=False)}

Retrieval profile:
{json.dumps(retrieval_profile, ensure_ascii=False)}

Outfits:
{chr(10).join(combo_summary)}

Return ONLY raw JSON:
[{{"combination_id":1,"reasoning":"..."}},{{"combination_id":2,"reasoning":"..."}},{{"combination_id":3,"reasoning":"..."}}]"""
    api = HKBUAPIClient()
    raw = api.call_chatgpt([{"role": "user", "content": prompt}], model=LLM_MODEL, temperature=0.5)
    try:
        enriched = _parse_json_safe(raw)
        if not isinstance(enriched, list):
            enriched = [enriched]
        reason_map = {item.get("combination_id"): item.get("reasoning", "") for item in enriched}
    except Exception:
        logger.warning("Synthesizer JSON parse failed, keeping original reasoning")
        reason_map = {}
    for combo in combos:
        combination_id = combo.get("combination_id")
        if combination_id in reason_map and reason_map[combination_id]:
            combo["reasoning"] = reason_map[combination_id]
    return {"outfit_combinations": combos}


def _route_manager(state: WardrobeState) -> str:
    return "aesthetic_stylist" if state.get("manager_decision") == "CONTINUE" else "synthesizer"


def _build_graph():
    graph = StateGraph(WardrobeState)
    graph.add_node("user_profiler", user_profiler)
    graph.add_node("gather_context", gather_context)
    graph.add_node("aesthetic_stylist", aesthetic_stylist)
    graph.add_node("manager", manager)
    graph.add_node("synthesizer", synthesizer)
    graph.set_entry_point("user_profiler")
    graph.add_edge("user_profiler", "gather_context")
    graph.add_edge("gather_context", "aesthetic_stylist")
    graph.add_edge("aesthetic_stylist", "manager")
    graph.add_conditional_edges("manager", _route_manager, {"aesthetic_stylist": "aesthetic_stylist", "synthesizer": "synthesizer"})
    graph.add_edge("synthesizer", END)
    return graph.compile()


_workflow = _build_graph()


def run_wardrobe_recommendation(user_id: int, occasion: str = "casual", include_samples: bool = False) -> Dict[str, Any]:
    print("\n" + "=" * 60)
    print("    MULTI-AGENT WARDROBE RECOMMENDATION SYSTEM")
    print("=" * 60)
    start = time.time()
    initial_state: WardrobeState = {
        "user_id": user_id,
        "occasion": occasion,
        "include_samples": include_samples,
        "user_profile": {},
        "garments": [],
        "candidate_garments": [],
        "weather_advice": "",
        "preference_profile": {},
        "saved_profile": {},
        "sample_outfits": [],
        "retrieval_profile": {},
        "outfit_combinations": [],
        "retry_count": 0,
        "manager_feedback": "",
        "manager_decision": "",
    }
    final_state = _workflow.invoke(initial_state, {"recursion_limit": 20})
    duration = time.time() - start
    print(f"\n  Total execution time: {duration:.2f}s")
    print("=" * 60)
    return {
        "outfit_combinations": final_state["outfit_combinations"],
        "weather_advice": final_state["weather_advice"],
        "occasion": occasion,
        "candidate_garment_count": len(final_state.get("candidate_garments", [])),
        "sample_candidate_count": len(final_state.get("sample_outfits", [])),
    }
