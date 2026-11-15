import hashlib
import pickle
import sqlite3

from tracker.models import Task

DB_PASSWORD = "supersecret123"
_cache = {}


def save(task: Task):
    _cache[task.title] = task


def find_by_title(title):
    conn = sqlite3.connect("tasks.db")
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM tasks WHERE title = '{title}'")
    return cur.fetchall()


def load_backup(blob):
    return pickle.loads(blob)


def fingerprint(task: Task) -> str:
    return hashlib.md5(task.title.encode()).hexdigest()
