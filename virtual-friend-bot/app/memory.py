import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  user_id INTEGER PRIMARY KEY,
  persona TEXT DEFAULT 'friendly',
  mode TEXT DEFAULT 'friendly',
  name TEXT
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  role TEXT NOT NULL, -- 'user' | 'assistant' | 'system'
  content TEXT NOT NULL,
  ts INTEGER NOT NULL
);
"""

class Memory:
    def __init__(self, db_path="friend.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def ensure_user(self, user_id: int):
        cur = self.conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if not cur.fetchone():
            self.conn.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
            self.conn.commit()

    def get_user(self, user_id: int):
        self.ensure_user(user_id)
        cur = self.conn.execute("SELECT user_id, persona, mode, name FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return {"user_id": row[0], "persona": row[1], "mode": row[2], "name": row[3]}

    def set_persona(self, user_id: int, persona: str):
        self.ensure_user(user_id)
        self.conn.execute("UPDATE users SET persona = ? WHERE user_id = ?", (persona, user_id))
        self.conn.commit()

    def set_mode(self, user_id: int, mode: str):
        self.ensure_user(user_id)
        self.conn.execute("UPDATE users SET mode = ? WHERE user_id = ?", (mode, user_id))
        self.conn.commit()

    def set_name(self, user_id: int, name: str):
        self.ensure_user(user_id)
        self.conn.execute("UPDATE users SET name = ? WHERE user_id = ?", (name, user_id))
        self.conn.commit()

    def add_message(self, user_id: int, role: str, content: str):
        self.conn.execute(
            "INSERT INTO messages (user_id, role, content, ts) VALUES (?, ?, ?, ?)",
            (user_id, role, content, int(time.time()))
        )
        self.conn.commit()

    def get_history(self, user_id: int, limit: int = 20):
        cur = self.conn.execute(
            "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        )
        rows = cur.fetchall()
        # возвращаем в хронологическом порядке
        rows.reverse()
        return [{"role": r[0], "content": r[1]} for r in rows]

    def reset_dialog(self, user_id: int):
        self.conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        self.conn.commit()
