import os
from flask import Flask, jsonify
from supabase import create_client, Client

def create_app():
    app = Flask(__name__)

    # Supabase क्रेडेंशियल्स को Render के Environment Variables से लोड करें
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    # Supabase क्लाइंट को ऐप के साथ इनिशियलाइज़ करें
    if supabase_url and supabase_key:
        app.supabase: Client = create_client(supabase_url, supabase_key)
    else:
        print("Warning: Supabase credentials are missing.")

    @app.route('/')
    def home():
        return "Hello! Render aur Supabase dono connected hain (Factory Pattern)."

    return app

# Gunicorn के लिए ऐप को एक्सपोज़ करें
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
app = create_app()  # ✅ पहले वेरिएबल बनाएँ

if __name__ == "__main__":
    app.run(debug=True)
