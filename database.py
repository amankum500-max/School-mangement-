import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date, datetime

# DATABASE_URL environment variable se aayega
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    # Render ke liye sslmode required hota hai
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    pass # Tables pehle hi Supabase mein ban chuke hain

def run(query, params=None):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def all(query, params=None):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(query, params)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

def one(query, params=None):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(query, params)
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

def today():
    return date.today().strftime('%Y-%m-%d')
