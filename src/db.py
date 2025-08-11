from typing import Optional, List, Dict, Any
from .supabase_client import supabase

def sign_up(email: str, password: str):
    # returns { user, session } or raises
    return supabase.auth.sign_up({"email": email, "password": password})

def sign_in(email: str, password: str):
    # returns { user, session } or raises
    return supabase.auth.sign_in_with_password({"email": email, "password": password})

def get_current_user():
    return supabase.auth.get_user()

def sign_out():
    supabase.auth.sign_out()

def save_writing(user_id: str, text: str, title: Optional[str] = None, metadata: Optional[dict] = None):
    data = {"user_id": user_id, "text": text, "title": title, "metadata": metadata or {}}
    return supabase.table("writings").insert(data).execute()

def list_writings(user_id: str) -> List[Dict[str, Any]]:
    res = (
        supabase.table("writings")
        .select("id, title, text, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []
