import sqlite3
import os
import uuid
from datetime import datetime

DB_PATH = "chatbot.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Users table for Login
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')

    # 2. Sessions table for individual conversation threads
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            title TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    # 3. Chat History table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            session_id TEXT,
            model_name TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')

    # Migrate columns if existing database table lacks session_id or model_name
    cursor.execute("PRAGMA table_info(history)")
    existing_cols = [row[1] for row in cursor.fetchall()]
    if "session_id" not in existing_cols:
        cursor.execute("ALTER TABLE history ADD COLUMN session_id TEXT")
    if "model_name" not in existing_cols:
        cursor.execute("ALTER TABLE history ADD COLUMN model_name TEXT")

    # MIGRATION: Ensure no previous chat is lost! Group unassigned history into a legacy session.
    cursor.execute("SELECT DISTINCT user_id FROM history WHERE session_id IS NULL OR session_id = ''")
    unassigned_users = cursor.fetchall()
    for (u_id,) in unassigned_users:
        if u_id == "guest":
            continue
        cursor.execute(
            "SELECT content FROM history WHERE user_id = ? AND role = 'user' AND (session_id IS NULL OR session_id = '') ORDER BY timestamp ASC LIMIT 1", 
            (u_id,)
        )
        first_row = cursor.fetchone()
        sess_title = "Previous Conversation"
        if first_row and first_row[0]:
            prompt_preview = first_row[0].strip().replace("\n", " ")
            sess_title = (prompt_preview[:32] + "...") if len(prompt_preview) > 32 else prompt_preview

        migrated_session_id = f"sess_migrated_{u_id}"
        cursor.execute(
            "INSERT OR IGNORE INTO sessions (id, user_id, title, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (migrated_session_id, u_id, sess_title)
        )
        cursor.execute(
            "UPDATE history SET session_id = ? WHERE user_id = ? AND (session_id IS NULL OR session_id = '')",
            (migrated_session_id, u_id)
        )
    
    # Insert default admin user if it doesn't exist
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (username, password) VALUES ('admin', 'admin123')")
        
    conn.commit()
    conn.close()

def authenticate_user(username, password):
    if username.lower() == "guest":
        return "guest"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if user exists with the matching password
    cursor.execute("SELECT id FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    
    if not user:
        # Check if username exists at all (wrong password)
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        exists = cursor.fetchone()
        
        if not exists:
            # Username doesn't exist, auto-register the new user!
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            user = (cursor.lastrowid,)
        else:
            # Username exists but password was wrong
            user = None
            
    conn.close()
    return user[0] if user else None

# ----------------- Session Operations -----------------

def create_session(session_id, user_id, title):
    """Creates a new chat session thread in the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO sessions (id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        (session_id, user_id, title)
    )
    conn.commit()
    conn.close()
    return {"id": session_id, "user_id": user_id, "title": title}

def get_user_sessions(user_id):
    """Fetches all saved sessions for the given user, ordered newest first."""
    if user_id == "guest":
        return []
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, title, created_at, updated_at FROM sessions WHERE user_id = ? ORDER BY updated_at DESC", 
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": row[0], "title": row[1], "created_at": row[2], "updated_at": row[3]}
        for row in rows
    ]

def get_session(session_id):
    """Fetches a single session metadata by ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, title, created_at, updated_at FROM sessions WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "user_id": row[1], "title": row[2], "created_at": row[3], "updated_at": row[4]}
    return None

def rename_session(session_id, user_id, new_title):
    """Renames an existing session."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND (user_id = ? OR ? = 'admin')",
        (new_title, session_id, user_id, user_id)
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0

def delete_session(session_id, user_id):
    """Deletes a session and all its messages."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Delete associated messages
    cursor.execute("DELETE FROM history WHERE session_id = ?", (session_id,))
    # Delete session record
    cursor.execute("DELETE FROM sessions WHERE id = ? AND (user_id = ? OR ? = 'admin')", (session_id, user_id, user_id))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0

def get_session_messages(session_id):
    """Returns all messages belonging to a specific session in chronological order."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, role, content, timestamp, model_name FROM history WHERE session_id = ? ORDER BY timestamp ASC, id ASC",
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": row[0],
            "role": row[1],
            "content": row[2],
            "timestamp": row[3],
            "model_name": row[4]
        }
        for row in rows
    ]

def save_message(user_id, role, content, session_id=None, model_name=None):
    """
    Saves a chat message linked to a session. 
    Updates the session's updated_at timestamp.
    """
    if user_id == "guest":
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # If session_id provided, ensure session exists
    if session_id:
        cursor.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if not cursor.fetchone():
            prompt_preview = content.strip().replace("\n", " ")
            title = (prompt_preview[:32] + "...") if len(prompt_preview) > 32 else (prompt_preview or "New Conversation")
            cursor.execute(
                "INSERT INTO sessions (id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (session_id, user_id, title)
            )
        else:
            cursor.execute("UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))

    cursor.execute(
        "INSERT INTO history (user_id, role, content, session_id, model_name) VALUES (?, ?, ?, ?, ?)",
        (user_id, role, content, session_id, model_name)
    )
    msg_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return msg_id

def delete_bot_response_for_prompt(prompt_id, user_id):
    """
    Deletes the bot response that answered a given user prompt.
    Returns deleted_bot_id if found and deleted, else None.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, session_id, role FROM history WHERE id = ? AND (user_id = ? OR ? = 'admin')",
        (prompt_id, user_id, user_id)
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    _, session_id, role = row
    deleted_bot_id = None
    if role == 'user' and session_id:
        cursor.execute(
            "SELECT id FROM history WHERE session_id = ? AND role = 'user' AND id > ? ORDER BY id ASC LIMIT 1",
            (session_id, prompt_id)
        )
        next_user = cursor.fetchone()
        next_user_id = next_user[0] if next_user else None

        if next_user_id:
            cursor.execute(
                "SELECT id FROM history WHERE session_id = ? AND role = 'bot' AND id > ? AND id < ? ORDER BY id ASC LIMIT 1",
                (session_id, prompt_id, next_user_id)
            )
        else:
            cursor.execute(
                "SELECT id FROM history WHERE session_id = ? AND role = 'bot' AND id > ? ORDER BY id ASC LIMIT 1",
                (session_id, prompt_id)
            )
        bot_row = cursor.fetchone()
        if bot_row:
            deleted_bot_id = bot_row[0]
            cursor.execute("DELETE FROM history WHERE id = ?", (deleted_bot_id,))
            conn.commit()
    conn.close()
    return deleted_bot_id

def edit_message(message_id, user_id, new_content, remove_response=False):
    """
    Updates content of an existing message by ID.
    If remove_response is True and this message is a user prompt, deletes its old bot response.
    Returns (success, deleted_bot_id).
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE history SET content = ? WHERE id = ? AND (user_id = ? OR ? = 'admin')",
        (new_content, message_id, user_id, user_id)
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()

    deleted_bot_id = None
    if rows_affected > 0 and remove_response:
        deleted_bot_id = delete_bot_response_for_prompt(message_id, user_id)

    return rows_affected > 0, deleted_bot_id

def delete_message(message_id, user_id, include_response=True):
    """
    Deletes a single message by ID.
    If include_response is True and this message is a user prompt,
    its corresponding bot response is also deleted.
    Returns (success, deleted_bot_id).
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Look up message details
    cursor.execute(
        "SELECT id, session_id, role FROM history WHERE id = ? AND (user_id = ? OR ? = 'admin')",
        (message_id, user_id, user_id)
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, None

    _, session_id, role = row
    deleted_bot_id = None

    if include_response and role == 'user' and session_id:
        cursor.execute(
            "SELECT id FROM history WHERE session_id = ? AND role = 'user' AND id > ? ORDER BY id ASC LIMIT 1",
            (session_id, message_id)
        )
        next_user = cursor.fetchone()
        next_user_id = next_user[0] if next_user else None

        if next_user_id:
            cursor.execute(
                "SELECT id FROM history WHERE session_id = ? AND role = 'bot' AND id > ? AND id < ? ORDER BY id ASC LIMIT 1",
                (session_id, message_id, next_user_id)
            )
        else:
            cursor.execute(
                "SELECT id FROM history WHERE session_id = ? AND role = 'bot' AND id > ? ORDER BY id ASC LIMIT 1",
                (session_id, message_id)
            )
        bot_row = cursor.fetchone()
        if bot_row:
            deleted_bot_id = bot_row[0]
            cursor.execute("DELETE FROM history WHERE id = ?", (deleted_bot_id,))

    cursor.execute(
        "DELETE FROM history WHERE id = ? AND (user_id = ? OR ? = 'admin')",
        (message_id, user_id, user_id)
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0, deleted_bot_id

def get_history(user_id, session_id=None):
    """Fetches chat history for the user or a specific session."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if session_id:
        cursor.execute(
            "SELECT role, content, timestamp, model_name FROM history WHERE user_id = ? AND session_id = ? ORDER BY timestamp ASC", 
            (user_id, session_id)
        )
    else:
        cursor.execute(
            "SELECT role, content, timestamp, model_name FROM history WHERE user_id = ? ORDER BY timestamp ASC", 
            (user_id,)
        )
    history = cursor.fetchall()
    conn.close()
    return history
