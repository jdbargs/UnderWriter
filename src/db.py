# src/db.py
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone

from .supabase_client import supabase

# ---------- FlowState Defaults ----------
# Fill these with your 10 strong defaults (plain strings).
DEFAULT_FLOW_PROMPTS = [
    "Write only the very beginning of a long novel.",
    "Describe every detail about the present moment you can muster.",
    "Take the perspective of an object you can currently see, as if it were alive.",
    "Recount a dream you can remember.",
    "Make an argument about something that bothers you.",
    "Imagine a place without naming or knowing it. Describe what you see.",
    "Retell and embellish a recent dialogue you heard.",
    "Consider a ridiculous idea with seriousness and sincerity.",
    "Pretend you are an astronaut floating in space.",
    "Write exclusively in rhyme."
]

def get_default_flow_prompts() -> List[Dict[str, Any]]:
    """Return defaults shaped like DB rows, so callers can treat them the same."""
    return [{"id": None, "text": p, "source": "default"} for p in DEFAULT_FLOW_PROMPTS]


# ---------- Auth ----------
def sign_up(email: str, password: str):
    return supabase.auth.sign_up({"email": email, "password": password})

def sign_in(email: str, password: str):
    return supabase.auth.sign_in_with_password({"email": email, "password": password})

def get_current_user():
    return supabase.auth.get_user()

def set_session(access_token: str, refresh_token: str):
    # Restore a session into the client (for Streamlit reruns)
    return supabase.auth.set_session(access_token, refresh_token)

def sign_out():
    supabase.auth.sign_out()

# ---------- Writings ----------
def save_writing(user_id: str, text: str, title: Optional[str] = None, metadata: Optional[dict] = None) -> Dict[str, Any]:
    data = {"user_id": user_id, "text": text, "title": title, "metadata": metadata or {}}
    res = supabase.table("writings").insert(data).execute()
    return (res.data or [None])[0]

def list_writings(user_id: str) -> List[Dict[str, Any]]:
    res = (
        supabase.table("writings")
        .select("id, title, text, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []

def get_writing(writing_id: str) -> Optional[Dict[str, Any]]:
    res = supabase.table("writings").select("*").eq("id", writing_id).single().execute()
    return res.data

def count_writings(user_id: str) -> int:
    res = supabase.table("writings").select("id", count="exact").eq("user_id", user_id).execute()
    return res.count or 0

# ---------- Writing Insights ----------
def insert_writing_insight(
    writing_id: str,
    intention: Optional[str],
    tone: Optional[str],
    energy: Optional[str],
    observations: Optional[str],
    micro_suggestions: Optional[List[dict]],
    metrics: Optional[dict],
):
    payload = {
        "writing_id": writing_id,
        "intention": intention,
        "tone": tone,
        "energy": energy,
        "observations": observations,
        "micro_suggestions": micro_suggestions or [],
        "metrics": metrics or {},
    }
    return supabase.table("writing_insights").insert(payload).execute()

def get_writing_insights(writing_id: str) -> List[Dict[str, Any]]:
    res = (
        supabase.table("writing_insights")
        .select("*")
        .eq("writing_id", writing_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []

# ---------- Companion Feedback ----------
def insert_companion_feedback(writing_id: str, feedback: str, mode: str = "spotlight"):
    payload = {"writing_id": writing_id, "feedback": feedback, "mode": mode}
    return supabase.table("companion_feedback").insert(payload).execute()

def get_companion_feedback(writing_id: str) -> List[Dict[str, Any]]:
    res = (
        supabase.table("companion_feedback")
        .select("*")
        .eq("writing_id", writing_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []

# ---------- Style Profile / Snapshots ----------
def upsert_style_profile(user_id: str, summary: str, traits: Optional[dict] = None):
    payload = {"user_id": user_id, "summary": summary, "traits": traits or {}}
    return supabase.table("style_profiles").upsert(payload).execute()

def get_style_profile(user_id: str) -> Optional[Dict[str, Any]]:
    res = supabase.table("style_profiles").select("*").eq("user_id", user_id).single().execute()
    return res.data

def insert_style_snapshot(user_id: str, snapshot: str, signals: Optional[dict] = None):
    payload = {"user_id": user_id, "snapshot": snapshot, "signals": signals or {}}
    return supabase.table("style_snapshots").insert(payload).execute()

def list_style_snapshots(user_id: str) -> List[Dict[str, Any]]:
    res = (
        supabase.table("style_snapshots")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []

# ==========================================================
# ================== FlowState (Practice) ==================
# ==========================================================

# ---------- Prompts ----------
import random

def random_flow_prompt(
    tag: Optional[str] = None,
    difficulty: Optional[int] = None,
    include_defaults: bool = True  # <-- NEW: include your hardcoded defaults by default
) -> Optional[Dict[str, Any]]:
    """
    Pick a random FlowState prompt.
    - Pulls up to 50 active prompts from Supabase (optionally filtered by tag/difficulty).
    - If include_defaults=True, mixes in your hardcoded defaults even when the DB has rows.
    """
    q = supabase.table("flow_prompts").select("*")

    if tag is not None:
        q = q.eq("tag", tag)
    if difficulty is not None:
        q = q.eq("difficulty", difficulty)

    # Prefer active prompts if column exists
    try:
        q = q.eq("active", True)
    except Exception:
        pass

    res = q.order("created_at", desc=True).limit(50).execute()
    rows = res.data or []

    pool = rows[:]  # DB prompts
    if include_defaults:
        pool += get_default_flow_prompts()  # your 10 defaults

    if not pool:
        return None

    return random.choice(pool)

def list_all_flow_prompts(include_defaults: bool = True) -> List[Dict[str, Any]]:
    res = supabase.table("flow_prompts").select("*").order("created_at", desc=True).limit(200).execute()
    rows = res.data or []
    return (rows + get_default_flow_prompts()) if include_defaults else rows


# ---------- Sessions ----------
def create_flow_session(
    user_id: str,
    mode: str,
    duration_seconds: Optional[int],
    target_words: Optional[int],
    goal_focus: Optional[List[str]],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "user_id": user_id,
        "mode": mode,
        "duration_seconds": duration_seconds,
        "target_words": target_words,
        "goal_focus": goal_focus,
    }
    res = supabase.table("flow_sessions").insert(payload).execute()
    return (res.data or [None])[0]

# ---------- Attempts ----------
def insert_flow_attempt(
    session_id: str,
    prompt_id: Optional[str],
    user_id: str,
    response_text: str,
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "session_id": session_id,
        "prompt_id": prompt_id,
        "user_id": user_id,
        "response_text": response_text,
        "start_time": (start_time or datetime.now(timezone.utc)).isoformat(),
        "end_time": (end_time or datetime.now(timezone.utc)).isoformat(),
        "meta": meta or {},
    }
    res = supabase.table("flow_attempts").insert(payload).execute()
    return (res.data or [None])[0]

# ---------- Metrics ----------
def insert_flow_metrics(
    attempt_id: str,
    user_id: str,
    metrics: Dict[str, Any],
) -> Dict[str, Any]:
    payload = {"attempt_id": attempt_id, "user_id": user_id, **metrics}
    res = supabase.table("flow_metrics").insert(payload).execute()
    return (res.data or [None])[0]

def list_flow_recent_metrics(user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    res = (
        supabase.table("flow_metrics")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []

def user_metric_baseline(user_id: str, metric_field: str, days: int = 7) -> Optional[float]:
    """
    Rolling average for a metric over the past N days.
    Returns None if not enough data.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    res = (
        supabase.table("flow_metrics")
        .select(f"{metric_field}, created_at")
        .eq("user_id", user_id)
        .gte("created_at", since)
        .order("created_at", desc=True)
        .limit(200)
        .execute()
    )
    rows = res.data or []
    vals = [r.get(metric_field) for r in rows if r.get(metric_field) is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)

# ---------- Feedback ----------
def insert_flow_feedback(
    attempt_id: str,
    user_id: str,
    feedback_text: str,
) -> Dict[str, Any]:
    payload = {"attempt_id": attempt_id, "user_id": user_id, "feedback": feedback_text}
    res = supabase.table("flow_feedback").insert(payload).execute()
    return (res.data or [None])[0]

# ---------- Goals & Progress ----------
def upsert_flow_goal(user_id: str, focus: str, target: float, window_days: int = 14, active: bool = True) -> Dict[str, Any]:
    """
    Emulate upsert by (user_id, focus, active=True). If one exists, update; else insert.
    """
    existing = (
        supabase.table("flow_goals")
        .select("*")
        .eq("user_id", user_id)
        .eq("focus", focus)
        .eq("active", True)
        .limit(1)
        .execute()
        .data
    )
    if existing:
        goal_id = existing[0]["id"]
        res = (
            supabase.table("flow_goals")
            .update({"target": target, "window_days": window_days, "active": active})
            .eq("id", goal_id)
            .execute()
        )
        return (res.data or [None])[0]
    else:
        payload = {"user_id": user_id, "focus": focus, "target": target, "window_days": window_days, "active": active}
        res = supabase.table("flow_goals").insert(payload).execute()
        return (res.data or [None])[0]

def active_flow_goals(user_id: str) -> List[Dict[str, Any]]:
    res = (
        supabase.table("flow_goals")
        .select("*")
        .eq("user_id", user_id)
        .eq("active", True)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []

def insert_flow_progress(goal_id: str, attempt_id: str, metric_value: float, delta: float) -> Dict[str, Any]:
    payload = {"goal_id": goal_id, "attempt_id": attempt_id, "metric_value": metric_value, "delta": delta}
    res = supabase.table("flow_progress").insert(payload).execute()
    return (res.data or [None])[0]

# ---------- Flow Prompts (teacher-owned) ----------
def create_flow_prompt(teacher_id: str, text: str, tags: Optional[List[str]] = None,
                       level: Optional[str] = None, active: bool = True) -> Dict[str, Any]:
    payload = {
        "teacher_id": teacher_id,
        "text": text,
        "tags": tags or [],
        "level": level,
        "active": active,
    }
    res = supabase.table("flow_prompts").insert(payload).execute()
    return (res.data or [None])[0]

def list_flow_prompts_for_teacher(teacher_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
    q = supabase.table("flow_prompts").select("*").eq("teacher_id", teacher_id)
    if active_only:
        q = q.eq("active", True)
    q = q.order("created_at", desc=True)
    res = q.execute()
    return res.data or []

def set_flow_prompt_active(prompt_id: str, active: bool) -> None:
    supabase.table("flow_prompts").update({"active": active}).eq("id", prompt_id).execute()

# ---------- Prompt ↔ Assignment linking ----------
def assign_prompts_to_assignment(assignment_id: str, prompt_ids: List[str]) -> None:
    if not prompt_ids:
        return
    rows = [{"assignment_id": assignment_id, "prompt_id": pid} for pid in prompt_ids]
    supabase.table("flow_prompt_assignments").upsert(rows, on_conflict="assignment_id,prompt_id").execute()

def remove_prompt_from_assignment(assignment_id: str, prompt_id: str) -> None:
    supabase.table("flow_prompt_assignments").delete().eq("assignment_id", assignment_id).eq("prompt_id", prompt_id).execute()

def list_prompts_for_assignment(assignment_id: str) -> List[Dict[str, Any]]:
    # join flow_prompt_assignments -> flow_prompts
    res = (
        supabase.table("flow_prompt_assignments")
        .select("id, sort, flow_prompts(id, text, tags, level, active, teacher_id)")
        .eq("assignment_id", assignment_id)
        .order("sort", desc=False)
        .execute()
    )
    rows = res.data or []
    # Flatten
    out = []
    for r in rows:
        p = r.get("flow_prompts") or {}
        p["link_id"] = r["id"]
        p["sort"] = r.get("sort")
        out.append(p)
    return out

def random_assigned_prompt(assignment_id: str) -> Optional[Dict[str, Any]]:
    rows = list_prompts_for_assignment(assignment_id)
    rows = [r for r in rows if r.get("active", True)]
    if not rows:
        return None
    import random
    return random.choice(rows)

# --- Profiles / Roles ---
def get_profile(user_id: str):
    res = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
    return res.data

def upsert_profile(user_id: str, display_name: str = None, school: str = None, role: str = None):
    payload = {"id": user_id}
    if display_name is not None: payload["display_name"] = display_name
    if school is not None: payload["school"] = school
    if role is not None: payload["role"] = role
    res = supabase.table("profiles").upsert(payload).execute()
    return (res.data or [None])[0]

def is_teacher(user_id: str) -> bool:
    p = get_profile(user_id)
    return bool(p and p.get("role") in ("teacher","admin"))

# ====== GradeSim: Rubrics, Criteria, Samples, Grader Versions, Requests/Results ======

# ---------- Rubrics ----------
def create_rubric(teacher_id: str, title: str, subject: Optional[str] = None,
                  grade_level: Optional[str] = None, scale: str = "0-4") -> Dict[str, Any]:
    payload = {
        "teacher_id": teacher_id,
        "title": title,
        "subject": subject,
        "grade_level": grade_level,
        "scale": scale,
    }
    res = supabase.table("rubrics").insert(payload).execute()
    return (res.data or [None])[0]

def list_rubrics(teacher_id: str) -> List[Dict[str, Any]]:
    res = (
        supabase.table("rubrics")
        .select("*")
        .eq("teacher_id", teacher_id)
        .eq("archived", False)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []

def get_rubric(rubric_id: str) -> Optional[Dict[str, Any]]:
    res = supabase.table("rubrics").select("*").eq("id", rubric_id).single().execute()
    return res.data

def archive_rubric(rubric_id: str, archived: bool = True) -> Optional[Dict[str, Any]]:
    res = supabase.table("rubrics").update({"archived": archived}).eq("id", rubric_id).execute()
    return (res.data or [None])[0]

# ---------- Rubric Criteria ----------
def add_rubric_criterion(rubric_id: str, name: str, descriptor_levels: Dict[str, str],
                         weight: float = 0.25) -> Dict[str, Any]:
    payload = {
        "rubric_id": rubric_id,
        "name": name,
        "descriptor_levels": descriptor_levels,
        "weight": weight,
    }
    res = supabase.table("rubric_criteria").insert(payload).execute()
    return (res.data or [None])[0]

def list_rubric_criteria(rubric_id: str) -> List[Dict[str, Any]]:
    res = (
        supabase.table("rubric_criteria")
        .select("*")
        .eq("rubric_id", rubric_id)
        .execute()
    )
    return res.data or []

def update_rubric_criterion(criterion_id: str, name: Optional[str] = None,
                            descriptor_levels: Optional[Dict[str, str]] = None,
                            weight: Optional[float] = None) -> Optional[Dict[str, Any]]:
    patch: Dict[str, Any] = {}
    if name is not None: patch["name"] = name
    if descriptor_levels is not None: patch["descriptor_levels"] = descriptor_levels
    if weight is not None: patch["weight"] = weight
    if not patch:
        return get_rubric_criterion(criterion_id)
    res = supabase.table("rubric_criteria").update(patch).eq("id", criterion_id).execute()
    return (res.data or [None])[0]

def get_rubric_criterion(criterion_id: str) -> Optional[Dict[str, Any]]:
    res = supabase.table("rubric_criteria").select("*").eq("id", criterion_id).single().execute()
    return res.data

def delete_rubric_criterion(criterion_id: str) -> None:
    supabase.table("rubric_criteria").delete().eq("id", criterion_id).execute()

# ---------- Teacher Grading Samples (anchors) ----------
def add_grading_sample(teacher_id: str, rubric_id: str, title: Optional[str],
                       text: str, overall: Optional[float],
                       per_criterion: Optional[Dict[str, Any]],
                       rationales: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = {
        "teacher_id": teacher_id,
        "rubric_id": rubric_id,
        "title": title,
        "text": text,
        "overall": overall,
        "per_criterion": per_criterion or {},
        "rationales": rationales or {},
    }
    res = supabase.table("grading_samples").insert(payload).execute()
    return (res.data or [None])[0]

def list_grading_samples(teacher_id: str, rubric_id: Optional[str] = None,
                         limit: int = 50) -> List[Dict[str, Any]]:
    q = (
        supabase.table("grading_samples")
        .select("*")
        .eq("teacher_id", teacher_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if rubric_id:
        q = q.eq("rubric_id", rubric_id)
    res = q.execute()
    return res.data or []

def get_grading_sample(sample_id: str) -> Optional[Dict[str, Any]]:
    res = supabase.table("grading_samples").select("*").eq("id", sample_id).single().execute()
    return res.data

def delete_grading_sample(sample_id: str) -> None:
    supabase.table("grading_samples").delete().eq("id", sample_id).execute()

# ---------- Grader Versions ----------
def _next_grader_version_number(teacher_id: str, rubric_id: str) -> int:
    res = (
        supabase.table("teacher_grader_versions")
        .select("version")
        .eq("teacher_id", teacher_id)
        .eq("rubric_id", rubric_id)
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    if res.data:
        return int(res.data[0]["version"]) + 1
    return 1

def create_grader_version(teacher_id: str, rubric_id: str, config: Dict[str, Any],
                          method: str = "few_shot_prompt", train_stats: Optional[Dict[str, Any]] = None,
                          is_active: bool = False, version: Optional[int] = None) -> Dict[str, Any]:
    ver = version or _next_grader_version_number(teacher_id, rubric_id)
    payload = {
        "teacher_id": teacher_id,
        "rubric_id": rubric_id,
        "version": ver,
        "method": method,
        "config": config or {},
        "train_stats": train_stats,
        "is_active": is_active,
    }
    res = supabase.table("teacher_grader_versions").insert(payload).execute()
    return (res.data or [None])[0]

def set_active_grader_version(teacher_id: str, rubric_id: str, version_id: str) -> None:
    # Deactivate all versions for that rubric/teacher
    supabase.table("teacher_grader_versions").update({"is_active": False}).eq("teacher_id", teacher_id).eq("rubric_id", rubric_id).execute()
    # Activate the chosen one
    supabase.table("teacher_grader_versions").update({"is_active": True}).eq("id", version_id).execute()

def list_grader_versions(teacher_id: str, rubric_id: str) -> List[Dict[str, Any]]:
    res = (
        supabase.table("teacher_grader_versions")
        .select("*")
        .eq("teacher_id", teacher_id)
        .eq("rubric_id", rubric_id)
        .order("version", desc=True)
        .execute()
    )
    return res.data or []

def get_active_grader_version(teacher_id: str, rubric_id: str) -> Optional[Dict[str, Any]]:
    res = (
        supabase.table("teacher_grader_versions")
        .select("*")
        .eq("teacher_id", teacher_id)
        .eq("rubric_id", rubric_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    return (res.data or [None])[0]

# ---------- Grade Requests / Results ----------
def create_grade_request(student_id: str, teacher_id: str, rubric_id: str,
                         writing_id: Optional[str] = None, text: Optional[str] = None) -> Dict[str, Any]:
    payload = {
        "student_id": student_id,
        "teacher_id": teacher_id,
        "rubric_id": rubric_id,
        "writing_id": writing_id,
        "text": text,
        "status": "queued",
    }
    res = supabase.table("grade_requests").insert(payload).execute()
    return (res.data or [None])[0]

def mark_grade_request_status(request_id: str, status: str) -> None:
    assert status in ("queued", "graded", "error")
    supabase.table("grade_requests").update({"status": status}).eq("id", request_id).execute()

def insert_grade_result(request_id: str, overall: float, per_criterion: Dict[str, Any],
                        rationales: Dict[str, Any], confidence: str,
                        model_version_id: Optional[str] = None,
                        tokens_used: Optional[int] = None, latency_ms: Optional[int] = None) -> Dict[str, Any]:
    payload = {
        "request_id": request_id,
        "overall": overall,
        "per_criterion": per_criterion,
        "rationales": rationales,
        "confidence": confidence,
        "model_version_id": model_version_id,
        "tokens_used": tokens_used,
        "latency_ms": latency_ms,
    }
    res = supabase.table("grade_results").insert(payload).execute()
    return (res.data or [None])[0]

def get_grade_result_by_request(request_id: str) -> Optional[Dict[str, Any]]:
    res = supabase.table("grade_results").select("*").eq("request_id", request_id).single().execute()
    return res.data

def list_grade_requests_for_teacher(teacher_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    res = (
        supabase.table("grade_requests")
        .select("*")
        .eq("teacher_id", teacher_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []

def list_grade_requests_for_student(student_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    res = (
        supabase.table("grade_requests")
        .select("*")
        .eq("student_id", student_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []

# ---------- Assignments ----------
def create_assignment(teacher_id: str, rubric_id: str, title: str,
                      period: Optional[str] = None, due_date: Optional[str] = None,
                      leniency: float = 0.5) -> Dict[str, Any]:
    payload = {
        "teacher_id": teacher_id,
        "rubric_id": rubric_id,
        "title": title,
        "period": period,
        "due_date": due_date,
        "leniency": leniency,
    }
    res = supabase.table("assignments").insert(payload).execute()
    return (res.data or [None])[0]

def list_assignments(teacher_id: str, rubric_id: Optional[str] = None) -> List[Dict[str, Any]]:
    q = (supabase.table("assignments").select("*").eq("teacher_id", teacher_id)
         .order("created_at", desc=True))
    if rubric_id:
        q = q.eq("rubric_id", rubric_id)
    res = q.execute()
    return res.data or []

def get_assignment(assignment_id: str) -> Optional[Dict[str, Any]]:
    res = supabase.table("assignments").select("*").eq("id", assignment_id).single().execute()
    return res.data

def update_assignment(assignment_id: str, **patch) -> Optional[Dict[str, Any]]:
    if not patch:
        return get_assignment(assignment_id)
    res = supabase.table("assignments").update(patch).eq("id", assignment_id).execute()
    return (res.data or [None])[0]

def delete_assignment(assignment_id: str) -> None:
    supabase.table("assignments").delete().eq("id", assignment_id).execute()

# ---------- Grading Samples (updated to include assignment_id) ----------
def add_grading_sample(teacher_id: str, rubric_id: str, assignment_id: str,
                       title: Optional[str], text: str, overall: Optional[float],
                       per_criterion: Optional[Dict[str, Any]],
                       rationales: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = {
        "teacher_id": teacher_id,
        "rubric_id": rubric_id,
        "assignment_id": assignment_id,
        "title": title,
        "text": text,
        "overall": overall,
        "per_criterion": per_criterion or {},
        "rationales": rationales or {},
    }
    res = supabase.table("grading_samples").insert(payload).execute()
    return (res.data or [None])[0]

def list_grading_samples(teacher_id: str, rubric_id: Optional[str] = None,
                         assignment_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    q = (supabase.table("grading_samples").select("*").eq("teacher_id", teacher_id)
         .order("created_at", desc=True).limit(limit))
    if rubric_id:
        q = q.eq("rubric_id", rubric_id)
    if assignment_id:
        q = q.eq("assignment_id", assignment_id)
    res = q.execute()
    return res.data or []

# =========================
# === Activity Logging  ===
# =========================

def log_activity(user_id: str, event_type: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Append a single event to user_activity_log.
    event_type examples:
      'writing_submitted', 'flow_burst_submitted', 'gradesim_selftest_run',
      'rubric_created', 'assignment_created', 'gradesim_anchor_added'
    """
    rec = {
        "user_id": user_id,
        "event_type": event_type,
        "event_payload": payload or {},
    }
    res = supabase.table("user_activity_log").insert(rec).execute()
    return (res.data or [None])[0]

def list_activity(user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    res = (
        supabase.table("user_activity_log")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []

def activity_streak_days(user_id: str) -> int:
    """
    Simple daily streak from user_activity_log.
    Counts consecutive days (including today) with >=1 event.
    """
    # Pull last 60 days of events
    since = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    res = (
        supabase.table("user_activity_log")
        .select("created_at")
        .eq("user_id", user_id)
        .gte("created_at", since)
        .order("created_at", desc=True)
        .limit(1000)
        .execute()
    )
    rows = res.data or []
    if not rows:
        return 0

    # Build set of date strings in local UTC-day (naive)
    days = set(r["created_at"][:10] for r in rows)  # 'YYYY-MM-DD'
    today = datetime.now(timezone.utc).date()
    streak = 0
    d = today
    while d.strftime("%Y-%m-%d") in days:
        streak += 1
        d = d - timedelta(days=1)
    return streak

# =========================
# === Quick Aggregates  ===
# =========================

def count_flow_attempts(user_id: str) -> int:
    res = supabase.table("flow_attempts").select("id", count="exact").eq("user_id", user_id).execute()
    return res.count or 0

def count_flow_sessions(user_id: str) -> int:
    res = supabase.table("flow_sessions").select("id", count="exact").eq("user_id", user_id).execute()
    return res.count or 0

def count_gradesim_selftests(user_id: str) -> int:
    # We log self-tests into user_activity_log with event_type='gradesim_selftest_run'
    res = (
        supabase.table("user_activity_log")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("event_type", "gradesim_selftest_run")
        .execute()
    )
    return res.count or 0

def get_user_overview(user_id: str) -> Dict[str, Any]:
    """
    One-shot “omniscient” snapshot the AI can use before giving feedback.
    Extend as needed.
    """
    try:
        return {
            "writings_count": count_writings(user_id),
            "flow_sessions_count": count_flow_sessions(user_id),
            "flow_attempts_count": count_flow_attempts(user_id),
            "gradesim_selftests_count": count_gradesim_selftests(user_id),
            "streak_days": activity_streak_days(user_id),
        }
    except Exception:
        # Never block feedback if an aggregate fails
        return {}

def get_user_context_pack(user_id: str, k_recent: int = 5) -> Dict[str, Any]:
    """A compact, always-available bundle the AI can read before responding."""
    from typing import cast
    # counts & streak
    overview = get_user_overview(user_id)
    # recent writings (ids + short excerpts)
    w = (
        supabase.table("writings")
        .select("id, created_at, title, text")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(k_recent)
        .execute()
        .data or []
    )
    recent_samples = []
    for row in w:
        txt = (row.get("text") or "").strip()
        if len(txt) > 400: txt = txt[:400] + "…"
        recent_samples.append({"id": row["id"], "title": row.get("title"), "excerpt": txt})

    # latest style profile & traits if present
    profile = get_style_profile(user_id) or {}
    # recent micro-signals from FlowState
    fm = list_flow_recent_metrics(user_id, limit=10)
    goals = [g.get("focus") for g in (active_flow_goals(user_id) or [])]

    return {
        "overview": overview,                      # counts, streak
        "style_profile": {
            "summary": profile.get("summary"),
            "traits": profile.get("traits") or {},
            "last_updated": profile.get("last_updated"),
        },
        "recent_samples": recent_samples,          # last few excerpts
        "flow_metrics_recent": fm,                 # last N attempts metrics
        "active_goals": goals,                     # playfulness/clarity/creativity
    }
