# src/db.py
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
import random

from .supabase_client import supabase

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
def random_flow_prompt(tag: Optional[str] = None, difficulty: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    Fetch up to 50 recent prompts (optionally filtered) and return one at random.
    For proper weighting/randomness, consider a server-side RPC later.
    """
    q = supabase.table("flow_prompts").select("*")
    if tag:
        q = q.eq("tag", tag)
    if difficulty:
        q = q.eq("difficulty", difficulty)
    res = q.order("created_at", desc=True).limit(50).execute()
    rows = res.data or []
    return random.choice(rows) if rows else None

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
