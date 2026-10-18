import os
import psycopg2
import psycopg2.extras
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_conn():
    if not DATABASE_URL:
        raise Exception("❌ DATABASE_URL missing!")
    # Supabase requires sslmode for secure connection
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    print("✅ Connected to Supabase PostgreSQL")

def run(query, params=()):
    pg_query = query.replace("?", "%s")
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(pg_query, params)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

def all(query, params=()):
    pg_query = query.replace("?", "%s")
    conn = get_conn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute(pg_query, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()

def one(query, params=()):
    pg_query = query.replace("?", "%s")
    conn = get_conn()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute(pg_query, params)
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        cursor.close()
        conn.close()

def current_month():
    return datetime.now().strftime("%Y-%m")

def today():
    return datetime.now().strftime("%Y-%m-%d")
