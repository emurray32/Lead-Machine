"""
Database storage layer for persisting GitHub i18n alerts.
Uses PostgreSQL via psycopg2.
"""

import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from datetime import datetime
from typing import List, Dict, Optional, Any

import config

DATABASE_URL = config.DATABASE_URL

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
               company: Optional[str] = None, search: Optional[str] = None,
               signal_type: Optional[str] = None) -> List[Dict]:
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
    """Get alert statistics (GitHub only)."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN source = 'github' THEN 1 END) as github_count
        FROM alerts
        WHERE source = 'github'
    """)
    result = cur.fetchone()
    stats = dict(result) if result else {"total": 0, "github_count": 0}

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


def get_company_alerts(company: str, limit: Optional[int] = None) -> List[Dict]:
    """Get all alerts for a specific company."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    query = "SELECT * FROM alerts WHERE company = %s ORDER BY created_at DESC"
    params = [company]
    
    if limit:
        query += " LIMIT %s"
        params.append(limit)
    
    cur.execute(query, params)
    alerts = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return [dict(a) for a in alerts]


def get_company_metrics(company: str) -> Dict:
    """Get aggregated metrics for a company focused on GitHub i18n signals."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT
            COUNT(*) as total_alerts,
            COUNT(CASE WHEN source = 'github' THEN 1 END) as github_count,
            COUNT(CASE WHEN metadata->>'signal_type' = 'NEW_LANG_FILE' THEN 1 END) as new_lang_files,
            COUNT(CASE WHEN metadata->>'signal_type' = 'OPEN_PR' THEN 1 END) as open_prs,
            MIN(created_at) as first_seen,
            MAX(created_at) as last_activity
        FROM alerts
        WHERE company = %s AND source = 'github'
    """, (company,))

    result = cur.fetchone()
    metrics = dict(result) if result else {
        'total_alerts': 0,
        'github_count': 0,
        'new_lang_files': 0,
        'open_prs': 0,
        'first_seen': None,
        'last_activity': None
    }

    cur.execute("""
        SELECT DISTINCT metadata->>'signal_type' as signal_type
        FROM alerts
        WHERE company = %s AND source = 'github' AND metadata->>'signal_type' IS NOT NULL
    """, (company,))
    signal_types = [row['signal_type'] for row in cur.fetchall()]
    metrics['signal_types'] = signal_types

    cur.execute("""
        SELECT metadata->'new_langs' as new_langs, metadata->'files' as files,
               metadata->>'detected_languages' as detected_languages
        FROM alerts
        WHERE company = %s AND source = 'github'
    """, (company,))

    all_languages = set()
    all_files = []
    for row in cur.fetchall():
        if row['new_langs']:
            langs = row['new_langs']
            if isinstance(langs, list):
                all_languages.update(langs)
        if row['detected_languages']:
            try:
                detected = row['detected_languages']
                if isinstance(detected, list):
                    all_languages.update(detected)
            except:
                pass
        if row['files']:
            files = row['files']
            if isinstance(files, list):
                all_files.extend(files)
    metrics['detected_languages'] = sorted(list(all_languages))
    metrics['localization_files'] = list(set(all_files))[:20]

    cur.execute("""
        SELECT DISTINCT metadata->>'author' as author
        FROM alerts
        WHERE company = %s AND source = 'github' AND metadata->>'author' IS NOT NULL
        LIMIT 15
    """, (company,))
    authors = [row['author'] for row in cur.fetchall() if row['author']]
    metrics['contributors'] = authors

    cur.close()
    conn.close()

    return metrics


def get_company_timeline(company: str) -> List[Dict]:
    """Get chronological timeline of i18n events for a company."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT
            id, created_at, source, title, message, keywords, url, metadata
        FROM alerts
        WHERE company = %s AND source = 'github'
        ORDER BY created_at ASC
    """, (company,))

    alerts = cur.fetchall()
    cur.close()
    conn.close()

    timeline = []
    cumulative_languages = set()

    for alert in alerts:
        metadata = alert.get('metadata') or {}
        signal_type = metadata.get('signal_type', 'UNKNOWN')

        new_langs = []
        if metadata.get('new_langs'):
            new_langs = metadata['new_langs'] if isinstance(metadata['new_langs'], list) else []
        elif metadata.get('detected_languages'):
            new_langs = metadata['detected_languages'] if isinstance(metadata['detected_languages'], list) else []

        for lang in new_langs:
            cumulative_languages.add(lang)

        timeline.append({
            'id': alert['id'],
            'date': alert['created_at'],
            'signal_type': signal_type,
            'title': alert['title'],
            'message': alert['message'],
            'url': alert['url'],
            'author': metadata.get('author'),
            'files': metadata.get('files', []),
            'languages_added': new_langs,
            'cumulative_languages': sorted(list(cumulative_languages)),
            'pr_number': metadata.get('pr_number'),
            'reviewers': metadata.get('reviewers', [])
        })

    return timeline


def get_all_companies_summary() -> List[Dict]:
    """Get summary of all companies with GitHub i18n activity."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT
            company,
            COUNT(*) as total_signals,
            COUNT(CASE WHEN metadata->>'signal_type' = 'NEW_LANG_FILE' THEN 1 END) as lang_files,
            COUNT(CASE WHEN metadata->>'signal_type' = 'OPEN_PR' THEN 1 END) as open_prs,
            MIN(created_at) as first_activity,
            MAX(created_at) as last_activity
        FROM alerts
        WHERE source = 'github'
        GROUP BY company
        ORDER BY last_activity DESC
    """)

    companies = [dict(row) for row in cur.fetchall()]
    cur.close()
    conn.close()

    return companies


def get_all_contributors(company: Optional[str] = None, sort_by: str = 'commits',
                         sort_order: str = 'desc', limit: int = 100) -> List[Dict]:
    """
    Get aggregated contributor data across all companies.

    Args:
        company: Optional filter by company name
        sort_by: 'commits', 'company', 'last_active', 'languages'
        sort_order: 'asc' or 'desc'
        limit: Max contributors to return

    Returns:
        List of contributor dicts with aggregated stats
    """
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Build query to aggregate contributor data
    query = """
        WITH contributor_data AS (
            SELECT
                metadata->>'author' as username,
                company,
                COUNT(*) as commit_count,
                COUNT(CASE WHEN metadata->>'signal_type' = 'NEW_LANG_FILE' THEN 1 END) as lang_file_commits,
                COUNT(CASE WHEN metadata->>'signal_type' = 'OPEN_PR' THEN 1 END) as pr_count,
                MIN(created_at) as first_seen,
                MAX(created_at) as last_active,
                ARRAY_AGG(DISTINCT metadata->>'signal_type') FILTER (WHERE metadata->>'signal_type' IS NOT NULL) as signal_types
            FROM alerts
            WHERE source = 'github'
                AND metadata->>'author' IS NOT NULL
                AND metadata->>'author' != ''
    """

    params = []
    if company:
        query += " AND company = %s"
        params.append(company)

    query += """
            GROUP BY metadata->>'author', company
        ),
        contributor_languages AS (
            SELECT
                metadata->>'author' as username,
                company,
                ARRAY_AGG(DISTINCT lang) FILTER (WHERE lang IS NOT NULL) as languages
            FROM alerts,
                LATERAL (
                    SELECT jsonb_array_elements_text(
                        COALESCE(metadata->'new_langs', metadata->'detected_languages', '[]'::jsonb)
                    ) as lang
                ) langs
            WHERE source = 'github'
                AND metadata->>'author' IS NOT NULL
    """

    if company:
        query += " AND company = %s"
        params.append(company)

    query += """
            GROUP BY metadata->>'author', company
        )
        SELECT
            cd.username,
            cd.company,
            cd.commit_count,
            cd.lang_file_commits,
            cd.pr_count,
            cd.first_seen,
            cd.last_active,
            cd.signal_types,
            COALESCE(cl.languages, ARRAY[]::text[]) as languages
        FROM contributor_data cd
        LEFT JOIN contributor_languages cl
            ON cd.username = cl.username AND cd.company = cl.company
    """

    # Add sorting
    order_dir = "DESC" if sort_order.lower() == 'desc' else "ASC"
    if sort_by == 'commits':
        query += f" ORDER BY cd.commit_count {order_dir}"
    elif sort_by == 'company':
        query += f" ORDER BY cd.company {order_dir}, cd.commit_count DESC"
    elif sort_by == 'last_active':
        query += f" ORDER BY cd.last_active {order_dir}"
    elif sort_by == 'languages':
        query += f" ORDER BY COALESCE(array_length(cl.languages, 1), 0) {order_dir}"
    else:
        query += f" ORDER BY cd.commit_count {order_dir}"

    query += " LIMIT %s"
    params.append(limit)

    cur.execute(query, params)
    contributors = [dict(row) for row in cur.fetchall()]

    cur.close()
    conn.close()

    return contributors


def get_contributor_stats() -> Dict:
    """Get overall contributor statistics."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT
            COUNT(DISTINCT metadata->>'author') as total_contributors,
            COUNT(DISTINCT company) as total_companies,
            COUNT(*) as total_commits
        FROM alerts
        WHERE source = 'github'
            AND metadata->>'author' IS NOT NULL
            AND metadata->>'author' != ''
    """)

    result = cur.fetchone()
    stats = dict(result) if result else {
        'total_contributors': 0,
        'total_companies': 0,
        'total_commits': 0
    }

    cur.close()
    conn.close()

    return stats


def get_contributor_details(username: str) -> Dict:
    """Get detailed information about a specific contributor."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Get all alerts for this contributor
    cur.execute("""
        SELECT
            company,
            title,
            message,
            url,
            created_at,
            metadata
        FROM alerts
        WHERE source = 'github'
            AND metadata->>'author' = %s
        ORDER BY created_at DESC
        LIMIT 50
    """, (username,))

    alerts = [dict(row) for row in cur.fetchall()]

    # Aggregate by company
    companies = {}
    all_languages = set()

    for alert in alerts:
        company = alert['company']
        if company not in companies:
            companies[company] = {
                'commit_count': 0,
                'languages': set(),
                'last_active': None
            }
        companies[company]['commit_count'] += 1
        if not companies[company]['last_active'] or alert['created_at'] > companies[company]['last_active']:
            companies[company]['last_active'] = alert['created_at']

        metadata = alert.get('metadata') or {}
        if metadata.get('new_langs'):
            langs = metadata['new_langs'] if isinstance(metadata['new_langs'], list) else []
            companies[company]['languages'].update(langs)
            all_languages.update(langs)
        if metadata.get('detected_languages'):
            langs = metadata['detected_languages'] if isinstance(metadata['detected_languages'], list) else []
            companies[company]['languages'].update(langs)
            all_languages.update(langs)

    # Convert sets to lists
    for company in companies:
        companies[company]['languages'] = sorted(list(companies[company]['languages']))

    cur.close()
    conn.close()

    return {
        'username': username,
        'companies': companies,
        'total_commits': len(alerts),
        'total_companies': len(companies),
        'all_languages': sorted(list(all_languages)),
        'recent_alerts': alerts[:10]
    }
