#!/usr/bin/env python3
"""
GitHub i18n Timeline Intelligence
==================================
This application monitors target companies for internationalization signals
through their public GitHub repositories (commits and PRs).

Features:
- Parallel processing for faster checks
- PR monitoring for early signals
- Webhook support for Zapier/Make.com

Run continuously or on-demand.
"""

import os
import time
import yaml
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any
import config
from monitors.common import (
    log, ensure_directories, load_json, save_json
)
from monitors.github_monitor import check_all_github, check_github_repo, check_github_prs
from monitors.webhooks import send_alert_to_webhooks

try:
    import storage
    storage.init_database()
    DB_AVAILABLE = True
except Exception as e:
    print(f"[WARNING] Database not available, alerts will only be logged to console: {e}")
    DB_AVAILABLE = False




def load_companies() -> List[Dict[str, Any]]:
    """Load company configuration from YAML file."""
    if not os.path.exists(config.COMPANIES_FILE):
        log(f"Warning: {config.COMPANIES_FILE} not found, using empty list", "WARNING")
        return []
    
    try:
        with open(config.COMPANIES_FILE, 'r') as f:
            config_data = yaml.safe_load(f)
        
        companies = config_data.get('companies', [])
        targets = []
        
        for company in companies:
            target = {
                "company": company.get('name', 'Unknown'),
                "github_org": company.get('github_org'),
                "github_repos": company.get('github_repos', [])
            }
            targets.append(target)
        
        log(f"Loaded {len(targets)} companies from {config.COMPANIES_FILE}")
        return targets
    except Exception as e:
        log(f"Error loading {config.COMPANIES_FILE}: {e}", "ERROR")
        return []


def get_targets() -> List[Dict[str, Any]]:
    """Get current target list, loading from file."""
    return load_companies()


def check_github_parallel(targets: List[Dict]) -> int:
    """Check GitHub repos in parallel for faster processing."""
    log("Starting parallel GitHub checks...")
    last_commits = load_json(config.LAST_COMMITS_FILE)
    total_alerts = 0
    state_lock = threading.Lock()  # Thread-safe lock for shared state updates

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

    def thread_safe_check(company, org, repo):
        """Wrapper to perform GitHub check with thread-safe state updates."""
        # Pass a thread-safe reference - dict updates are atomic in CPython
        # but we use a lock for extra safety when updating shared state
        alerts = check_github_repo(company, org, repo, last_commits)
        return alerts

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}

        for company, org, repo in tasks:
            future = executor.submit(thread_safe_check, company, org, repo)
            futures[future] = (company, org, repo)

            pr_future = executor.submit(check_github_prs, company, org, repo)
            futures[pr_future] = (company, org, repo, 'pr')

        for future in as_completed(futures):
            try:
                alerts = future.result()
                with state_lock:
                    total_alerts += alerts
            except Exception as e:
                task_info = futures[future]
                log(f"Error in parallel check for {task_info}: {e}", "ERROR")

    save_json(config.LAST_COMMITS_FILE, last_commits)
    log(f"Parallel GitHub checks complete. Found {total_alerts} alerts.")
    return total_alerts


def check_all_sources_parallel(targets: List[Dict]) -> Dict[str, int]:
    """Run GitHub monitoring (the only source we track)."""
    log("Starting GitHub monitoring...")
    results = {"github": 0}

    try:
        results["github"] = check_github_parallel(targets)
    except Exception as e:
        log(f"Error in GitHub checks: {e}", "ERROR")

    log(f"GitHub check complete. Total alerts: {results['github']}")
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

    # Validate configuration at startup
    config.validate_config()

    ensure_directories()
    
    targets = get_targets()
    log(f"Monitoring {len(targets)} companies")
    
    if not targets:
        log("No companies configured. Please add companies via:")
        log("  1. Dashboard Admin panel at /admin")
        log("  2. Edit companies.yaml directly")
        return
    
    last_github_check = 0

    # Check if we should run in continuous mode or single-check mode
    continuous_mode = os.environ.get('MONITOR_CONTINUOUS', 'false').lower() == 'true'

    try:
        while True:
            now = time.time()
            checks_performed = False

            if now - last_github_check >= config.GITHUB_CHECK_INTERVAL:
                github_alerts = check_github_parallel(targets)
                last_github_check = now
                log(f"GitHub check complete: {github_alerts} alerts")
                checks_performed = True

            if checks_performed:
                log("Check cycle complete.")

            # Exit after first run if not in continuous mode
            if not continuous_mode:
                log("Single-check mode. Exiting.")
                break

            # Sleep before next check cycle
            sleep_time = config.GITHUB_CHECK_INTERVAL
            log(f"Sleeping for {sleep_time} seconds...")
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        log("Shutdown requested by user.")
    except Exception as e:
        log(f"Error during monitoring: {e}", "ERROR")

    log("Monitoring finished.")


if __name__ == "__main__":
    main()
