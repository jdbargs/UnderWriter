# src/db.py
from typing import Optional, List, Dict, Any
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
