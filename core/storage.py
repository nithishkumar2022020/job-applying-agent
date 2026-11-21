"""
Database and Application Tracking Store.
Handles SQLite persistence for job history, rate limiting tracking, and semantic Q&A caching.
"""

import hashlib
import os
import re
import sqlite3
from datetime import datetime, date
from typing import Optional, Dict, Any, List


class ApplicationStore:
    def __init__(self, db_path: str = "data/applications.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Applications tracker table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    job_id TEXT,
                    job_title TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    job_url TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT
                )
            """)

            # Semantic Q&A Cache table (avoids repeated LLM calls for identical/similar questions)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS qa_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    normalized_key TEXT UNIQUE NOT NULL,
                    raw_question TEXT NOT NULL,
                    answer_text TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    @staticmethod
    def normalize_question(question: str) -> str:
        """Strip punctuation, whitespace, and lowercase for cache keying."""
        cleaned = re.sub(r'[^a-zA-Z0-9\s]', '', question.lower())
        return " ".join(cleaned.split())

    def get_cached_answer(self, question: str) -> Optional[Dict[str, str]]:
        key = self.normalize_question(question)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT answer_text, provider FROM qa_cache WHERE normalized_key = ?",
                (key,)
            )
            row = cursor.fetchone()
            if row:
                return {"answer": row["answer_text"], "provider": row["provider"]}
        return None

    def save_cached_answer(self, question: str, answer: str, provider: str):
        key = self.normalize_question(question)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO qa_cache (normalized_key, raw_question, answer_text, provider)
                VALUES (?, ?, ?, ?)
                """,
                (key, question.strip(), answer.strip(), provider)
            )
            conn.commit()

    def has_applied(self, job_url: str, job_id: Optional[str] = None) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if job_id:
                cursor.execute(
                    "SELECT 1 FROM applications WHERE job_id = ? OR job_url = ?",
                    (job_id, job_url)
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM applications WHERE job_url = ?",
                    (job_url,)
                )
            return cursor.fetchone() is not None

    def log_application(
        self,
        platform: str,
        job_title: str,
        company_name: str,
        job_url: str,
        status: str,
        mode: str,
        job_id: Optional[str] = None,
        notes: str = ""
    ) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO applications 
                (platform, job_id, job_title, company_name, job_url, status, mode, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (platform, job_id, job_title, company_name, job_url, status, mode, notes)
            )
            conn.commit()
            return cursor.lastrowid

    def get_today_application_count(self) -> int:
        today_str = date.today().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) as count 
                FROM applications 
                WHERE date(created_at) = date('now') 
                AND status IN ('SUBMITTED', 'AUTOFILLED_PENDING_REVIEW')
                """
            )
            row = cursor.fetchone()
            return row["count"] if row else 0

    def get_stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM applications")
            total = cursor.fetchone()["total"]

            cursor.execute("SELECT status, COUNT(*) as count FROM applications GROUP BY status")
            status_breakdown = {row["status"]: row["count"] for row in cursor.fetchall()}

            cursor.execute("SELECT platform, COUNT(*) as count FROM applications GROUP BY platform")
            platform_breakdown = {row["platform"]: row["count"] for row in cursor.fetchall()}

            cursor.execute("SELECT COUNT(*) as cached_answers FROM qa_cache")
            cached_answers = cursor.fetchone()["cached_answers"]

            return {
                "total_processed": total,
                "today_count": self.get_today_application_count(),
                "status_breakdown": status_breakdown,
                "platform_breakdown": platform_breakdown,
                "cached_qas": cached_answers,
            }

    def get_recent_applications(self, limit: int = 15) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, platform, job_title, company_name, job_url, status, mode, created_at
                FROM applications
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
