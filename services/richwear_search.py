"""
services/richwear_search.py

Personalized RichWear retrieval for recommendation and try-on flows.
The service loads RichWear metadata once, scores all samples against the
current user's style/weather profile, and returns a diverse shortlisted set.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set

logger = logging.getLogger(__name__)

DATASET_PATH = Path("sample-outfits/richwear~/RichWear")

# Cache loaded data to avoid re-reading on every call
_cache: Dict = {}

_STOP_TOKENS = {
    "",
    "nan",
    "look",
    "style",
    "fashion",
    "outfit",
    "wear",
    "today",
    "the",
    "and",
    "for",
    "with",
}

_STYLE_HINTS = {
    "minimalist": {"minimal", "clean", "simple", "basic", "monotone", "solid", "neutral"},
    "streetwear": {"street", "urban", "oversized", "hoodie", "sneakers", "cargo", "graphic", "denim"},
    "vintage": {"vintage", "retro", "classic", "preppy", "thrift"},
    "casual": {"casual", "tee", "shirt", "denim", "everyday", "simple"},
    "formal": {"formal", "tailored", "blazer", "dress", "shirt", "office", "business"},
    "party": {"party", "night", "glam", "dress", "heels", "sparkle"},
    "outdoor": {"outdoor", "layered", "jacket", "boots", "functional", "sport"},
    "date": {"date", "romantic", "soft", "dress", "knit", "smart"},
}

_WEATHER_HINTS = {
    "hot": {"summer", "light", "breathable", "tee", "shorts", "dress", "linen"},
    "cold": {"coat", "jacket", "knit", "layer", "boots", "winter"},
    "rain": {"jacket", "coat", "boots", "layer", "wind"},
    "wind": {"jacket", "coat", "layer"},
    "sunny": {"spring", "summer", "bright", "light"},
}


def _safe_row(rows: Sequence, idx: int, default):
    return rows[idx] if idx < len(rows) else default


def _load_dataset():
    """Load and cache all RichWear metadata files."""
    if _cache:
        return _cache

    base = DATASET_PATH
    _cache["photos"] = _load_txt(base / "photos.txt")
    _cache["gender"] = _load_txt(base / "gender.txt")
    _cache["v_labels"] = _load_txt_mv(base / "label_verified.txt")
    _cache["n_labels"] = _load_txt_mv(base / "label_noisy.txt")
    _cache["hashtags"] = _load_txt_mv(base / "hashtags.txt")
    _cache["brands"] = _load_txt_mv(base / "brands.txt")

    logger.info(
        "[RICHWEAR] Loaded dataset: %s photos, %s noisy labels",
        len(_cache["photos"]),
        len(_cache["n_labels"]),
    )
    return _cache


def _load_txt(filename: Path) -> List[str]:
    with open(filename, "r", encoding="utf-8") as f:
        return [line.strip() for line in f.readlines()]


def _load_txt_mv(filename: Path) -> List[List[str]]:
    with open(filename, "r", encoding="utf-8") as f:
        return [line.strip().split(",") for line in f.readlines()]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _tokenize(values: Iterable[str]) -> Set[str]:
    tokens: Set[str] = set()
    for value in values:
        raw = _normalize_text(value)
        if not raw or raw in _STOP_TOKENS:
            continue
        for token in re.split(r"[^a-z0-9+#]+", raw):
            token = token.strip().lower()
            if not token or token in _STOP_TOKENS:
                continue
            if len(token) == 1 and not token.isdigit():
                continue
            tokens.add(token)
    return tokens


def _parse_weather_context(weather_context: str) -> Dict[str, object]:
    lowered = weather_context.lower()
    temps = re.findall(r"(\d+)\s*-\s*(\d+)\s*c", lowered)

    signals: Set[str] = set()
    if temps:
        _, max_temp = temps[0]
        max_c = int(max_temp)
        if max_c >= 28:
            signals.add("hot")
        elif max_c <= 18:
            signals.add("cold")

    if any(term in lowered for term in ["rain", "shower", "thunderstorm", "storm"]):
        signals.add("rain")
    if any(term in lowered for term in ["wind", "breeze", "gust"]):
        signals.add("wind")
    if any(term in lowered for term in ["sunny", "fine", "clear"]):
        signals.add("sunny")

    keyword_tokens: Set[str] = set()
    for signal in signals:
        keyword_tokens.update(_WEATHER_HINTS.get(signal, set()))

    return {
        "signals": signals,
        "keyword_tokens": keyword_tokens,
    }


def _build_preference_tokens(
    styles: Optional[Sequence[str]],
    colors: Optional[Sequence[str]],
    preferred_patterns: Optional[Sequence[str]],
    favorite_brands: Optional[str],
    occasion: str,
    weather_context: str,
) -> Dict[str, Set[str]]:
    style_tokens = _tokenize(styles or [])
    expanded_style_tokens = set(style_tokens)
    for style in styles or []:
        expanded_style_tokens.update(_STYLE_HINTS.get(style.strip().lower(), set()))

    color_tokens = _tokenize(colors or [])
    pattern_tokens = _tokenize(preferred_patterns or [])
    brand_tokens = _tokenize([favorite_brands] if favorite_brands else [])
    occasion_tokens = _tokenize([occasion])

    weather_info = _parse_weather_context(weather_context)
    weather_tokens = weather_info["keyword_tokens"]

    return {
        "styles": expanded_style_tokens,
        "colors": color_tokens,
        "patterns": pattern_tokens,
        "brands": brand_tokens,
        "occasion": occasion_tokens,
        "weather": set(weather_tokens),
        "weather_signals": set(weather_info["signals"]),
    }


def _score_sample(
    metadata_tokens: Set[str],
    labels: List[str],
    colors: Set[str],
    preference_tokens: Dict[str, Set[str]],
    target_gender: Optional[str],
    sample_gender: str,
    feedback_profile: Optional[Dict],
) -> tuple[int, List[str]]:
    score = 0
    reasons: List[str] = []

    if target_gender:
        if sample_gender == target_gender:
            score += 30
            reasons.append("gender-match")
        else:
            return -1, ["gender-mismatch"]

    def apply_hits(label: str, tokens: Set[str], weight: int, reason_prefix: str) -> None:
        nonlocal score
        if not tokens:
            return
        hits = sorted(tokens.intersection(metadata_tokens))
        if hits:
            score += min(len(hits), 3) * weight
            reasons.append(f"{reason_prefix}:{', '.join(hits[:3])}")

    apply_hits("styles", preference_tokens["styles"], 8, "style")
    apply_hits("colors", preference_tokens["colors"], 7, "color")
    apply_hits("patterns", preference_tokens["patterns"], 5, "pattern")
    apply_hits("brands", preference_tokens["brands"], 8, "brand")
    apply_hits("occasion", preference_tokens["occasion"], 5, "occasion")
    apply_hits("weather", preference_tokens["weather"], 5, "weather")

    if feedback_profile:
        liked_colors = _tokenize(feedback_profile.get("preferred_colors", []))
        avoided_colors = _tokenize(feedback_profile.get("avoided_colors", []))
        preferred_categories = _tokenize(feedback_profile.get("preferred_categories", []))

        liked_color_hits = sorted(liked_colors.intersection(colors))
        if liked_color_hits:
            score += min(len(liked_color_hits), 2) * 6
            reasons.append(f"feedback-color:{', '.join(liked_color_hits[:2])}")

        avoided_hits = avoided_colors.intersection(colors)
        if avoided_hits:
            score -= min(len(avoided_hits), 2) * 5
            reasons.append(f"avoid-color:{', '.join(sorted(avoided_hits)[:2])}")

        category_hits = preferred_categories.intersection(metadata_tokens)
        if category_hits:
            score += min(len(category_hits), 2) * 4
            reasons.append(f"feedback-category:{', '.join(sorted(category_hits)[:2])}")

    label_tokens = _tokenize(labels)
    if {"dress", "coat", "jacket", "knit"}.intersection(label_tokens) and "cold" in preference_tokens["weather_signals"]:
        score += 4
        reasons.append("weather-layering-fit")
    if {"shorts", "tee", "shirt", "dress"}.intersection(label_tokens) and "hot" in preference_tokens["weather_signals"]:
        score += 4
        reasons.append("weather-lightweight-fit")

    return score, reasons


def _diversify_candidates(candidates: List[Dict], shortlist_limit: int) -> List[Dict]:
    shortlisted: List[Dict] = []
    seen_signatures: Set[tuple[str, ...]] = set()

    for candidate in candidates:
        signature_tokens = sorted(_tokenize(candidate["verified_labels"] + candidate["noisy_labels"]))
        signature = tuple(signature_tokens[:4]) or (str(candidate["index"]),)

        if signature in seen_signatures and len(shortlisted) < shortlist_limit // 2:
            continue

        shortlisted.append(candidate)
        seen_signatures.add(signature)
        if len(shortlisted) >= shortlist_limit:
            break

    if len(shortlisted) < shortlist_limit:
        seen_ids = {sample["index"] for sample in shortlisted}
        for candidate in candidates:
            if candidate["index"] in seen_ids:
                continue
            shortlisted.append(candidate)
            if len(shortlisted) >= shortlist_limit:
                break

    return shortlisted


def _build_sample_candidate(
    idx: int,
    photos: List[str],
    gender_list: List[str],
    verified: List[str],
    noisy: List[str],
    tags: List[str],
    sample_brands: List[str],
    score: int,
    reasons: List[str],
    metadata_tokens: Set[str],
) -> Dict:
    return {
        "index": idx,
        "image_url": f"/richwear/{photos[idx]}",
        "gender": _safe_row(gender_list, idx, ""),
        "verified_labels": verified,
        "noisy_labels": noisy,
        "hashtags": tags,
        "brands": sample_brands,
        "match_score": score,
        "match_reasons": reasons,
        "metadata_tokens": sorted(metadata_tokens),
    }


def _relaxed_fallback_candidates(
    photos: List[str],
    gender_list: List[str],
    v_labels: List[List[str]],
    n_labels: List[List[str]],
    hashtags: List[List[str]],
    brands: List[List[str]],
    shortlist_limit: int,
    target_gender: Optional[str],
) -> List[Dict]:
    fallback: List[Dict] = []
    for idx in range(len(photos)):
        sample_gender = _safe_row(gender_list, idx, "")
        if target_gender and sample_gender != target_gender:
            continue
        verified = [value.strip() for value in _safe_row(v_labels, idx, []) if str(value).strip()]
        noisy = [value.strip() for value in _safe_row(n_labels, idx, []) if str(value).strip()]
        tags = [value.strip() for value in _safe_row(hashtags, idx, []) if value and value.strip() != "nan"]
        sample_brands = [value.strip() for value in _safe_row(brands, idx, []) if value and value.strip() != "nan"]
        metadata_tokens = _tokenize(verified + noisy + tags + sample_brands)
        fallback.append(
            _build_sample_candidate(
                idx=idx,
                photos=photos,
                gender_list=gender_list,
                verified=verified,
                noisy=noisy,
                tags=tags,
                sample_brands=sample_brands,
                score=1,
                reasons=["fallback-generic-sample"],
                metadata_tokens=metadata_tokens,
            )
        )
        if len(fallback) >= shortlist_limit * 2:
            break
    diversified = _diversify_candidates(fallback, shortlist_limit)
    if diversified:
        logger.warning("[RICHWEAR SEARCH] Using relaxed fallback shortlist=%s", len(diversified))
    return diversified


def search_richwear_samples(
    gender: Optional[str] = None,
    colors: Optional[List[str]] = None,
    styles: Optional[List[str]] = None,
    weather_context: str = "",
    occasion: str = "",
    preferred_patterns: Optional[List[str]] = None,
    favorite_brands: Optional[str] = None,
    feedback_profile: Optional[Dict] = None,
    limit: int = 64,
    shortlist_limit: int = 18,
) -> List[Dict]:
    """
    Search RichWear using a scored retrieval + shortlisting pipeline.

    Step 1: score the full dataset against the user's style profile.
    Step 2: keep a larger relevant candidate pool.
    Step 3: diversify into a smaller, prompt-friendly shortlist.
    """
    logger.info(
        "[RICHWEAR SEARCH] gender=%s colors=%s styles=%s occasion=%s shortlist=%s",
        gender,
        colors,
        styles,
        occasion,
        shortlist_limit,
    )

    try:
        data = _load_dataset()
        photos = data["photos"]
        gender_list = data["gender"]
        v_labels = data["v_labels"]
        n_labels = data["n_labels"]
        hashtags = data["hashtags"]
        brands = data["brands"]

        target_gender = None
        if gender:
            target_gender = "WOMEN" if gender.lower() in ["female", "woman", "women"] else "MEN"

        preference_tokens = _build_preference_tokens(
            styles=styles,
            colors=colors,
            preferred_patterns=preferred_patterns,
            favorite_brands=favorite_brands,
            occasion=occasion,
            weather_context=weather_context,
        )

        scored_candidates: List[Dict] = []
        for idx in range(len(photos)):
            try:
                verified = [value.strip() for value in _safe_row(v_labels, idx, []) if str(value).strip()]
                noisy = [value.strip() for value in _safe_row(n_labels, idx, []) if str(value).strip()]
                tags = [value.strip() for value in _safe_row(hashtags, idx, []) if value and value.strip() != "nan"]
                sample_brands = [value.strip() for value in _safe_row(brands, idx, []) if value and value.strip() != "nan"]

                metadata_tokens = _tokenize(verified + noisy + tags + sample_brands)
                color_tokens = _tokenize(noisy)
                score, reasons = _score_sample(
                    metadata_tokens=metadata_tokens,
                    labels=verified + noisy,
                    colors=color_tokens,
                    preference_tokens=preference_tokens,
                    target_gender=target_gender,
                    sample_gender=_safe_row(gender_list, idx, ""),
                    feedback_profile=feedback_profile,
                )
                if score < 0:
                    continue

                scored_candidates.append(
                    _build_sample_candidate(
                        idx=idx,
                        photos=photos,
                        gender_list=gender_list,
                        verified=verified,
                        noisy=noisy,
                        tags=tags,
                        sample_brands=sample_brands,
                        score=score,
                        reasons=reasons,
                        metadata_tokens=metadata_tokens,
                    )
                )
            except Exception as row_exc:
                logger.warning("[RICHWEAR SEARCH] Skipping broken row idx=%s: %s", idx, row_exc)
                continue

        scored_candidates.sort(key=lambda item: item["match_score"], reverse=True)
        candidate_pool = scored_candidates[: max(limit, shortlist_limit)]
        shortlisted = _diversify_candidates(candidate_pool, shortlist_limit)
        if not shortlisted:
            shortlisted = _relaxed_fallback_candidates(
                photos=photos,
                gender_list=gender_list,
                v_labels=v_labels,
                n_labels=n_labels,
                hashtags=hashtags,
                brands=brands,
                shortlist_limit=shortlist_limit,
                target_gender=target_gender,
            )

        logger.info(
            "[RICHWEAR SEARCH] candidate_pool=%s shortlisted=%s best_score=%s",
            len(candidate_pool),
            len(shortlisted),
            shortlisted[0]["match_score"] if shortlisted else None,
        )
        return shortlisted

    except Exception as exc:
        logger.exception("RichWear search failed: %s", exc)
        return []
