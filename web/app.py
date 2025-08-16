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
    create_flow_prompt, list_flow_prompts_for_teacher, set_flow_prompt_active,
    assign_prompts_to_assignment, remove_prompt_from_assignment, list_prompts_for_assignment,
    random_assigned_prompt,  # if you want to call it in UI
    # GradeSim
    create_rubric, list_rubrics, get_rubric, archive_rubric,
    add_rubric_criterion, list_rubric_criteria, update_rubric_criterion, delete_rubric_criterion,
    add_grading_sample, list_grading_samples, delete_grading_sample,
    create_grader_version, list_grader_versions, set_active_grader_version, get_active_grader_version,
    # Assignments
    create_assignment, list_assignments, get_assignment, update_assignment, delete_assignment,
    # Roles
    get_profile, upsert_profile
)
from src.supabase_client import supabase

# Optional analysis imports (comment out if not ready)
from src.analyzer import analyze_text, analyze_flow_text, compute_flow_composite
from src.tone_classifier import classify_tone
from src.ai_feedback import get_ai_feedback, get_flow_feedback
from src.ai_grader import extract_rubric_schema, extract_scored_sample, grade_with_rubric


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

    # Role detection
    prof = get_profile(uid) if uid else None
    role = (prof or {}).get("role", "student")
    is_teacher = role in ("teacher", "admin")

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
        "fs_use_my_prompts": False,  # teacher option
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

    # --------------------------
    # Teacher prompt management
    # --------------------------
    if is_teacher:
        with st.expander("Teacher: Manage FlowState prompts"):
            with st.form("create_flow_prompt_form"):
                p1, p2 = st.columns([3,1])
                new_prompt_text = p1.text_area(
                    "New prompt",
                    height=100,
                    placeholder="E.g., Describe a small sound that reveals a larger story.",
                    key="fsp_new_text",
                )
                tag_str = p2.text_input("Tags (comma-sep)", placeholder="sensory, narrative", key="fsp_tags")
                level = p2.selectbox("Level (optional)", ["", "9th", "10th", "11th", "12th"], index=0, key="fsp_level")
                active = p2.checkbox("Active", value=True, key="fsp_active")
                addp = st.form_submit_button("Add prompt")
                if addp and new_prompt_text.strip():
                    tags = [t.strip() for t in (tag_str or "").split(",") if t.strip()]
                    create_flow_prompt(uid, new_prompt_text.strip(), tags=tags, level=(level or None) or None, active=active)
                    st.success("Prompt created.")
                    st.rerun()

            # List teacher prompts
            teacher_prompts = list_flow_prompts_for_teacher(uid, active_only=False)
            if not teacher_prompts:
                st.caption("You haven’t created any prompts yet.")
            else:
                st.markdown("**Your prompts**")
                for p in teacher_prompts[:50]:
                    colx, coly = st.columns([6,2])
                    colx.write(f"• {p['text'][:100]}{'…' if len(p['text'])>100 else ''}")
                    new_act = coly.checkbox(
                        "Active", value=p.get("active", True), key=f"fsp_toggle_{p['id']}"
                    )
                    # If toggled, update
                    if new_act != p.get("active", True):
                        set_flow_prompt_active(p["id"], new_act)
                        st.experimental_rerun()

            # Option for teachers to pull *only* from their prompts when starting a burst
            st.session_state.fs_use_my_prompts = st.checkbox(
                "When I start a burst, use only my prompts (not global)",
                value=st.session_state.fs_use_my_prompts,
                key="fsp_use_mine",
            )

    # Helper: pick a random teacher prompt (active)
    def _random_teacher_prompt(teacher_id: str):
        rows = list_flow_prompts_for_teacher(teacher_id, active_only=True)
        if not rows:
            return None
        import random
        r = random.choice(rows)
        return {"id": r["id"], "text": r["text"]}

    # --------------------------
    # Setup form (student view)
    # --------------------------
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

        # Create session
        session = create_flow_session(
            user_id=uid,
            mode=st.session_state.fs_mode,
            duration_seconds=st.session_state.fs_duration if st.session_state.fs_mode == "timed" else None,
            target_words=st.session_state.fs_target_words if st.session_state.fs_mode == "wordcount" else None,
            goal_focus=st.session_state.fs_goals,
        )
        st.session_state.fs_session_id = session["id"]

        # Choose a prompt
        prompt_row = None
        if is_teacher and st.session_state.fs_use_my_prompts:
            prompt_row = _random_teacher_prompt(uid)
        if not prompt_row:
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
                st.caption("Trends vs 7-day baseline: " + " · ".join(trend_bits))

            st.markdown("**Micro-feedback**")
            st.write(fb)

            # Prep for another round
            next_prompt = None
            if is_teacher and st.session_state.fs_use_my_prompts:
                next_prompt = _random_teacher_prompt(uid)
            if not next_prompt:
                next_prompt = random_flow_prompt()

            st.session_state.fs_prompt = (next_prompt or {}).get(
                "text", "Write the first thing that comes to mind about a texture you can feel."
            )
            st.session_state.fs_prompt_id = (next_prompt or {}).get("id")
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

    uid = current_user_id()
    prof = get_profile(uid) if uid else None
    role = (prof or {}).get("role", "student")
    if role not in ("teacher", "admin"):
        st.info("Only teachers can access GradeSim. Update your profile role to 'teacher' if you're testing.")
        return

    # ---- Rubric import (upload → extract → tweak weights → save) ----
    st.subheader("Create or import a rubric")
    up_col1, up_col2 = st.columns([2,1])
    with up_col1:
        uploaded = st.file_uploader("Upload rubric (PDF, DOCX, or TXT)", type=["pdf", "docx", "txt"], key="rubric_uploader")
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
            st.dataframe(
                [{"Criterion": c["name"], "Weight": c["weight"]} for c in schema["criteria"]],
                use_container_width=True,
            )
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

    # ---- Pick rubric, manage assignments ----
    st.subheader("Assignments")
    rubrics = list_rubrics(uid)
    if not rubrics:
        st.caption("No rubrics yet. Upload one above.")
        return

    rubric_map = {f"{r['title']} ({r['id'][:8]})": r for r in rubrics}
    sel_label = st.selectbox("Rubric", list(rubric_map.keys()), key="gs_rubric_select")
    rubric = rubric_map[sel_label]

    # Create assignment
    with st.form("create_assignment"):
        a1, a2, a3 = st.columns([2,1,1])
        a_title = a1.text_input("Assignment title", placeholder="Narrative #1 — Seasons", key="assn_title_input")
        a_period = a2.text_input("Period/Section (optional)", key="assn_period_input")
        a_due = a3.date_input("Due date (optional)", key="assn_due_input")
        leniency = st.slider("Leniency for this assignment (0=stricter, 1=lenient)", 0.0, 1.0, 0.5, 0.05, key="assn_leniency_slider")
        create_a = st.form_submit_button("Create assignment")
        if create_a:
            row = create_assignment(
                teacher_id=uid, rubric_id=rubric["id"], title=a_title.strip() or "Untitled Assignment",
                period=a_period or None, due_date=(a_due.isoformat() if a_due else None), leniency=leniency
            )
            st.success(f"Assignment created: {row['title']}")

    assignments = list_assignments(uid, rubric_id=rubric["id"])
    if not assignments:
        st.caption("No assignments yet for this rubric.")
        return

    assignment_map = {f"{a['title']} ({a.get('period') or 'all'}) [{a['id'][:6]}]": a for a in assignments}
    sel_asn = st.selectbox("Select assignment", list(assignment_map.keys()), key="gs_assignment_select")
    assignment = assignment_map[sel_asn]

    st.divider()

    # ---- Upload graded samples (Essay + Filled rubric) ----
    st.subheader("Upload graded sample")
    s1, s2 = st.columns(2)
    essay_file = s1.file_uploader("Student essay (PDF/DOCX/TXT)", type=["pdf","docx","txt"], key="sample_essay_upload")
    graded_rubric_file = s2.file_uploader("Filled/graded rubric (PDF/DOCX/TXT)", type=["pdf","docx","txt"], key="sample_rubric_upload")
    sample_title = st.text_input("Optional label", placeholder="Student A — Draft 1", key="sample_label_input")

    if st.button("Extract & Save sample", key="sample_save_btn"):
        if not graded_rubric_file:
            st.warning("Please upload the filled rubric for this sample.")
        else:
            essay_text = _read_uploaded_text(essay_file) if essay_file else ""
            rubric_text = _read_uploaded_text(graded_rubric_file)
            # Fetch rubric schema from DB to guide extraction
            crits = list_rubric_criteria(rubric["id"])
            schema = {
                "title": rubric["title"],
                "scale": rubric["scale"],
                "criteria": [{"name": c["name"], "weight": float(c["weight"]), "descriptor_levels": c["descriptor_levels"]} for c in crits],
            }
            from src.ai_grader import extract_scored_sample
            with st.spinner("Reading the filled rubric…"):
                scored = extract_scored_sample(rubric_text, schema)
            st.json(scored, expanded=False)

            row = add_grading_sample(
                teacher_id=uid,
                rubric_id=rubric["id"],
                assignment_id=assignment["id"],
                title=sample_title or None,
                text=essay_text or rubric_text,  # store essay if present, else rubric text for backref
                overall=scored.get("overall"),
                per_criterion=scored.get("per_criterion"),
                rationales=scored.get("rationales"),
            )
            st.success(f"Saved graded sample {row['id'][:8]}.")

    # Show recent samples for this assignment
    st.markdown("**Recent samples for this assignment**")
    samples = list_grading_samples(uid, rubric_id=rubric["id"], assignment_id=assignment["id"])
    if not samples:
        st.caption("No samples yet.")
    else:
        for s in samples[:8]:
            with st.expander(f"{(s.get('title') or '(untitled)')} — {s['id'][:8]}"):
                st.json({"overall": s.get("overall"), "per_criterion": s.get("per_criterion")}, expanded=False)

        # --- Self-test the grader on a paper you already graded ---
    st.divider()
    st.subheader("Self-test the grader")

    test_col1, test_col2 = st.columns([2,1])
    test_essay = test_col1.file_uploader("Upload a student essay to test (PDF/DOCX/TXT)", type=["pdf","docx","txt"], key="selftest_essay")
    use_active = test_col2.checkbox("Use ACTIVE grader version (if any)", value=True, key="selftest_use_active")

    # Build rubric schema
    crits = list_rubric_criteria(rubric["id"])
    rubric_schema = {
        "title": rubric["title"],
        "scale": rubric["scale"],
        "criteria": [
            {"name": c["name"], "weight": float(c["weight"]), "descriptor_levels": c["descriptor_levels"]}
            for c in crits
        ],
    }

    # Collect anchors
    # Prefer active version’s chosen anchors; else use latest samples for this assignment
    anchors = []
    leniency_hint = assignment.get("leniency", 0.5)
    if use_active:
        active = get_active_grader_version(uid, rubric["id"])
        if active:
            leniency_hint = active.get("config", {}).get("leniency", leniency_hint)
            anchor_ids = active.get("config", {}).get("anchors", [])
            if anchor_ids:
                all_for_asn = list_grading_samples(uid, rubric_id=rubric["id"], assignment_id=assignment["id"])
                by_id = {s["id"]: s for s in all_for_asn}
                anchors = [by_id[aid] for aid in anchor_ids if aid in by_id]

    if not anchors:
        anchors = list_grading_samples(uid, rubric_id=rubric["id"], assignment_id=assignment["id"])[:6]

    # Optional: let teacher key in *their* true scores to compare (no JSON)
    with st.expander("Enter your true scores (optional) to compare"):
        teacher_overall = st.number_input(f"Your overall ({rubric['scale']})", min_value=0.0, max_value=100.0, value=0.0, step=0.5, key="selftest_teacher_overall")
        teacher_scores = {}
        for i, c in enumerate(rubric_schema["criteria"]):
            teacher_scores[c["name"]] = st.number_input(
                f"{c['name']}",
                min_value=0.0, max_value=100.0, value=0.0, step=0.5,
                key=f"selftest_teacher_{i}"
            )

    if st.button("Run self-test", key="selftest_run_btn"):
        if not test_essay:
            st.warning("Upload an essay to test.")
        else:
            essay_text = _read_uploaded_text(test_essay)
            with st.spinner("Grading with your rubric and anchors…"):
                # Convert anchors to the minimal structure expected by grade_with_rubric
                anchor_min = [{"text": a.get("text") or "", "overall": a.get("overall"), "per_criterion": a.get("per_criterion")} for a in anchors]
                pred = grade_with_rubric(essay_text, rubric_schema, anchors=anchor_min, leniency=leniency_hint)

            # Show prediction
            st.markdown("**Predicted grade**")
            st.json(pred, expanded=False)

            # If the teacher entered their true scores, compare
            if any(v != 0.0 for v in teacher_scores.values()) or teacher_overall != 0.0:
                import math
                rows = []
                abs_diffs = []
                for c in rubric_schema["criteria"]:
                    name = c["name"]
                    ai = pred["per_criterion"].get(name)
                    tr = teacher_scores.get(name)
                    if ai is None or tr is None:
                        delta = None
                    else:
                        delta = ai - tr
                        abs_diffs.append(abs(delta))
                    rows.append({"Criterion": name, "AI": ai, "Teacher": tr, "Δ (AI–Teacher)": delta})

                # Simple MAE on criteria that both provided
                mae = (sum(abs_diffs)/len(abs_diffs)) if abs_diffs else None
                o_ai = pred.get("overall")
                o_tr = teacher_overall if teacher_overall != 0.0 else None
                o_delta = (o_ai - o_tr) if (o_ai is not None and o_tr is not None) else None

                # Render compact comparison table
                st.markdown("**Comparison**")
                st.dataframe(rows, use_container_width=True)
                st.write(f"**Criterion MAE:** {mae:.2f}" if mae is not None else "**Criterion MAE:** n/a")
                st.write(f"**Overall Δ (AI–Teacher):** {o_delta:.2f}" if o_delta is not None else "**Overall Δ:** n/a")


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
