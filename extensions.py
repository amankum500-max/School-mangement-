from flask_socketio import SocketIO
from supabase import create_client, Client
import google.generativeai as genai
from config import Config

socketio = SocketIO(cors_allowed_origins="*", async_mode='eventlet')

if Config.SUPABASE_URL and Config.SUPABASE_KEY:
    supabase: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
else:
    supabase = None

if Config.GEMINI_API_KEY:
    genai.configure(api_key=Config.GEMINI_API_KEY)
    ai_model = genai.GenerativeModel('gemini-1.5-flash')
else:
    ai_model = None
