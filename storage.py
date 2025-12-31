"""
Database storage layer for persisting alerts.
Uses PostgreSQL via psycopg2 with connection pooling.
"""

import os
import json
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, Json
from contextlib import contextmanager
from datetime import datetime
from typing import List, Dict, Optional, Any

import config

DATABASE_URL = config.DATABASE_URL

# Connection pool (initialized lazily)
_connection_pool = None

def _get_pool():
    """Get or create the connection pool."""
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=DATABASE_URL
        )
    return _connection_pool

@contextmanager
def get_connection():
    """Get a database connection from the pool using context manager."""
    conn = None
    try:
        conn = _get_pool().getconn()
        yield conn
    finally:
        if conn:
            _get_pool().putconn(conn)

def init_database():
    """Initialize the database schema."""
    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source VARCHAR(50) NOT NULL,
                company VARCHAR(100) NOT NULL,
                title VARCHAR(500),
                message TEXT,
                keywords TEXT,
                url TEXT,
                metadata JSONB
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at DESC)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_company ON alerts(company)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_alerts_source ON alerts(source)
        """)

        conn.commit()
        cur.close()

def save_alert(source: str, company: str, title: str, message: str,
               keywords: List[str], url: str, metadata: Optional[Dict] = None) -> int:
    """Save an alert to the database and return the ID."""
    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO alerts (source, company, title, message, keywords, url, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (source, company, title, message, ', '.join(keywords), url,
              Json(metadata) if metadata else None))

        result = cur.fetchone()
        alert_id = result[0] if result else 0
        conn.commit()
        cur.close()

        return alert_id

def get_alerts(limit: int = 100, source: Optional[str] = None,
               company: Optional[str] = None, search: Optional[str] = None,
               signal_type: Optional[str] = None) -> List[Dict]:
    """Get alerts with optional filtering."""
    with get_connection() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        query = "SELECT * FROM alerts WHERE 1=1"
        params = []

        if source:
            query += " AND source = %s"
            params.append(source)

        if company:
            query += " AND company = %s"
            params.append(company)

        if search:
            query += " AND (company ILIKE %s OR title ILIKE %s OR message ILIKE %s OR keywords ILIKE %s)"
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern, search_pattern, search_pattern])

        if signal_type:
            query += " AND metadata->>'signal_type' = %s"
            params.append(signal_type)

        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)

        cur.execute(query, params)
        alerts = cur.fetchall()

        cur.close()

        return [dict(a) for a in alerts]

def get_companies() -> List[str]:
    """Get list of distinct companies with alerts."""
    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("SELECT DISTINCT company FROM alerts ORDER BY company")
        companies = [row[0] for row in cur.fetchall()]

        cur.close()

        return companies

def get_alert_stats() -> Dict:
    """Get alert statistics."""
    with get_connection() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN source = 'github' THEN 1 END) as github_count,
                COUNT(CASE WHEN source = 'playstore' OR source = 'rss' THEN 1 END) as playstore_count,
                COUNT(CASE WHEN source = 'docs' THEN 1 END) as docs_count
            FROM alerts
        """)
        result = cur.fetchone()
        stats = dict(result) if result else {"total": 0, "github_count": 0, "playstore_count": 0, "docs_count": 0}

        cur.close()

        return stats

def prune_old_alerts(days: int = 90) -> int:
    """Delete alerts older than specified days. Returns count deleted."""
    with get_connection() as conn:
        cur = conn.cursor()

        # Fix SQL injection vulnerability - use parameterized query properly
        cur.execute("""
            DELETE FROM alerts
            WHERE created_at < NOW() - INTERVAL %s
        """, (f'{days} days',))

        deleted = cur.rowcount
        conn.commit()
        cur.close()

        return deleted


def get_company_alerts(company: str, limit: Optional[int] = None) -> List[Dict]:
    """Get all alerts for a specific company."""
    with get_connection() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        query = "SELECT * FROM alerts WHERE company = %s ORDER BY created_at DESC"
        params = [company]

        if limit:
            query += " LIMIT %s"
            params.append(limit)

        cur.execute(query, params)
        alerts = cur.fetchall()

        cur.close()

        return [dict(a) for a in alerts]


def get_company_metrics(company: str) -> Dict:
    """Get aggregated metrics for a company."""
    with get_connection() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT
                COUNT(*) as total_alerts,
                COUNT(CASE WHEN source = 'github' THEN 1 END) as github_count,
                COUNT(CASE WHEN source = 'playstore' THEN 1 END) as playstore_count,
                COUNT(CASE WHEN source = 'docs' THEN 1 END) as docs_count,
                COUNT(CASE WHEN metadata->>'signal_type' = 'NEW_LANG_FILE' THEN 1 END) as new_lang_files,
                COUNT(CASE WHEN metadata->>'signal_type' = 'NEW_HREFLANG' THEN 1 END) as new_hreflangs,
                COUNT(CASE WHEN metadata->>'signal_type' = 'NEW_APP_LANG' THEN 1 END) as new_app_langs,
                COUNT(CASE WHEN metadata->>'signal_type' = 'OPEN_PR' THEN 1 END) as open_prs,
                MIN(created_at) as first_seen,
                MAX(created_at) as last_activity
            FROM alerts
            WHERE company = %s
        """, (company,))

        result = cur.fetchone()
        metrics = dict(result) if result else {
            'total_alerts': 0,
            'github_count': 0,
            'playstore_count': 0,
            'docs_count': 0,
            'new_lang_files': 0,
            'new_hreflangs': 0,
            'new_app_langs': 0,
            'open_prs': 0,
            'first_seen': None,
            'last_activity': None
        }

        cur.execute("""
            SELECT DISTINCT metadata->>'signal_type' as signal_type
            FROM alerts
            WHERE company = %s AND metadata->>'signal_type' IS NOT NULL
        """, (company,))
        signal_types = [row['signal_type'] for row in cur.fetchall()]
        metrics['signal_types'] = signal_types

        cur.execute("""
            SELECT metadata->'new_langs' as new_langs
            FROM alerts
            WHERE company = %s AND metadata->'new_langs' IS NOT NULL
        """, (company,))

        all_languages = set()
        for row in cur.fetchall():
            if row['new_langs']:
                langs = row['new_langs']
                if isinstance(langs, list):
                    all_languages.update(langs)
        metrics['detected_languages'] = list(all_languages)

        cur.execute("""
            SELECT DISTINCT metadata->>'author' as author
            FROM alerts
            WHERE company = %s AND metadata->>'author' IS NOT NULL
            LIMIT 10
        """, (company,))
        authors = [row['author'] for row in cur.fetchall() if row['author']]
        metrics['contributors'] = authors

        cur.close()

        return metrics
