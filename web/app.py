import streamlit as st
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.analyzer import analyze_text
from src.storage import update_profile
from src.ai_feedback import get_ai_feedback  # AI reflection module

# --- Streamlit Config ---
st.set_page_config(page_title="Style Profiler", page_icon="✍️", layout="centered")
st.title("✍️ Style Profiler")
st.write(
    "Paste some writing, and I'll reflect on its tone, mood, and style. "
    "Over time, I'll get to know your unique voice and comment on how this piece fits into your broader style."
)

# Initialize session history
if "history" not in st.session_state:
    st.session_state.history = []

# Input box
user_input = st.text_area("Write or paste text:", height=150)

# Analyze button
if st.button("Analyze"):
    if user_input.strip():
        # 1. Analyze metrics (for internal profile tracking only)
        metrics = analyze_text(user_input)
        profile = update_profile(metrics)

        # 2. Summarize profile for AI context
        if profile["count"] > 2:
            profile_summary = (
                f"You tend to write with {('longer' if profile['avg_sentence_length'] > 15 else 'shorter')} sentences "
                f"and a {'more varied' if profile['vocab_richness'] > 0.4 else 'simpler'} vocabulary."
            )
        else:
            profile_summary = "No established profile yet; this may be a first impression."

        # 3. Get AI interpretive feedback
        ai_response = get_ai_feedback(user_input, profile_summary)

        # 4. Display AI feedback
        st.markdown("### Feedback")
        st.markdown(ai_response)

        # 5. Save to history
        st.session_state.history.append({
            "text": user_input,
            "ai_feedback": ai_response
        })

# Show history (past entries + feedback)
if st.session_state.history:
    st.markdown("---\n### Past Entries")
    for entry in reversed(st.session_state.history):
        st.markdown(f"**You wrote:**\n> {entry['text']}")
        st.markdown(f"**Feedback:**\n{entry['ai_feedback']}")
        st.markdown("---")
