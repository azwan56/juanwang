"""
SQLite Data storage for YuePaoQuan metrics and monthly goals.
Replaces MongoDB requirement for immediate out-of-the-box GCP deployment.
"""

import sqlite3
import logging
from datetime import datetime
import os

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'yuepaoquan.db')

class DatabaseConnector:
    def __init__(self):
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(DB_PATH)

    def _init_db(self):
        """Create tables if they don't exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Monthly Goals Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS monthly_goals (
                    user_id TEXT,
                    month TEXT,
                    target_km REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, month)
                )
            ''')
            # Running Records Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS running_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    month TEXT,
                    distance_km REAL,
                    duration TEXT,
                    pace TEXT,
                    avg_hr INTEGER,
                    msg_id TEXT UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            logger.info(f"[DB] SQLite Initialized at {DB_PATH}")

    def save_monthly_goal(self, user_id: str, month: str, target_km: float):
        """Upserts a monthly goal for a user."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO monthly_goals (user_id, month, target_km)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, month) DO UPDATE SET target_km=excluded.target_km, created_at=CURRENT_TIMESTAMP
            ''', (user_id, month, target_km))
            conn.commit()

    def get_monthly_goal(self, user_id: str, month: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT target_km FROM monthly_goals WHERE user_id=? AND month=?', (user_id, month))
            row = cursor.fetchone()
            return row[0] if row else None

    def save_activity(self, data: dict):
        """Saves a running record using normalized OCR data."""
        user_id = data.get("user_id")
        msg_id = data.get("msg_id", f"fake_{datetime.now().timestamp()}")
        # Derive month string e.g. "2026-04"
        month = datetime.now().strftime("%Y-%m")
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO running_records (user_id, month, distance_km, duration, pace, avg_hr, msg_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_id,
                    month,
                    float(data.get("distance_km") or 0),
                    data.get("duration", ""),
                    data.get("avg_pace", ""),
                    data.get("avg_hr", 0) or 0,
                    msg_id
                ))
                conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                logger.warning(f"[DB] Activity {msg_id} already exists, skipping insert.")
                return None

    def get_monthly_stats(self, user_id: str, month: str):
        """Calculate total distance for user in month."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT SUM(distance_km) FROM running_records WHERE user_id=? AND month=?
            ''', (user_id, month))
            row = cursor.fetchone()
            total_dist = row[0] if row and row[0] else 0.0
            
            target = self.get_monthly_goal(user_id, month)
            return {
                "total_km": round(total_dist, 2),
                "target_km": target,
                "progress_pct": round((total_dist / target * 100) if target else 0, 1),
                "remaining_km": round(max(0, target - total_dist), 2) if target else None
            }

    def get_leaderboard(self, month: str):
        """Fetch all user stats and merge them for a leaderboard."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Get totals
            cursor.execute('''
                SELECT user_id, SUM(distance_km) FROM running_records 
                WHERE month = ? GROUP BY user_id
            ''', (month,))
            totals = {row[0]: row[1] or 0.0 for row in cursor.fetchall()}
            
            # Get goals
            cursor.execute('''
                SELECT user_id, target_km FROM monthly_goals 
                WHERE month = ?
            ''', (month,))
            goals = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Merge
            users = set(totals.keys()) | set(goals.keys())
            results = []
            for uid in users:
                total = totals.get(uid, 0.0)
                target = goals.get(uid)
                results.append({
                    "user_id": uid,
                    "total_km": round(total, 2),
                    "target_km": target,
                    "progress_pct": round((total / target * 100) if target else 0, 1),
                    "remaining_km": round(max(0, target - total), 2) if target else None
                })
                
            # Sort by total_km descending
            return sorted(results, key=lambda x: x["total_km"], reverse=True)
