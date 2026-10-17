import os
from flask import Flask, jsonify, request
from supabase import create_client, Client

def create_app():
    app = Flask(__name__)

    # Supabase credentials from Environment Variables
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    # Initialize Supabase Client
    if supabase_url and supabase_key:
        app.supabase: Client = create_client(supabase_url, supabase_key)
    else:
        print("Warning: Supabase credentials are missing.")

    # Home route
    @app.route('/')
    def home():
        return "Hello! Render aur Supabase dono connected hain."

    # --- NAYA ROUTE: Students ka data dekhne ke liye ---
    @app.route('/students', methods=['GET'])
    def get_students():
        try:
            # Supabase se 'students' table ka data fetch karein
            response = app.supabase.table('students').select("*").execute()
            return jsonify(response.data), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app

# Gunicorn ke liye app ko expose karein
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
