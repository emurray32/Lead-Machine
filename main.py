#!/usr/bin/env python3
"""
Unified Localization/Phrase-String Intent Monitoring Application
================================================================
This application monitors multiple target companies for early localization
and phrase-string intent signals across three integrated sources:
1. Public GitHub repositories (commits and PRs)
2. Google Play App Store updates
3. Public API/Developer Documentation pages

Features:
- Parallel processing for faster checks
- Modular monitor architecture
- Generic webhook support for Zapier/Make.com
- PR monitoring for early signals

Run continuously or on-demand. Free-tier friendly but ready for "Always On".
"""

import os
import time
import yaml
from datetime import datetime
from typing import Dict, List, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from monitors.common import (
    log, ensure_directories, load_json, save_json,
    DATA_DIR, LAST_COMMITS_FILE
)
from monitors.github_monitor import check_all_github, check_github_repo, check_github_prs
from monitors.playstore_monitor import check_all_play_store
from monitors.docs_monitor import check_all_docs
from monitors.webhooks import send_alert_to_webhooks

try:
    import storage
    storage.init_database()
    DB_AVAILABLE = True
except Exception as e:
    print(f"[WARNING] Database not available, alerts will only be logged to console: {e}")
    DB_AVAILABLE = False

COMPANIES_FILE = "companies.yaml"

GITHUB_CHECK_INTERVAL = 6 * 60 * 60
RSS_DOCS_CHECK_INTERVAL = 24 * 60 * 60
MAIN_LOOP_SLEEP = 60


def load_companies() -> List[Dict[str, Any]]:
    """Load company configuration from YAML file."""
    if not os.path.exists(COMPANIES_FILE):
        log(f"Warning: {COMPANIES_FILE} not found, using empty list", "WARNING")
        return []
    
    try:
        with open(COMPANIES_FILE, 'r') as f:
            config = yaml.safe_load(f)
        
        companies = config.get('companies', [])
        targets = []
        
        for company in companies:
            target = {
                "company": company.get('name', 'Unknown'),
                "github_org": company.get('github_org'),
                "github_repos": company.get('github_repos', []),
                "play_package": company.get('play_package'),
                "rss_url": None,
                "doc_urls": company.get('doc_urls', [])
            }
            targets.append(target)
        
        log(f"Loaded {len(targets)} companies from {COMPANIES_FILE}")
        return targets
    except Exception as e:
        log(f"Error loading {COMPANIES_FILE}: {e}", "ERROR")
        return []


def get_targets() -> List[Dict[str, Any]]:
    """Get current target list, loading from file."""
    return load_companies()


def check_github_parallel(targets: List[Dict]) -> int:
    """Check GitHub repos in parallel for faster processing."""
    log("Starting parallel GitHub checks...")
    last_commits = load_json(LAST_COMMITS_FILE)
    total_alerts = 0
    
    tasks = []
    for target in targets:
        company = target.get("company", "Unknown")
        org = target.get("github_org")
        repos = target.get("github_repos", [])
        
        if not org or not repos:
            continue
        
        for repo in repos:
            tasks.append((company, org, repo))
    
    if not tasks:
        return 0
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}
        
        for company, org, repo in tasks:
            future = executor.submit(check_github_repo, company, org, repo, last_commits)
            futures[future] = (company, org, repo)
            
            pr_future = executor.submit(check_github_prs, company, org, repo)
            futures[pr_future] = (company, org, repo, 'pr')
        
        for future in as_completed(futures):
            try:
                alerts = future.result()
                total_alerts += alerts
            except Exception as e:
                task_info = futures[future]
                log(f"Error in parallel check for {task_info}: {e}", "ERROR")
    
    save_json(LAST_COMMITS_FILE, last_commits)
    log(f"Parallel GitHub checks complete. Found {total_alerts} alerts.")
    return total_alerts


def check_all_sources_parallel(targets: List[Dict]) -> Dict[str, int]:
    """Run all source checks in parallel."""
    log("Starting parallel monitoring across all sources...")
    results = {"github": 0, "playstore": 0, "docs": 0}
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        github_future = executor.submit(check_github_parallel, targets)
        playstore_future = executor.submit(check_all_play_store, targets)
        docs_future = executor.submit(check_all_docs, targets)
        
        futures = {
            github_future: "github",
            playstore_future: "playstore",
            docs_future: "docs"
        }
        
        for future in as_completed(futures):
            source = futures[future]
            try:
                results[source] = future.result()
            except Exception as e:
                log(f"Error in {source} checks: {e}", "ERROR")
    
    total = sum(results.values())
    log(f"All checks complete. Total alerts: {total} (GitHub: {results['github']}, Play Store: {results['playstore']}, Docs: {results['docs']})")
    return results


def run_full_check():
    """Run a complete check of all sources."""
    targets = get_targets()
    
    if not targets:
        log("No targets configured. Add companies via the Admin panel or companies.yaml")
        return
    
    log(f"Running full check for {len(targets)} companies...")
    results = check_all_sources_parallel(targets)
    
    return results


def main():
    """Main entry point for the monitoring application."""
    log("=" * 60)
    log("Localization Monitor Starting")
    log("=" * 60)
    
    ensure_directories()
    
    targets = get_targets()
    log(f"Monitoring {len(targets)} companies")
    
    if not targets:
        log("No companies configured. Please add companies via:")
        log("  1. Dashboard Admin panel at /admin")
        log("  2. Edit companies.yaml directly")
        return
    
    last_github_check = 0
    last_rss_docs_check = 0
    
    try:
        now = time.time()
        
        if now - last_github_check >= GITHUB_CHECK_INTERVAL:
            github_alerts = check_github_parallel(targets)
            last_github_check = now
            log(f"GitHub check complete: {github_alerts} alerts")
        
        if now - last_rss_docs_check >= RSS_DOCS_CHECK_INTERVAL:
            playstore_alerts = check_all_play_store(targets)
            docs_alerts = check_all_docs(targets)
            last_rss_docs_check = now
            log(f"Play Store check complete: {playstore_alerts} alerts")
            log(f"Documentation check complete: {docs_alerts} alerts")
        
        log("Initial check complete.")
        
    except KeyboardInterrupt:
        log("Shutdown requested by user.")
    except Exception as e:
        log(f"Error during monitoring: {e}", "ERROR")
    
    log("Check finished. Exiting.")


if __name__ == "__main__":
    main()
