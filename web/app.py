# web/app.py
import streamlit as st
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db import (
    sign_up, sign_in, sign_out, get_current_user, set_session,
    save_writing, list_writings, count_writings,
    insert_writing_insight, insert_companion_feedback,
    upsert_style_profile, insert_style_snapshot
)
from src.supabase_client import supabase

# Optional analysis imports (comment out if not ready)
from src.analyzer import analyze_text
from src.tone_classifier import classify_tone
from src.ai_feedback import get_ai_feedback

st.set_page_config(page_title="Style Profiler", page_icon="✍️", layout="centered")

# ---- Session bootstrapping ----
if "user" not in st.session_state:
    st.session_state.user = None
if "sb_session" not in st.session_state:
    st.session_state.sb_session = None

# Try to restore session on every run
try:
    if st.session_state.sb_session:
        set_session(
            st.session_state.sb_session["access_token"],
            st.session_state.sb_session["refresh_token"],
        )
        u = get_current_user().user
        if u and not st.session_state.user:
            st.session_state.user = {"id": u.id, "email": u.email}
except Exception:
    pass

def current_user_id():
    # Prefer cached
    if st.session_state.user and "id" in st.session_state.user:
        return st.session_state.user["id"]
    # Fallback to client
    try:
        u = get_current_user().user
        return u.id if u else None
    except Exception:
        return None

# ---- Auth UI ----
def auth_screen():
    st.title("✍️ Style Profiler — Sign in")

    tab_signin, tab_signup = st.tabs(["Sign In", "Sign Up"])
    with tab_signin:
        with st.form("signin_form"):
            email = st.text_input("Email", key="signin_email")
            password = st.text_input("Password", type="password", key="signin_pw")
            submitted = st.form_submit_button("Sign In")
            if submitted:
                try:
                    res = sign_in(email, password)
                    session = res.session
                    # persist tokens so we can restore across reruns
                    st.session_state.sb_session = {
                        "access_token": session.access_token,
                        "refresh_token": session.refresh_token,
                    }
                    # set into client immediately
                    set_session(session.access_token, session.refresh_token)
                    user = get_current_user().user
                    st.session_state.user = {"id": user.id, "email": user.email}
                    st.success("Signed in.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Sign in failed: {e}")

    with tab_signup:
        with st.form("signup_form"):
            email_su = st.text_input("Email", key="signup_email")
            password_su = st.text_input("Password", type="password", key="signup_pw")
            submitted_su = st.form_submit_button("Create Account")
            if submitted_su:
                try:
                    sign_up(email_su, password_su)
                    st.success("Account created. Please sign in.")
                except Exception as e:
                    st.error(f"Sign up failed: {e}")

# ---- App UI (authed) ----
def app_screen():
    st.title("✍️ Style Profiler")
    st.caption(f"Logged in as {st.session_state.user['email']}")

    if st.button("Log out"):
        try:
            sign_out()
        finally:
            st.session_state.user = None
            st.session_state.sb_session = None
            st.rerun()

    st.subheader("New Writing")
    title = st.text_input("Title (optional)")
    text = st.text_area("Write or paste text", height=180)

    def infer_intention(txt: str) -> str:
        t = txt.lower()
        if "?" in txt: return "inquisitive"
        if any(w in t for w in ["i think", "maybe", "perhaps", "wonder"]): return "exploratory"
        if any(w in t for w in ["should", "must", "need to", "important"]): return "persuasive"
        if any(w in t for w in ["i feel", "i'm", "sad", "happy", "excited"]): return "expressive"
        return "descriptive"

    def infer_energy(metrics) -> str:
        avg_len = metrics.get("sentence_length_avg", 0)
        if avg_len >= 22: return "calm/expansive"
        if avg_len >= 15: return "steady"
        return "brisk"

    if st.button("Analyze & Save"):
        uid = current_user_id()
        if not uid:
            st.error("You must be signed in to save.")
            st.stop()

        if not text.strip():
            st.warning("Please enter some text.")
            st.stop()

        # 1) Save writing
        writing = save_writing(uid, text, title=title or None, metadata={})
        writing_id = writing["id"]

        # 2) Internal metrics (optional)
        try:
            metrics = analyze_text(text)
            tone = classify_tone(text)
            intention = infer_intention(text)
            energy = infer_energy(metrics)
        except Exception:
            # if analyzer isn't configured, keep going
            metrics, tone, intention, energy = {}, None, None, None

        # 3) LLM reflection (optional)
        feedback = None
        try:
            profile_summary = "Learning your style; reflections deepen as you write more."
            feedback = get_ai_feedback(text, profile_summary)
            st.markdown("**Reflection:**")
            st.write(feedback)
        except Exception as e:
            st.info(f"(AI feedback unavailable) {e}")

        # 4) Insert insights + feedback rows
        try:
            insert_writing_insight(
                writing_id=writing_id,
                intention=intention,
                tone=tone,
                energy=energy,
                observations=None,        # Archivist later
                micro_suggestions=[],     # fill as you add micro-edits
                metrics={"avg_sentence_len": metrics.get("sentence_length_avg"),
                        "vocab_richness": metrics.get("vocab_richness")}
            )
            if feedback:
                insert_companion_feedback(writing_id, feedback, mode="spotlight")

            st.success("Saved.")
        except Exception as e:
            st.error(f"Save insights/feedback failed: {e}")

        # 5) Periodic style snapshot
        try:
            total = count_writings(uid)
            if total % 5 == 0:
                snap = f"By entry {total}, tone leans '{tone}' with '{intention}' intent; energy '{energy}'."
                upsert_style_profile(uid, summary=snap, traits={})
                insert_style_snapshot(uid, snapshot=snap, signals={})
        except Exception:
            pass

    st.divider()
    st.subheader("Your Past Writings")

    uid = current_user_id()
    if not uid:
        st.warning("Please sign in to view your writings.")
        return

    try:
        writings = list_writings(uid)
        if not writings:
            st.write("No entries yet.")
        else:
            for w in writings:
                with st.expander(f"{w.get('title') or '(untitled)'} — {w['created_at']}"):
                    st.code(w["text"])
    except Exception as e:
        st.error(f"Could not load writings: {e}")

# ---- Entry point ----
# If we can detect a user, go to app; else show auth
try:
    if st.session_state.user is None:
        u = get_current_user().user
        if u:
            st.session_state.user = {"id": u.id, "email": u.email}
except Exception:
    pass

if st.session_state.user is None:
    auth_screen()
else:
    app_screen()
