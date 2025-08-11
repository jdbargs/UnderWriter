from supabase import create_client, Client
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

# App client: use anon key so RLS + user JWT applies
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
