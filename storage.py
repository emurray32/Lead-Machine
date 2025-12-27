"""
Database storage layer for persisting alerts.
Uses PostgreSQL via psycopg2.
"""

import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from datetime import datetime
from typing import List, Dict, Optional, Any

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_connection():
    """Get a database connection."""
    return psycopg2.connect(DATABASE_URL)

def init_database():
    """Initialize the database schema."""
    conn = get_connection()
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
    conn.close()

def save_alert(source: str, company: str, title: str, message: str, 
               keywords: List[str], url: str, metadata: Optional[Dict] = None) -> int:
    """Save an alert to the database and return the ID."""
    conn = get_connection()
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
    conn.close()
    
    return alert_id

def get_alerts(limit: int = 100, source: Optional[str] = None, 
               company: Optional[str] = None) -> List[Dict]:
    """Get alerts with optional filtering."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    query = "SELECT * FROM alerts WHERE 1=1"
    params = []
    
    if source:
        query += " AND source = %s"
        params.append(source)
    
    if company:
        query += " AND company = %s"
        params.append(company)
    
    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    
    cur.execute(query, params)
    alerts = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return [dict(a) for a in alerts]

def get_companies() -> List[str]:
    """Get list of distinct companies with alerts."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT DISTINCT company FROM alerts ORDER BY company")
    companies = [row[0] for row in cur.fetchall()]
    
    cur.close()
    conn.close()
    
    return companies

def get_alert_stats() -> Dict:
    """Get alert statistics."""
    conn = get_connection()
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
    conn.close()
    
    return stats

def prune_old_alerts(days: int = 90) -> int:
    """Delete alerts older than specified days. Returns count deleted."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        DELETE FROM alerts 
        WHERE created_at < NOW() - INTERVAL '%s days'
    """, (days,))
    
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    
    return deleted
