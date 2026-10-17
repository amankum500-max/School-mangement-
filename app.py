import os
from flask import Flask, jsonify
from supabase import create_client, Client

app = Flask(__name__)

# Render ke Environment Variables se keys aayengi
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Supabase connection error: {e}")

@app.route('/')
def home():
    return "Hello! Render aur Supabase dono connected hain."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
