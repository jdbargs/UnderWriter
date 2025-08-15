# web/app.py
import streamlit as st
import sys, os
from datetime import datetime, timezone
import io

# Optional file parsers for rubric uploads
try:
    import PyPDF2
except Exception:
    PyPDF2 = None
try:
    import docx  # python-docx
except Exception:
    docx = None

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
    # GradeSim
    create_rubric, list_rubrics, get_rubric, archive_rubric,
    add_rubric_criterion, list_rubric_criteria, update_rubric_criterion, delete_rubric_criterion,
    add_grading_sample, list_grading_samples, delete_grading_sample,
    create_grader_version, list_grader_versions, set_active_grader_version, get_active_grader_version,
    # Roles
    get_profile, upsert_profile
)
from src.supabase_client import supabase

# Optional analysis imports (comment out if not ready)
from src.analyzer import analyze_text, analyze_flow_text, compute_flow_composite
from src.tone_classifier import classify_tone
from src.ai_feedback import get_ai_feedback, get_flow_feedback
from src.ai_grader import extract_rubric_schema

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
            submitted = st.form_submit_button("Sign In", use_container_width=True)
            if submitted:
                try:
                    res = sign_in(email, password)
                    session = res.session
                    st.session_state.sb_session = {
                        "access_token": session.access_token,
                        "refresh_token": session.refresh_token,
                    }
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
            submitted_su = st.form_submit_button("Create Account", use_container_width=True)
            if submitted_su:
                try:
                    sign_up(email_su, password_su)
                    st.success("Account created. Please sign in.")
                except Exception as e:
                    st.error(f"Sign up failed: {e}")

# ----------------------------
# FlowState (Practice) section
# ----------------------------
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
                key="fs_mode_select",
            )
        with c2:
            duration = st.number_input(
                "Duration (sec)",
                min_value=30,
                max_value=600,
                value=st.session_state.fs_duration,
                step=15,
                disabled=(mode != "timed"),
                key="fs_duration_input",
            )
        with c3:
            target_words = st.number_input(
                "Target words",
                min_value=30,
                max_value=1000,
                value=st.session_state.fs_target_words,
                step=10,
                disabled=(mode != "wordcount"),
                key="fs_target_words_input",
            )

        goals = st.multiselect(
            "Focus goals",
            ["playfulness", "clarity", "creativity"],
            default=st.session_state.fs_goals,
            key="fs_goals_multiselect",
        )

        start_burst = st.form_submit_button("Start burst", use_container_width=True)

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
            if st.button("Begin writing", key="fs_begin_btn"):
                st.session_state.fs_started_at = datetime.now(timezone.utc)
        else:
            st.caption(f"Started at {st.session_state.fs_started_at.isoformat()} (UTC)")

        # Text area
        st.session_state.fs_response = st.text_area(
            "Your burst (submit in one go; keep it spontaneous)",
            value=st.session_state.fs_response,
            height=200,
            placeholder="Type fast. Don’t overthink.",
            key="fs_response_text",
        )

        # Submit attempt
        if st.session_state.fs_started_at and st.button("Submit", key="fs_submit_btn"):
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

# ----------------------------
# GradeSim — Teacher Console
# ----------------------------
def _read_uploaded_text(uploaded_file) -> str:
    if uploaded_file is None:
        return ""
    name = uploaded_file.name.lower()
    data = uploaded_file.read()
    buf = io.BytesIO(data)

    if name.endswith(".pdf"):
        if not PyPDF2:
            return "(Install PyPDF2 to parse PDFs)"
        try:
            reader = PyPDF2.PdfReader(buf)
            pages = [p.extract_text() or "" for p in reader.pages]
            return "\n\n".join(pages).strip()
        except Exception:
            return "(Could not parse PDF. Try a .docx or .txt.)"

    if name.endswith(".docx"):
        if not docx:
            return "(Install python-docx to parse DOCX)"
        try:
            d = docx.Document(buf)
            return "\n".join(p.text for p in d.paragraphs).strip()
        except Exception:
            return "(Could not parse DOCX. Try a PDF or .txt.)"

    # Fallback: treat as text
    try:
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return "(Unsupported file encoding)"

def gradesim_teacher_section():
    st.header("GradeSim — Teacher Console")

    # user/role
    uid = current_user_id()
    prof = get_profile(uid) if uid else None
    role = (prof or {}).get("role", "student")
    if role not in ("teacher", "admin"):
        st.info("Only teachers can access GradeSim. Update your profile role to 'teacher' if you're testing.")
        return

    # ---- Rubric import (upload → extract → tweak → save) ----
    st.subheader("Create or import a rubric")
    up_col1, up_col2 = st.columns([2,1])
    with up_col1:
        uploaded = st.file_uploader(
            "Upload rubric (PDF, DOCX, or TXT)", type=["pdf", "docx", "txt"], key="rubric_uploader"
        )
    with up_col2:
        scale_choice = st.selectbox("Preferred scale (fallback)", ["0-4", "0-100"], index=0, key="pref_scale_select")

    if uploaded:
        raw_text = _read_uploaded_text(uploaded)
        if not raw_text or raw_text.startswith("("):
            st.error(raw_text or "Could not read file.")
        else:
            with st.spinner("Extracting rubric…"):
                schema = extract_rubric_schema(raw_text)
            if not schema.get("scale"):
                schema["scale"] = scale_choice

            st.success(f"Extracted: {schema.get('title','(untitled)')}")
            crit_names = [c["name"] for c in schema["criteria"]]
            st.markdown("**Criteria & weights (adjust if needed)**")
            new_weights = []
            for idx, c in enumerate(schema["criteria"]):
                col1, col2 = st.columns([3,2])
                col1.write(f"**{c['name']}**")
                w = col2.slider(
                    f"Weight: {c['name']}",
                    0.0, 1.0, float(c.get("weight", 0.25)),
                    0.05, key=f"rubric_weight_{idx}"
                )
                new_weights.append(w)
            total = sum(new_weights) or 1.0
            for i, c in enumerate(schema["criteria"]):
                c["weight"] = round(new_weights[i] / total, 4)

            st.markdown("**Preview**")
            st.dataframe(
                [{"Criterion": c["name"], "Weight": c["weight"]} for c in schema["criteria"]],
                use_container_width=True,
            )
            st.caption("Descriptor levels were captured; you can refine them later.")

            if st.button("Save rubric", key="save_extracted_rubric_btn"):
                rrow = create_rubric(
                    teacher_id=uid,
                    title=schema.get("title") or "(untitled)",
                    subject=None,
                    grade_level=None,
                    scale=schema.get("scale") or "0-4",
                )
                for c in schema["criteria"]:
                    add_rubric_criterion(
                        rubric_id=rrow["id"],
                        name=c["name"],
                        descriptor_levels=c.get("descriptor_levels") or {"4":"","3":"","2":"","1":"","0":""},
                        weight=float(c["weight"]),
                    )
                st.success(f"Saved rubric '{rrow['title']}' with {len(schema['criteria'])} criteria.")

    st.divider()
    st.subheader("Manage rubrics / criteria (optional)")
    rubrics = list_rubrics(uid)
    if not rubrics:
        st.caption("No rubrics yet. Upload one above.")
        return

    rubric_map = {f"{r['title']} ({r['id'][:8]})": r for r in rubrics}
    sel_label = st.selectbox("Select a rubric", list(rubric_map.keys()), key="rubric_select_existing")
    rubric = rubric_map[sel_label]
    st.markdown(f"**Selected:** {rubric['title']} — scale `{rubric['scale']}`")

    crits = list_rubric_criteria(rubric["id"])
    if crits:
        for c in crits:
            with st.expander(f"{c['name']} — weight {c['weight']}"):
                st.json(c["descriptor_levels"], expanded=False)
                colu1, colu2, colu3 = st.columns([1,1,1])
                new_name = colu1.text_input(
                    f"Rename ({c['id'][:6]})",
                    value=c["name"],
                    key=f"crit_name_{c['id']}"
                )
                new_weight = colu2.number_input(
                    f"Weight ({c['id'][:6]})",
                    min_value=0.0, max_value=1.0,
                    value=float(c["weight"]),
                    step=0.05,
                    key=f"crit_weight_{c['id']}"
                )
                if colu3.button(f"Save ({c['id'][:6]})", key=f"crit_save_{c['id']}"):
                    update_rubric_criterion(c["id"], name=new_name, weight=new_weight)
                    st.success("Updated. Refresh to see changes.")
                if st.button(f"Delete criterion {c['id'][:6]}", key=f"crit_del_{c['id']}"):
                    delete_rubric_criterion(c["id"])
                    st.warning("Deleted. Refresh to see changes.")

    # ---- (Optional) Manual add criterion retained, but no JSON required to use GradeSim ----
    with st.form("add_criterion"):
        st.caption("Add a criterion (optional)")
        cc1, cc2 = st.columns([1,1])
        name = cc1.text_input("Criterion name", placeholder="Thesis, Evidence, Organization…", key="crit_add_name")
        weight = cc2.number_input("Weight (0–1)", min_value=0.0, max_value=1.0, value=0.25, step=0.05, key="crit_add_weight")
        st.write("Descriptor levels (JSON): e.g. {\"4\":\"mastery…\",\"3\":\"…\",\"2\":\"…\",\"1\":\"…\",\"0\":\"…\"}")
        raw_json = st.text_area("Descriptors JSON", height=120, placeholder='{"4":"…","3":"…","2":"…","1":"…","0":"…"}', key="crit_add_desc_json")
        addc = st.form_submit_button("Add criterion", use_container_width=True)
        if addc:
            try:
                import json
                desc = json.loads(raw_json) if raw_json.strip() else {"4":"","3":"","2":"","1":"","0":""}
                add_rubric_criterion(rubric["id"], name=name.strip(), descriptor_levels=desc, weight=float(weight))
                st.success("Criterion added.")
            except Exception as e:
                st.error(f"Bad JSON or save failed: {e}")

    st.divider()
    st.subheader("Grading Samples (Anchors)")
    samples = list_grading_samples(uid, rubric_id=rubric["id"])
    if samples:
        for s in samples[:10]:
            with st.expander(f"{(s.get('title') or '(untitled)')} — {s['id'][:8]}"):
                st.code(s["text"][:800] + ("..." if len(s["text"]) > 800 else ""))
                st.json({"overall": s.get("overall"), "per_criterion": s.get("per_criterion")}, expanded=False)
                if st.button(f"Delete sample {s['id'][:6]}", key=f"sample_del_{s['id']}"):
                    delete_grading_sample(s["id"])
                    st.warning("Sample deleted. Refresh to update list.")

    with st.form("add_sample"):
        st.caption("Add a graded sample (optional but improves calibration)")
        s1, s2 = st.columns([2,1])
        title = s1.text_input("Sample title (optional)", key="sample_title_input")
        overall = s2.number_input(f"Overall ({rubric['scale']})", min_value=0.0, max_value=100.0, value=3.0, step=0.5, key="sample_overall_input")
        text = st.text_area("Student text", height=180, key="sample_text_input")
        st.write("Per-criterion scores JSON (e.g., {\"Thesis\":3,\"Evidence\":4})")
        raw_scores = st.text_area("Scores JSON", height=100, key="sample_scores_json")
        add_s = st.form_submit_button("Save sample", use_container_width=True)
        if add_s:
            try:
                import json
                pc = json.loads(raw_scores) if raw_scores.strip() else {}
                add_grading_sample(uid, rubric["id"], title=title or None, text=text, overall=float(overall), per_criterion=pc)
                st.success("Sample saved.")
            except Exception as e:
                st.error(f"Save failed: {e}")

    st.divider()
    st.subheader("Grader Versions")
    versions = list_grader_versions(uid, rubric["id"])
    active = get_active_grader_version(uid, rubric["id"])
    if versions:
        st.caption(f"Active version: **{active['version']}**" if active else "No active version.")
        for v in versions:
            with st.expander(f"Version {v['version']} — {'ACTIVE' if v['is_active'] else 'inactive'}"):
                st.json({"method": v["method"], "config": v["config"], "train_stats": v.get("train_stats")})
                if not v["is_active"]:
                    if st.button(f"Activate v{v['version']}", key=f"activate_v_{v['id']}"):
                        set_active_grader_version(uid, rubric["id"], v["id"])
                        st.success("Activated.")
    with st.form("new_version"):
        st.caption("Create a new version (stores config; you control anchors & parameters)")
        leniency = st.slider("Leniency (0=stricter, 1=lenient)", 0.0, 1.0, 0.5, 0.05, key="leniency_slider")
        sample_options = {f"{(s.get('title') or 'untitled')} [{s['id'][:6]}]": s["id"] for s in samples}
        chosen = st.multiselect("Anchor samples (recommended: 3–6 across the range)", list(sample_options.keys()), key="anchor_multiselect")
        create_v = st.form_submit_button("Create version", use_container_width=True)
        if create_v:
            config = {"leniency": leniency, "anchors": [sample_options[k] for k in chosen]}
            vrow = create_grader_version(uid, rubric["id"], config=config, method="few_shot_prompt", train_stats=None, is_active=False)
            st.success(f"Created version {vrow['version']}. Activate when ready.")

# ----------------------------
# App UI (authed)
# ----------------------------
def app_screen():
    st.title("✍️ UnderWriter")
    st.caption(f"Logged in as {st.session_state.user['email']}")

    if st.button("Log out", key="logout_btn"):
        try:
            sign_out()
        finally:
            st.session_state.user = None
            st.session_state.sb_session = None
            st.rerun()

    # ---- Role / Profile ----
    uid = current_user_id()
    prof = get_profile(uid) if uid else None
    role = (prof or {}).get("role", "student")

    with st.expander("Profile"):
        st.write(f"Role: **{role}**")
        colA, colB = st.columns(2)
        new_name = colA.text_input(
            "Display name",
            value=(prof or {}).get("display_name", ""),
            key="profile_display_name_input",
        )
        new_school = colB.text_input(
            "School (optional)",
            value=(prof or {}).get("school", ""),
            key="profile_school_input",
        )
        if st.button("Save profile", key="profile_save_btn"):
            upsert_profile(uid, display_name=new_name, school=new_school)
            st.success("Profile saved.")

    # ---- Tabs: Writing | FlowState | (GradeSim if teacher) ----
    tabs = ["Writing Companion", "FlowState (Practice)"]
    is_teacher_role = role in ("teacher", "admin")
    if is_teacher_role:
        tabs.append("GradeSim (Teacher)")

    t_objs = st.tabs(tabs)

    # --- Tab 0: Writing Companion ---
    with t_objs[0]:
        st.subheader("New Writing")
        title = st.text_input("Title (optional)", key="wc_title_input")
        text = st.text_area("Write or paste text", height=180, key="wc_text_input")

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

        if st.button("Analyze & Save", key="wc_analyze_btn"):
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
                    observations=None,
                    micro_suggestions=[],
                    metrics={
                        "avg_sentence_len": metrics.get("sentence_length_avg"),
                        "vocab_richness": metrics.get("vocab_richness"),
                    },
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

    # --- Tab 1: FlowState ---
    with t_objs[1]:
        flowstate_section()

    # --- Tab 2: GradeSim (Teacher) ---
    if is_teacher_role:
        with t_objs[2]:
            gradesim_teacher_section()

# ---- Entry point ----
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
