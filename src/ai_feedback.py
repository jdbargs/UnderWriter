# src/ai_feedback.py
import os
import openai

# Legacy client path (repo pins openai==0.28.1)
openai.api_key = os.getenv("OPENAI_API_KEY")

# --------------------------
# Core Writing Companion
# --------------------------
_COMPANION_SYSTEM = """You are a reflective writing companion.
You never write or rewrite for the user. You read what they wrote and respond with insight:
interpretation, frank critique when warranted, and precise micro-adjustments (punctuation,
connective words, synonyms, minor flow tweaks). Keep it conversational, warm, and direct.
Avoid technical metrics or scores. Speak to effect on a reader (tone, energy, clarity, rhythm).
Honor the user's intention and established style. If the writing is already clear, affirm and keep suggestions minimal.
If intention is unclear, ask one pointed question (at most one)."""

def get_ai_feedback(text: str, profile_summary: str = "") -> str:
    """
    Standard companion reflection (not FlowState).
    Returns a short paragraph plus micro-suggestions, respecting non-generative rules.
    """
    user_msg = (
        f"Profile hint: {profile_summary or 'learning user style'}\n\n"
        "User writing:\n---\n" + text + "\n---\n"
        "Give a short reflection and a few micro-suggestions (tiny adjustments only). Do not rewrite."
    )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": _COMPANION_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.5,
            max_tokens=300,
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"(Fallback) Reflection unavailable: {e}. One nudge: read once out loud and trim any filler."

# --------------------------
# FlowState (Practice Mode)
# --------------------------
_FLOWSTATE_SYSTEM = """You are a reflective writing companion in FlowState (practice) mode.
Constraints:
- Never write or rewrite for the user.
- At most THREE short sentences total.
- Recognize one concrete improvement trend if present.
- Offer exactly ONE micro-nudge aligned to the user’s selected goal(s).
- Keep tone warm, brisk, and direct. No lists, no emojis."""

def get_flow_feedback(text: str, goals: list, last_trends: str = "") -> str:
    """
    FlowState micro-feedback: ≤3 short sentences, one goal-aligned nudge, no rewriting.
    """
    goals_str = ", ".join(goals) if goals else "none"
    user_msg = (
        f"User goals: {goals_str}.\n"
        f"Recent trend summary: {last_trends or 'none'}.\n"
        "User's FlowState attempt:\n"
        f"---\n{text}\n---\n"
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
        # Tiny static fallback if API fails/missing
        return "Nice burst. Keep momentum—state one idea plainly, then add one vivid image next round."
