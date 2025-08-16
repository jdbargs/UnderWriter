# src/ai_grader.py
import os
import json
import openai
from dotenv import load_dotenv

# --- Setup ---
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# -----------------------------
# Rubric extraction from uploads
# -----------------------------
_EXTRACT_SYSTEM = """You are an assistant that converts teacher rubrics into a clean JSON schema.
- Do not invent criteria not present.
- If weights aren't explicit, propose reasonable weights that sum to ~1.0.
- Preserve descriptor wording; keep it concise.
Output only JSON with this schema:
{
  "title": "string",
  "scale": "0-4" | "0-100",
  "criteria": [
    {
      "name": "string",
      "weight": number,     // 0..1
      "descriptor_levels": { "4":"...", "3":"...", "2":"...", "1":"...", "0":"..." }
    }
  ]
}
"""

def _normalize_weights(criteria):
    total = sum(float(c.get("weight", 0) or 0) for c in criteria) or 1.0
    for c in criteria:
        c["weight"] = round(float(c.get("weight", 0) or 0) / total, 4)
    return criteria

def extract_rubric_schema(rubric_text: str) -> dict:
    """Extract a structured rubric schema (title/scale/criteria/weights/descriptors) from teacher text."""
    user = (
        "Extract a rubric JSON from the following text. If the scale isn't explicit, prefer '0-4'.\n\n"
        f"RUBRIC TEXT:\n---\n{rubric_text}\n---"
    )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=1200,
        )
        raw = resp["choices"][0]["message"]["content"].strip()
        data = json.loads(raw)
        # normalize
        data["criteria"] = _normalize_weights(data.get("criteria", []))
        data["scale"] = (data.get("scale") or "0-4") if data.get("scale") in ("0-4", "0-100") else "0-4"
        # ensure descriptor bands exist
        for c in data["criteria"]:
            d = c.get("descriptor_levels") or {}
            for k in ["4","3","2","1","0"]:
                d.setdefault(k, "")
            c["descriptor_levels"] = d
        return data
    except Exception as e:
        # Fallback minimal schema if LLM fails
        return {
            "title": "Untitled Rubric",
            "scale": "0-4",
            "criteria": [
                {"name": "Thesis", "weight": 0.25, "descriptor_levels": {"4":"","3":"","2":"","1":"","0":""}},
                {"name": "Evidence", "weight": 0.25, "descriptor_levels": {"4":"","3":"","2":"","1":"","0":""}},
                {"name": "Organization", "weight": 0.25, "descriptor_levels": {"4":"","3":"","2":"","1":"","0":""}},
                {"name": "Style/Mechanics", "weight": 0.25, "descriptor_levels": {"4":"","3":"","2":"","1":"","0":""}},
            ]
        }

# -----------------------------------------
# Filled-rubric score extraction (no manual)
# -----------------------------------------
_EXTRACT_SCORES_SYSTEM = """You are an assistant that reads a teacher's filled/graded rubric and returns structured scores.
Follow the given rubric schema (criteria names and 0-4 or 0-100 scale). Do not invent criteria.
Return concise rationales per criterion using the rubric language where possible.
Output JSON only:
{
  "overall": number,
  "per_criterion": { "CriterionName": number, ... },
  "rationales": { "CriterionName": "short explanation", ... }
}"""

def extract_scored_sample(graded_rubric_text: str, rubric_schema: dict) -> dict:
    """Parse the filled rubric text into per-criterion scores aligned to rubric_schema."""
    user = (
        "RUBRIC SCHEMA:\n" + json.dumps(rubric_schema, ensure_ascii=False) +
        "\n\nFILLED/TEACHER-GRADED RUBRIC TEXT:\n---\n" + graded_rubric_text + "\n---"
    )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": _EXTRACT_SCORES_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_tokens=900,
        )
        data = json.loads(resp["choices"][0]["message"]["content"])
        # Ensure schema criteria are present
        rubric_criteria = [c["name"] for c in rubric_schema.get("criteria", [])]
        pc = data.get("per_criterion", {}) or {}
        for name in rubric_criteria:
            pc.setdefault(name, None)
        data["per_criterion"] = pc
        return data
    except Exception as e:
        return {"overall": None, "per_criterion": {}, "rationales": {"_note": f"Extraction failed: {e}"}}

# -----------------------------
# Self-test grading (few-shot)
# -----------------------------
_GRADE_SYSTEM = """You are an assistant that grades essays strictly according to a given rubric.
- Use only the rubric criteria and scale provided.
- Be consistent with the rubric's language and weighting.
- Return concise rationales per criterion (1–2 sentences each).
- Do not invent criteria or add points outside the scale.
Output JSON only:
{
  "overall": number,
  "per_criterion": { "CriterionName": number, ... },
  "rationales": { "CriterionName": "short rationale", ... },
  "confidence": "low|medium|high"
}"""

def _format_anchors(anchors, max_chars=1400):
    """
    anchors: list of dicts with keys {"text", "overall", "per_criterion"}
    We keep it compact; truncate text and include the numeric labels.
    """
    out = []
    for a in anchors or []:
        txt = (a.get("text") or "").strip().replace("\n", " ")
        if len(txt) > max_chars:
            txt = txt[:max_chars] + "..."
        out.append({
            "text_excerpt": txt,
            "overall": a.get("overall"),
            "per_criterion": a.get("per_criterion") or {}
        })
    return out

def grade_with_rubric(essay_text: str, rubric_schema: dict,
                      anchors: list = None, leniency: float = 0.5) -> dict:
    """
    Few-shot rubric grading.
    - rubric_schema: {"title","scale","criteria":[{"name","weight","descriptor_levels"}]}
    - anchors: optional list of prior graded samples (essay text + labels)
    - leniency: 0..1 (used as a hint, not hard math)
    """
    try:
        user_payload = {
            "rubric_schema": rubric_schema,
            "leniency_hint": float(leniency),
            "anchors": _format_anchors(anchors)[:6],
            "essay_text": essay_text,
        }
        resp = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": _GRADE_SYSTEM},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}
            ],
            temperature=0.2,
            max_tokens=1200,
        )
        data = json.loads(resp["choices"][0]["message"]["content"])
        # Ensure every criterion has a slot
        crit_names = [c["name"] for c in rubric_schema.get("criteria", [])]
        pc = data.get("per_criterion", {}) or {}
        for n in crit_names:
            pc.setdefault(n, None)
        data["per_criterion"] = pc
        if "confidence" not in data:
            data["confidence"] = "medium"
        return data
    except Exception as e:
        return {
            "overall": None,
            "per_criterion": {},
            "rationales": {"_note": f"Grading failed: {e}"},
            "confidence": "low",
        }
