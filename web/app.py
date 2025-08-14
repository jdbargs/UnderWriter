# web/app.py
import streamlit as st
import sys, os
from datetime import datetime, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db import (
    # Auth
    sign_up, sign_in, sign_out, get_current_user, set_session,
    # Core writings
    save_writing, list_writings, count_writings,
    insert_writing_insight, insert_companion_feedback,
    upsert_style_profile, insert_style_snapshot,
    # FlowState additions
    create_flow_session, random_flow_prompt, insert_flow_attempt,
    insert_flow_metrics, user_metric_baseline, insert_flow_feedback,
)
from src.supabase_client import supabase

# Optional analysis imports (comment out if not ready)
from src.analyzer import analyze_text, analyze_flow_text, compute_flow_composite
from src.tone_classifier import classify_tone
from src.ai_feedback import get_ai_feedback, get_flow_feedback

st.set_page_config(page_title="UnderWriter", page_icon="✍️", layout="centered")

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
    st.title("✍️ UnderWriter — Sign in")

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

# ---- FlowState UI (Practice Mode) ----
def flowstate_section():
    st.header("FlowState — quick bursts for flow & style")

    uid = current_user_id()
    if not uid:
        st.info("Sign in to use FlowState.")
        return

    # Initialize session state
    defaults = {
        "fs_session_id": None,
        "fs_prompt": None,
        "fs_prompt_id": None,
        "fs_started_at": None,
        "fs_mode": "timed",
        "fs_duration": 90,
        "fs_target_words": 120,
        "fs_goals": [],
        "fs_response": "",
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

    with st.form("fs_setup", clear_on_submit=False):
        st.subheader("Setup")
        c1, c2, c3 = st.columns(3)
        with c1:
            mode = st.selectbox(
                "Mode",
                ["timed", "wordcount", "free"],
                index=["timed", "wordcount", "free"].index(st.session_state.fs_mode),
            )
        with c2:
            duration = st.number_input(
                "Duration (sec)",
                min_value=30,
                max_value=600,
                value=st.session_state.fs_duration,
                step=15,
                disabled=(mode != "timed"),
            )
        with c3:
            target_words = st.number_input(
                "Target words",
                min_value=30,
                max_value=1000,
                value=st.session_state.fs_target_words,
                step=10,
                disabled=(mode != "wordcount"),
            )

        goals = st.multiselect(
            "Focus goals",
            ["playfulness", "clarity", "creativity"],
            default=st.session_state.fs_goals,
        )

        start_burst = st.form_submit_button("Start burst")

    if start_burst:
        # Persist setup
        st.session_state.fs_mode = mode
        st.session_state.fs_duration = int(duration)
        st.session_state.fs_target_words = int(target_words)
        st.session_state.fs_goals = goals

        # Create session and fetch a prompt
        session = create_flow_session(
            user_id=uid,
            mode=st.session_state.fs_mode,
            duration_seconds=st.session_state.fs_duration if st.session_state.fs_mode == "timed" else None,
            target_words=st.session_state.fs_target_words if st.session_state.fs_mode == "wordcount" else None,
            goal_focus=st.session_state.fs_goals,
        )
        st.session_state.fs_session_id = session["id"]
        prompt_row = random_flow_prompt()
        st.session_state.fs_prompt = (prompt_row or {}).get(
            "text", "Write the first thing that comes to mind about a sound you can hear right now."
        )
        st.session_state.fs_prompt_id = (prompt_row or {}).get("id")
        st.session_state.fs_response = ""
        st.session_state.fs_started_at = None
        st.success("Session ready. Scroll down to begin writing.")

    if st.session_state.fs_session_id:
        st.markdown("#### Prompt")
        st.info(st.session_state.fs_prompt)

        # Begin writing → record start time
        if st.session_state.fs_started_at is None:
            if st.button("Begin writing"):
                st.session_state.fs_started_at = datetime.now(timezone.utc)
        else:
            st.caption(f"Started at {st.session_state.fs_started_at.isoformat()} (UTC)")

        # Text area
        st.session_state.fs_response = st.text_area(
            "Your burst (submit in one go; keep it spontaneous)",
            value=st.session_state.fs_response,
            height=200,
            placeholder="Type fast. Don’t overthink.",
        )

        # Submit attempt
        if st.session_state.fs_started_at and st.button("Submit"):
            end_time = datetime.now(timezone.utc)
            elapsed = (end_time - st.session_state.fs_started_at).total_seconds()

            # Save attempt
            attempt = insert_flow_attempt(
                session_id=st.session_state.fs_session_id,
                prompt_id=st.session_state.fs_prompt_id,
                user_id=uid,
                response_text=st.session_state.fs_response.strip(),
                start_time=st.session_state.fs_started_at,
                end_time=end_time,
                meta={
                    "mode": st.session_state.fs_mode,
                    "duration": st.session_state.fs_duration,
                    "target_words": st.session_state.fs_target_words,
                },
            )

            # Metrics
            m = analyze_flow_text(st.session_state.fs_response)
            composite = compute_flow_composite(
                elapsed_seconds=elapsed, metrics=m, goal_focus=st.session_state.fs_goals
            )
            metrics_row = insert_flow_metrics(
                attempt_id=attempt["id"],
                user_id=uid,
                metrics={
                    "elapsed_seconds": round(elapsed, 2),
                    "word_count": m["word_count"],
                    "wpm": round(60.0 * m["word_count"] / max(elapsed, 1e-6), 2),
                    "vocab_type_count": m["vocab_type_count"],
                    "vocab_ttr": m["vocab_ttr"],
                    "repetition_rate": m["repetition_rate"],
                    "playfulness_score": m["playfulness_score"],
                    "clarity_score": m["clarity_score"],
                    "creativity_score": m["creativity_score"],
                    "composite_score": composite,
                },
            )

            # Goal deltas vs 7-day baseline
            trend_bits = []
            for focus in st.session_state.fs_goals:
                key = f"{focus}_score"
                baseline = user_metric_baseline(uid, key, days=7) or 0.0
                val = float(m[key])
                delta = round(val - baseline, 4)
                trend_bits.append(f"{focus.capitalize()} {('+' if delta >= 0 else '')}{delta:.2f}")
            last_trends = "; ".join(trend_bits) if trend_bits else "no active goal trend"

            # Micro-feedback (≤3 sentences)
            fb = get_flow_feedback(
                st.session_state.fs_response, st.session_state.fs_goals, last_trends=last_trends
            )
            insert_flow_feedback(attempt_id=attempt["id"], user_id=uid, feedback_text=fb)

            # UI result
            st.success("Submitted!")
            b1, b2, b3, b4, b5 = st.columns(5)
            b1.metric("WPM", f'{metrics_row["wpm"]}')
            b2.metric("TTR", f'{metrics_row["vocab_ttr"]}')
            b3.metric("Playful", f'{metrics_row["playfulness_score"]}')
            b4.metric("Clarity", f'{metrics_row["clarity_score"]}')
            b5.metric("Creativity", f'{metrics_row["creativity_score"]}')
            st.metric("Composite", f'{metrics_row["composite_score"]}')

            if trend_bits:
                st.caption("Trends vs 7‑day baseline: " + " · ".join(trend_bits))

            st.markdown("**Micro‑feedback**")
            st.write(fb)

            # Prep for another round, keep same session
            prompt_row = random_flow_prompt()
            st.session_state.fs_prompt = (prompt_row or {}).get(
                "text", "Write the first thing that comes to mind about a texture you can feel."
            )
            st.session_state.fs_prompt_id = (prompt_row or {}).get("id")
            st.session_state.fs_response = ""
            st.session_state.fs_started_at = None
            st.info("New prompt loaded. Hit **Begin writing** when ready.")

# ---- App UI (authed) ----
def app_screen():
    st.title("✍️ UnderWriter")
    st.caption(f"Logged in as {st.session_state.user['email']}")

    if st.button("Log out"):
        try:
            sign_out()
        finally:
            st.session_state.user = None
            st.session_state.sb_session = None
            st.rerun()

    # Tabs: Core Writing | FlowState
    tab_core, tab_flow = st.tabs(["Writing Companion", "FlowState (Practice)"])
    with tab_core:
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
        else:
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

    with tab_flow:
        flowstate_section()

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
