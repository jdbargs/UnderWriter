import streamlit as st
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db import (
    save_writing, list_writings, get_current_user,
    insert_writing_insight, insert_companion_feedback,
    upsert_style_profile, insert_style_snapshot, count_writings,
)
from src.analyzer import analyze_text
from src.tone_classifier import classify_tone  # your heuristic tone
from src.ai_feedback import get_ai_feedback    # your LLM reflection

# --- assume you already set st.session_state.user with {id,email} after login ---

st.subheader("New Writing")
title = st.text_input("Title (optional)")
text = st.text_area("Write or paste text", height=180)

def infer_intention(txt: str) -> str:
    t = txt.lower()
    if "?" in txt:
        return "inquisitive"
    if any(w in t for w in ["i think", "maybe", "perhaps", "wonder"]):
        return "exploratory"
    if any(w in t for w in ["should", "must", "need to", "important"]):
        return "persuasive"
    if any(w in t for w in ["i feel", "i'm", "sad", "happy", "excited"]):
        return "expressive"
    return "descriptive"

def infer_energy(metrics) -> str:
    # toy heuristic: longer avg sentence ≈ calmer/reflective; shorter ≈ higher energy
    avg_len = metrics.get("sentence_length_avg", 0)
    if avg_len >= 22: return "calm/expansive"
    if avg_len >= 15: return "steady"
    return "brisk"

if st.button("Analyze & Save"):
    if not text.strip():
        st.warning("Please enter some text.")
    else:
        user = get_current_user().user
        user_id = user.id

        # 1) Save writing
        writing = save_writing(user_id, text, title=title or None, metadata={})
        writing_id = writing["id"]

        # 2) Compute basic metrics (internal only)
        metrics = analyze_text(text)
        tone = classify_tone(text)
        intention = infer_intention(text)
        energy = infer_energy(metrics)

        # 3) LLM reflection (Companion)
        try:
            # Minimal profile summary (you can fetch style_profiles later for richer context)
            profile_summary = "Learning your style; reflections deepen as you write more."
            feedback = get_ai_feedback(text, profile_summary)
        except Exception as e:
            feedback = f"(AI feedback unavailable) {e}"

        # 4) Insert insights + feedback rows
        try:
            insert_writing_insight(
                writing_id=writing_id,
                intention=intention,
                tone=tone,
                energy=energy,
                observations=None,            # optional: short natural-language summary (Archivist later)
                micro_suggestions=[],         # optional: fill as you implement micro-edits
                metrics={"avg_sentence_len": metrics.get("sentence_length_avg"),
                        "vocab_richness": metrics.get("vocab_richness")}
            )
            insert_companion_feedback(writing_id, feedback, mode="spotlight")
            st.success("Saved and analyzed.")
            st.markdown("**Reflection:**")
            st.write(feedback)
        except Exception as e:
            st.error(f"Save insights/feedback failed: {e}")

        # 5) Periodically update the style profile + snapshot
        try:
            total = count_writings(user_id)
            if total % 5 == 0:  # every 5th submission
                # crude snapshot for now—replace with Archivist AI summary later
                snapshot = f"By entry {total}, tone leans '{tone}' with '{intention}' intent; energy reads '{energy}'."
                upsert_style_profile(user_id, summary=snapshot, traits={})
                insert_style_snapshot(user_id, snapshot=snapshot, signals={"k": "v"})
        except Exception:
            pass  # non-fatal

st.divider()
st.subheader("Your Past Writings")

try:
    user = get_current_user().user
    writings = list_writings(user.id)
    if not writings:
        st.write("No entries yet.")
    else:
        for w in writings:
            with st.expander(f"{w.get('title') or '(untitled)'} — {w['created_at']}"):
                st.code(w["text"])
                # you can also fetch and show latest feedback/insights here if you want
except Exception as e:
    st.error(f"Could not load writings: {e}")
