# src/ai_grader.py
import os
import json
import openai

openai.api_key = os.getenv("OPENAI_API_KEY")

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
      "descriptor_levels": { "4":"...", "3":"...", "2":"...", "1":"...", "0":"..." } // if 0-100, normalize to 4..0 bands
    }
  ]
}
"""

def _normalize_weights(criteria):
    total = sum(c.get("weight", 0) for c in criteria) or 1.0
    for c in criteria:
        c["weight"] = round(float(c.get("weight", 0)) / total, 4)
    return criteria

def extract_rubric_schema(rubric_text: str) -> dict:
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
        # Normalize weights to sum ~1
        data["criteria"] = _normalize_weights(data.get("criteria", []))
        # Ensure 0-4 scale canonicalization
        data["scale"] = data.get("scale") or "0-4"
        if data["scale"] not in ("0-4", "0-100"):
            data["scale"] = "0-4"
        # Ensure descriptors have 4..0 keys
        for c in data["criteria"]:
            d = c.get("descriptor_levels") or {}
            # If 0-100 bands provided, map to 4..0
            keys = list(d.keys())
            if any("%" in k for k in keys) or any(k.isdigit() and int(k) > 4 for k in keys):
                # leave as-is; teacher can tweak later if needed
                pass
            # guarantee all bands exist
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
