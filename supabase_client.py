import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_KEY")

if not URL or not KEY:
    raise RuntimeError("❌ SUPABASE_URL aur SUPABASE_KEY .env me set karo")

supabase = create_client(URL, KEY)
