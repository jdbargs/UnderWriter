# src/ai_feedback.py
import os
import json
from typing import Optional, List, Dict, Any

import openai
from dotenv import load_dotenv

# --- Setup ---
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# ============================
# System prompts (guardrails)
# ============================

_COMPANION_SYSTEM = """
You are a reflective writing companion. You never write or rewrite for the user. You only read what they wrote and respond with insight: interpretation, critique when warranted, and precise micro-adjustments (punctuation, connective words, synonyms, or minor flow tweaks). Your job is to help them sound like the best version of themselves, not like you.

Core stance
- Be conversational, warm, and direct — but not indulgent.
- Default to offering both praise and critique unless the writing is professional-grade, original-sounding, and highly consistent with its context. This threshold is rare; most users benefit from specific, frank feedback.
- Be critical when needed: if the writing is weak or the reasoning/facts are flawed, say so plainly and explain why.
- Avoid technical or numeric metrics (no counts, scores, readability numbers). Speak to the effect on a reader (tone, energy, clarity, rhythm).
- Discern the user’s intention, and adapt your feedback lens accordingly (business, technical, creative, etc.).
- Your response should be proportional to the length of their writing. Avoid verbosity.

Personalization rules
- Use the provided “User Context Pack” to compare the current piece to the user’s own baseline (counts, streak, traits, recent excerpts, goals).
- Prefer comparisons to the user’s history over generic rules (e.g., “compared to your usual brisk cadence…”).
- Name recurring quirks gently if traits indicate them (e.g., “those parenthetical asides”).
- If context is thin, say you’re offering a first impression.

Boundaries (hard rules)
- Do not generate standalone text, paragraphs, or rewrites.
- Do not output raw readability metrics or scores.
- Keep suggestions micro and optional.
- Quote the user directly when making observations.

Output style
- 1–2 short paragraphs for reflection.
- Then 2–5 bullet micro‑suggestions (≤ ~12 words each), each grounded in a quoted fragment.
- If the piece is already strong for their usual style, say so and keep notes minimal.
"""

_FLOWSTATE_SYSTEM = """
You are a reflective writing companion in FlowState practice mode.
Constraints:
- Never write or rewrite for the user.
- At most THREE short sentences total.
- Recognize one concrete improvement trend if present (based on context pack/goals).
- Offer exactly ONE micro‑nudge aligned to the user’s selected goal(s).
- Keep tone warm, brisk, and direct. No lists, no emojis.
"""

# ============================
# Helpers
# ============================

def _truncate(s: str, max_chars: int) -> str:
    if s is None:
        return ""
    s = s.strip()
    return s if len(s) <= max_chars else s[:max_chars] + "…"

def _safe_json(obj: Any, max_chars: int = 2000) -> str:
    """
    Stringify JSON safely and cap length to avoid blowing prompt budget.
    """
    try:
        j = json.dumps(obj or {}, ensure_ascii=False)
    except Exception:
        j = "{}"
    return _truncate(j, max_chars)

def _format_personal_anchors(anchors: Optional[List[Dict[str, Any]]], max_each: int = 400, k: int = 3) -> str:
    """
    anchors: list like [{"id": "...", "title": "...", "excerpt": "..."}]
    Returns a compact string for the prompt.
    """
    if not anchors:
        return "[]"
    pruned = []
    for a in anchors[:k]:
        pruned.append({
            "id": a.get("id"),
            "title": a.get("title"),
            "excerpt": _truncate(a.get("excerpt") or "", max_each),
        })
    return _safe_json(pruned, max_chars=1600)

# ============================
# Public API
# ============================

def get_ai_feedback(
    text: str,
    profile_summary: str = "",
    context_pack: Optional[Dict[str, Any]] = None,
    personal_anchors: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Standard companion reflection (not FlowState).
    Returns a short reflection + micro‑suggestions, with personalization.
    - context_pack: {"overview": {...}, "style_profile": {...}, "recent_samples": [...], "flow_metrics_recent": [...], "active_goals": [...]}
    - personal_anchors: list of the user's own past excerpts to serve as style anchors
    """
    ctx_json = _safe_json(context_pack, max_chars=1800)
    anchors_json = _format_personal_anchors(personal_anchors, max_each=360, k=3)

    user_msg = (
        f"User Context Pack (counts/streak/traits/goals/excerpts):\n{ctx_json}\n\n"
        f"User style summary (if any): {profile_summary or 'learning user style'}\n\n"
        f"Personal anchors (prior excerpts to calibrate feedback):\n{anchors_json}\n\n"
        "Current writing:\n---\n" + _truncate(text, 6000) + "\n---\n\n"
        "Task: Provide a short reflection and a few micro‑suggestions.\n"
        "- Compare to the user's own baseline when relevant (from Context Pack/anchors).\n"
        "- Keep suggestions micro (tiny edits only), each grounded in a brief quote.\n"
        "- Do NOT rewrite or generate content for the user."
    )

    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": _COMPANION_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.5,
            max_tokens=380,
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"(Fallback) Reflection unavailable: {e}. One nudge: read once out loud and trim any filler."

def get_flow_feedback(
    text: str,
    goals: List[str],
    last_trends: str = "",
    context_pack: Optional[Dict[str, Any]] = None
) -> str:
    """
    FlowState micro‑feedback: ≤3 sentences, one micro‑nudge aligned to active goals.
    - goals: e.g. ['playfulness','clarity']
    - last_trends: a compact string like 'Playfulness +0.07; Clarity -0.02'
    - context_pack: optional; used to recognize improvement trend or note consistency
    """
    goals_str = ", ".join(goals) if goals else "none"
    ctx_hint = _safe_json(
        {
            "active_goals": (context_pack or {}).get("active_goals"),
            "overview": (context_pack or {}).get("overview"),
        },
        max_chars=600,
    )

    user_msg = (
        f"User goals: {goals_str}\n"
        f"Recent trend summary: {last_trends or 'none'}\n"
        f"Context (counts/goals): {ctx_hint}\n"
        "User's FlowState attempt:\n"
        f"---\n{_truncate(text, 3000)}\n---\n"
        "Respond now with ≤3 short sentences, honoring the constraints."
    )

    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": _FLOWSTATE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.4,
            max_tokens=120,
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception:
        # Minimal non-LLM fallback
        return "Nice burst. Keep momentum—state one idea plainly, then add one vivid image."

# ============================
# (Optional) tiny convenience
# ============================

def format_context_hint_for_logs(context_pack: Optional[Dict[str, Any]]) -> str:
    """
    Handy if you want to append a one-liner hint into logs or UI.
    """
    if not context_pack:
        return ""
    ov = (context_pack or {}).get("overview", {}) or {}
    return f"(Overview: writings={ov.get('writings_count',0)}, bursts={ov.get('flow_attempts_count',0)}, streak={ov.get('streak_days',0)}d)"
