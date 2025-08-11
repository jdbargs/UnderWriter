import streamlit as st
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db import sign_up, sign_in, get_current_user, sign_out, save_writing, list_writings
from src.analyzer import analyze_text  # optional; keep for profiling
from src.ai_feedback import get_ai_feedback  # optional; comment out if not ready

st.set_page_config(page_title="Style Profiler", page_icon="✍️", layout="centered")

# Session
if "user" not in st.session_state:
    st.session_state.user = None

def require_auth_ui():
    st.title("✍️ Style Profiler — Sign in")

    tabs = st.tabs(["Sign In", "Sign Up"])
    with tabs[0]:
        with st.form("signin"):
            email = st.text_input("Email", key="signin_email")
            password = st.text_input("Password", type="password", key="signin_pw")
            submitted = st.form_submit_button("Sign In")
            if submitted:
                try:
                    res = sign_in(email, password)
                    # Persist session in supabase client automatically
                    user = get_current_user().user
                    st.session_state.user = {"id": user.id, "email": user.email}
                    st.success("Signed in.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Sign in failed: {e}")

    with tabs[1]:
        with st.form("signup"):
            email_su = st.text_input("Email", key="signup_email")
            password_su = st.text_input("Password", type="password", key="signup_pw")
            submitted_su = st.form_submit_button("Create Account")
            if submitted_su:
                try:
                    sign_up(email_su, password_su)
                    st.success("Account created. Please sign in.")
                except Exception as e:
                    st.error(f"Sign up failed: {e}")

def app_ui():
    st.title("✍️ Style Profiler")
    st.caption(f"Logged in as {st.session_state.user['email']}")
    colA, colB = st.columns([1,1])
    with colB:
        if st.button("Log out"):
            try:
                sign_out()
            finally:
                st.session_state.user = None
                st.rerun()

    st.subheader("New Writing")
    title = st.text_input("Title (optional)")
    text = st.text_area("Write or paste text", height=180)

    if st.button("Analyze & Save"):
        if text.strip():
            # Optional analysis—use internally; don't show raw metrics
            _metrics = analyze_text(text)

            # Optional AI reflection (comment out if API not configured)
            try:
                profile_summary = "Learning your style; reflections will deepen as you write more."
                feedback = get_ai_feedback(text, profile_summary)
                st.markdown("**Reflection:**")
                st.write(feedback)
            except Exception as e:
                st.info(f"(AI feedback unavailable) {e}")

            # Save to DB
            try:
                save_writing(st.session_state.user["id"], text, title=title or None, metadata={})
                st.success("Saved.")
            except Exception as e:
                st.error(f"Save failed: {e}")

    st.divider()
    st.subheader("Your Past Writings")
    try:
        writings = list_writings(st.session_state.user["id"])
        if not writings:
            st.write("No entries yet.")
        else:
            for w in writings:
                st.markdown(f"**{w.get('title') or '(untitled)'}** — _{w['created_at']}_")
                st.code(w["text"])
                st.markdown("---")
    except Exception as e:
        st.error(f"Could not load writings: {e}")

# Gate by auth
try:
    if st.session_state.user is None:
        user = get_current_user().user
        if user:
            st.session_state.user = {"id": user.id, "email": user.email}
except Exception:
    pass

if st.session_state.user is None:
    require_auth_ui()
else:
    app_ui()
