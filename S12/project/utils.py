from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

ALLOWED_VERDICTS = {"supported", "partially_supported", "not_evaluable"}

CASE_RULES = {
    "M01": {
        "ingredient": "creatine_monohydrate",
        "claim_type": "rendimiento",
        "outcome_target": "strength",
        "patterns": [
            ["strength"],
            ["stronger"],
            ["boost", "strength"],
            ["boosts", "strength"],
            ["increase", "strength"],
            ["increases", "strength"],
            ["improve", "strength"],
            ["improves", "strength"],
        ],
    },
    "M04": {
        "ingredient": "caffeine",
        "claim_type": "energia_fatiga",
        "outcome_target": "perceived_energy_fatigue_reduction",
        "patterns": [
            ["fatigue"],
            ["less", "fatigue"],
            ["reduce", "fatigue"],
            ["reduces", "fatigue"],
            ["energy"],
            ["boost", "energy"],
            ["boosts", "energy"],
            ["alertness"],
        ],
    },
    "M07": {
        "ingredient": "whey_protein",
        "claim_type": "recuperacion",
        "outcome_target": "post_exercise_recovery",
        "patterns": [
            ["recovery"],
            ["recover"],
            ["recover", "after", "training"],
            ["recover", "faster"],
            ["post", "workout", "recovery"],
        ],
    },
    "M08": {
        "ingredient": "whey_protein",
        "claim_type": "composicion_corporal",
        "outcome_target": "lean_mass_gain",
        "patterns": [
            ["muscle", "growth"],
            ["lean", "mass"],
            ["lean", "muscle"],
            ["build", "muscle"],
            ["builds", "muscle"],
            ["muscle", "gain"],
            ["hypertrophy"],
        ],
    },
}

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "provisional_verdict": {
            "type": "string",
            "enum": ["supported", "partially_supported", "not_evaluable"],
        },
        "short_explanation": {"type": "string"},
    },
    "required": ["provisional_verdict", "short_explanation"],
}


def load_data(data_dir: str = "data") -> Dict[str, pd.DataFrame]:
    base = Path(data_dir)
    return {
        "documents": pd.read_csv(base / "practice_documents.csv"),
        "evidence": pd.read_csv(base / "practice_evidence_fragments.csv"),
        "lexicon": pd.read_csv(base / "practice_lexicon.csv"),
        "scope": pd.read_csv(base / "practice_matrix_scope.csv"),
    }


def normalize_text(text: str) -> str:
    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9\s/-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", normalize_text(text))


def _contains_phrase(text: str, phrase: str) -> bool:
    pattern = rf"\b{re.escape(normalize_text(phrase))}\b"
    return re.search(pattern, text) is not None


def detect_ingredient(normalized_claim: str, lexicon_df: pd.DataFrame) -> Tuple[Optional[str], str]:
    ingredient_rows = lexicon_df[lexicon_df["term_type"] == "ingredient"].copy()
    ingredient_rows["surface_form"] = ingredient_rows["surface_form"].astype(str).map(normalize_text)
    ingredient_rows = ingredient_rows.sort_values("surface_form", key=lambda s: s.map(len), ascending=False)

    matches = []
    for _, row in ingredient_rows.iterrows():
        if _contains_phrase(normalized_claim, row["surface_form"]):
            matches.append(row["canonical_form"])

    unique_matches = sorted(set(matches))
    if len(unique_matches) == 1:
        return unique_matches[0], "ok"
    if len(unique_matches) > 1:
        return None, "multiple_ingredients_detected"
    return None, "ingredient_not_detected"


def detect_matrix_case(normalized_claim: str) -> Tuple[Optional[str], str]:
    token_set = set(tokenize(normalized_claim))
    matches = []

    for matrix_id, rule in CASE_RULES.items():
        for pattern in rule["patterns"]:
            if all(token in token_set for token in pattern):
                matches.append(matrix_id)
                break

    unique_matches = sorted(set(matches))
    if len(unique_matches) == 1:
        return unique_matches[0], "ok"
    if len(unique_matches) > 1:
        return None, "multiple_claim_cases_detected"
    return None, "claim_case_not_detected"


def check_scope(ingredient: str, matrix_id: str, scope_df: pd.DataFrame) -> Tuple[bool, str]:
    rows = scope_df[
        (scope_df["ingredient"] == ingredient)
        & (scope_df["matrix_id"] == matrix_id)
        & (scope_df["scope_status"] == "evaluable")
    ]
    if rows.empty:
        return False, "ingredient_claim_case_out_of_scope"
    return True, "ok"


def score_fragment(normalized_claim: str, row: pd.Series) -> float:
    claim_tokens = set(tokenize(normalized_claim))
    keyword_tokens = set(tokenize(str(row.get("retrieval_keywords", "")).replace("|", " ")))
    text_tokens = set(tokenize(str(row.get("fragment_text", ""))))

    overlap_keywords = len(claim_tokens & keyword_tokens)
    overlap_text = len(claim_tokens & text_tokens)

    strength_bonus = {
        "strong": 2.0,
        "moderate": 1.0,
        "weak": 0.5,
    }.get(str(row.get("support_strength", "")).strip().lower(), 0.0)

    support_flag = str(row.get("supports_claim", "")).strip().lower()
    support_bonus = {
        "yes": 1.0,
        "partial": 0.5,
    }.get(support_flag, 0.0)

    return (overlap_keywords * 3) + overlap_text + strength_bonus + support_bonus


def retrieve_evidence(
    normalized_claim: str,
    ingredient: str,
    matrix_id: str,
    evidence_df: pd.DataFrame,
    top_k: int = 2,
) -> List[dict]:
    subset = evidence_df[
        (evidence_df["ingredient"] == ingredient)
        & (evidence_df["matrix_id"] == matrix_id)
    ].copy()

    if subset.empty:
        return []

    subset["retrieval_score"] = subset.apply(lambda row: score_fragment(normalized_claim, row), axis=1)
    subset = subset.sort_values(["retrieval_score", "fragment_id"], ascending=[False, True])

    records = []
    for _, row in subset.head(top_k).iterrows():
        records.append(
            {
                "fragment_id": row["fragment_id"],
                "doc_id": row["doc_id"],
                "matrix_id": row["matrix_id"],
                "ingredient": row["ingredient"],
                "claim_type": row["claim_type"],
                "outcome_target": row["outcome_target"],
                "fragment_text": row["fragment_text"],
                "supports_claim": row["supports_claim"],
                "support_strength": row["support_strength"],
                "conditions_or_limits": row["conditions_or_limits"],
            }
        )
    return records


def build_prompt(
    original_claim: str,
    normalized_claim: str,
    ingredient: str,
    matrix_id: str,
    evidence_items: List[dict],
    template_path: str = "prompt_template.txt",
) -> str:
    evidence_lines = []
    for idx, item in enumerate(evidence_items, start=1):
        evidence_lines.append(
            f"{idx}. [{item['fragment_id']}] {item['fragment_text']} "
            f"(supports_claim={item['supports_claim']}, support_strength={item['support_strength']})"
        )

    template = Path(template_path).read_text(encoding="utf-8")
    return template.format(
        original_claim=original_claim,
        normalized_claim=normalized_claim,
        ingredient=ingredient,
        matrix_id=matrix_id,
        evidence_block="\n".join(evidence_lines),
        schema_json=json.dumps(JSON_SCHEMA, ensure_ascii=False),
    )


def call_ollama(
    prompt: str,
    model: str = "qwen2.5:3b",
    base_url: str = "http://localhost:11434/api/chat",
    timeout: int = 60,
) -> dict:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You classify short supplement claims for an academic prototype. "
                    "Answer with JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": JSON_SCHEMA,
        "options": {"temperature": 0},
    }

    response = requests.post(base_url, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()

    raw_content = data.get("message", {}).get("content", "").strip()
    if not raw_content:
        raise RuntimeError("Empty response from Ollama.")

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ollama did not return valid JSON: {raw_content}") from exc

    verdict = parsed.get("provisional_verdict")
    explanation = str(parsed.get("short_explanation", "")).strip()

    if verdict not in ALLOWED_VERDICTS:
        raise RuntimeError(f"Invalid verdict returned by Ollama: {verdict}")
    if not explanation:
        raise RuntimeError("Ollama returned an empty short_explanation.")

    return {
        "provisional_verdict": verdict,
        "short_explanation": explanation,
    }


def fallback_verdict(evidence_items: List[dict]) -> dict:
    if not evidence_items:
        return {
            "provisional_verdict": "not_evaluable",
            "short_explanation": "No relevant evidence fragments were retrieved from the reduced corpus.",
        }

    strongest = evidence_items[0]
    support_flag = str(strongest["supports_claim"]).lower()
    support_strength = str(strongest["support_strength"]).lower()

    if support_flag == "yes" and support_strength in {"strong", "moderate"}:
        verdict = "supported"
        explanation = "The top retrieved evidence directly supports the claim within the reduced practice scope."
    else:
        verdict = "partially_supported"
        explanation = "The retrieved evidence is relevant but limited, indirect, or mixed, so full support is not justified."

    return {
        "provisional_verdict": verdict,
        "short_explanation": explanation,
    }


def analyze_claim(
    claim: str,
    data: Dict[str, pd.DataFrame],
    use_llm: bool = True,
    model: str = "qwen2.5:3b",
) -> dict:
    original_claim = claim.strip()
    normalized_claim = normalize_text(original_claim)

    result = {
        "original_claim": original_claim,
        "normalized_claim": normalized_claim,
        "detected_ingredient": None,
        "matched_scope_case": None,
        "provisional_verdict": None,
        "short_explanation": None,
        "retrieved_evidence": [],
    }

    if not original_claim:
        result["provisional_verdict"] = "not_evaluable"
        result["short_explanation"] = "Empty claim. Please enter a short text claim."
        return result

    ingredient, ingredient_status = detect_ingredient(normalized_claim, data["lexicon"])
    if ingredient is None:
        result["provisional_verdict"] = "not_evaluable"
        result["short_explanation"] = (
            "The ingredient could not be resolved unambiguously inside the limited practice scope."
            if ingredient_status == "multiple_ingredients_detected"
            else "No supported ingredient was detected in the claim."
        )
        return result

    result["detected_ingredient"] = ingredient

    matrix_id, case_status = detect_matrix_case(normalized_claim)
    if matrix_id is None:
        result["provisional_verdict"] = "not_evaluable"
        result["short_explanation"] = (
            "The claim appears to match multiple supported claim cases, so the prototype cannot evaluate it safely."
            if case_status == "multiple_claim_cases_detected"
            else "The claim target is outside the small set of supported claim cases."
        )
        return result

    in_scope, _ = check_scope(ingredient, matrix_id, data["scope"])
    if not in_scope:
        result["matched_scope_case"] = matrix_id
        result["provisional_verdict"] = "not_evaluable"
        result["short_explanation"] = "This ingredient + claim-case combination is outside the practice scope."
        return result

    result["matched_scope_case"] = matrix_id
    evidence_items = retrieve_evidence(normalized_claim, ingredient, matrix_id, data["evidence"], top_k=2)
    result["retrieved_evidence"] = evidence_items

    if not evidence_items:
        result["provisional_verdict"] = "not_evaluable"
        result["short_explanation"] = "No relevant evidence fragments were found in the reduced corpus."
        return result

    if use_llm:
        prompt = build_prompt(
            original_claim=original_claim,
            normalized_claim=normalized_claim,
            ingredient=ingredient,
            matrix_id=matrix_id,
            evidence_items=evidence_items,
        )
        model_output = call_ollama(prompt=prompt, model=model)
    else:
        model_output = fallback_verdict(evidence_items)

    result.update(model_output)
    return result