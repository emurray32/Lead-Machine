"""
GitHub Repository and Pull Request Monitoring
Detects localization file additions and PR activity.
"""

import os
import time
import requests
from typing import Dict, List, Optional

import config
from .common import (
    log, alert, load_json, save_json, get_headers,
    is_bot_author, is_localization_file, extract_language_from_file,
    contains_keywords
)

try:
    import storage
    DB_AVAILABLE = True
except:
    DB_AVAILABLE = False


def get_commit_files(org: str, repo: str, sha: str) -> List[Dict]:
    """Fetch the files changed in a specific commit."""
    try:
        url = f"https://api.github.com/repos/{org}/{repo}/commits/{sha}"
        response = requests.get(url, headers=get_headers(), timeout=30)
        if response.status_code == 200:
            commit_data = response.json()
            return commit_data.get("files", [])
    except Exception as e:
        log(f"Error fetching commit files for {sha}: {e}", "WARNING")
    return []


def check_github_repo(company: str, org: str, repo: str, last_commits: Dict) -> int:
    """
    Check a GitHub repository for new localization file additions.
    Returns the number of alerts generated.
    """
    alert_count = 0
    repo_key = f"{company}/{org}/{repo}"
    
    try:
        url = f"https://api.github.com/repos/{org}/{repo}/commits"
        params = {"per_page": 20}
        
        response = requests.get(url, headers=get_headers(), params=params, timeout=30)
        
        if response.status_code == 403:
            remaining = response.headers.get("X-RateLimit-Remaining", "unknown")
            log(f"GitHub rate limit hit (remaining: {remaining}). Sleeping...", "WARNING")
            time.sleep(config.GITHUB_RATE_LIMIT_SLEEP)
            return 0
        
        if response.status_code == 404:
            log(f"Repository not found: {org}/{repo}", "WARNING")
            return 0
        
        response.raise_for_status()
        commits = response.json()
        
        if not commits:
            return 0
        
        last_sha = last_commits.get(repo_key)
        new_last_sha = commits[0]["sha"]
        
        for commit in commits:
            sha = commit["sha"]
            
            if sha == last_sha:
                break
            
            author = commit.get("commit", {}).get("author", {}).get("name", "Unknown")
            
            if is_bot_author(author):
                continue
            
            commit_url = commit.get("html_url", "")
            message = commit.get("commit", {}).get("message", "")
            short_message = message.split('\n')[0][:100]
            
            files = get_commit_files(org, repo, sha)
            new_l10n_files = []
            detected_languages = []
            
            for file_info in files:
                filepath = file_info.get("filename", "")
                status = file_info.get("status", "")
                
                if status == "added" and is_localization_file(filepath):
                    new_l10n_files.append(filepath)
                    lang = extract_language_from_file(filepath)
                    if lang and lang not in detected_languages:
                        detected_languages.append(lang)
            
            if new_l10n_files:
                signal_type = "NEW_LANG_FILE"
                keywords = detected_languages if detected_languages else ["new localization file"]
                files_display = ", ".join(os.path.basename(f) for f in new_l10n_files[:3])
                if len(new_l10n_files) > 3:
                    files_display += f" (+{len(new_l10n_files) - 3} more)"
                
                alert_msg = (
                    f"GITHUB [{signal_type}] [{company}] {org}/{repo}:\n"
                    f"  Files: {files_display}\n"
                    f"  Languages: {', '.join(detected_languages) if detected_languages else 'unknown'}\n"
                    f"  Author: {author}\n"
                    f"  URL: {commit_url}"
                )
                alert(alert_msg)
                
                if DB_AVAILABLE:
                    try:
                        storage.save_alert(
                            source="github",
                            company=company,
                            title=f"[{signal_type}] {org}/{repo}: {files_display}",
                            message=f"New localization files by {author}. {short_message}",
                            keywords=keywords,
                            url=commit_url,
                            metadata={"sha": sha, "author": author, "signal_type": signal_type, "files": new_l10n_files[:5]}
                        )
                    except Exception as e:
                        log(f"Failed to save alert to database: {e}", "WARNING")
                
                alert_count += 1
            else:
                matched_keywords = contains_keywords(message)
                if matched_keywords:
                    signal_type = "KEYWORD"
                    
                    alert_msg = (
                        f"GITHUB [{signal_type}] [{company}] {org}/{repo}:\n"
                        f"  Message: {short_message}\n"
                        f"  Author: {author}\n"
                        f"  Keywords: {', '.join(matched_keywords)}\n"
                        f"  URL: {commit_url}"
                    )
                    alert(alert_msg)
                    
                    if DB_AVAILABLE:
                        try:
                            storage.save_alert(
                                source="github",
                                company=company,
                                title=f"[{signal_type}] {org}/{repo}: {short_message}",
                                message=f"By {author}",
                                keywords=matched_keywords,
                                url=commit_url,
                                metadata={"sha": sha, "author": author, "signal_type": signal_type}
                            )
                        except Exception as e:
                            log(f"Failed to save alert to database: {e}", "WARNING")
                    
                    alert_count += 1
        
        last_commits[repo_key] = new_last_sha
        
    except requests.RequestException as e:
        log(f"Error checking GitHub repo {org}/{repo}: {e}", "ERROR")
    except Exception as e:
        log(f"Unexpected error checking GitHub repo {org}/{repo}: {e}", "ERROR")
    
    return alert_count


def check_github_prs(company: str, org: str, repo: str) -> int:
    """
    Check open Pull Requests for localization signals.
    PRs titled with translation/localization keywords indicate intent before merge.
    Returns the number of alerts generated.
    """
    alert_count = 0
    
    try:
        url = f"https://api.github.com/repos/{org}/{repo}/pulls"
        params = {"state": "open", "per_page": 30}
        
        response = requests.get(url, headers=get_headers(), params=params, timeout=30)
        
        if response.status_code == 403:
            log(f"GitHub rate limit hit for PR check", "WARNING")
            return 0
        
        if response.status_code == 404:
            return 0
        
        response.raise_for_status()
        prs = response.json()
        
        l10n_keywords = [
            "translation", "translate", "localization", "localisation",
            "i18n", "l10n", "language", "arabic", "french", "spanish",
            "german", "chinese", "japanese", "korean", "portuguese"
        ]
        
        for pr in prs:
            title = pr.get("title", "").lower()
            body = (pr.get("body") or "").lower()
            pr_url = pr.get("html_url", "")
            pr_number = pr.get("number", 0)
            author = pr.get("user", {}).get("login", "Unknown")
            
            if is_bot_author(author):
                continue
            
            title_matches = [kw for kw in l10n_keywords if kw in title]
            
            if title_matches:
                signal_type = "OPEN_PR"
                
                alert_msg = (
                    f"GITHUB [{signal_type}] [{company}] {org}/{repo}:\n"
                    f"  PR #{pr_number}: {pr.get('title', 'No title')}\n"
                    f"  Author: {author}\n"
                    f"  Keywords: {', '.join(title_matches)}\n"
                    f"  URL: {pr_url}"
                )
                alert(alert_msg)
                
                if DB_AVAILABLE:
                    try:
                        storage.save_alert(
                            source="github",
                            company=company,
                            title=f"[{signal_type}] PR #{pr_number}: {pr.get('title', '')[:80]}",
                            message=f"Open pull request by {author} - early localization signal",
                            keywords=title_matches,
                            url=pr_url,
                            metadata={"pr_number": pr_number, "author": author, "signal_type": signal_type}
                        )
                    except Exception as e:
                        log(f"Failed to save PR alert: {e}", "WARNING")
                
                alert_count += 1
        
    except Exception as e:
        log(f"Error checking PRs for {org}/{repo}: {e}", "ERROR")
    
    return alert_count


def check_all_github(targets: List[Dict]) -> int:
    """Check all configured GitHub repositories."""
    log("Starting GitHub checks...")
    last_commits = load_json(config.LAST_COMMITS_FILE)
    total_alerts = 0
    repos_checked = 0
    
    for target in targets:
        company = target.get("company", "Unknown")
        org = target.get("github_org")
        repos = target.get("github_repos", [])
        
        if not org or not repos:
            continue
        
        for repo in repos:
            alerts = check_github_repo(company, org, repo, last_commits)
            pr_alerts = check_github_prs(company, org, repo)
            total_alerts += alerts + pr_alerts
            repos_checked += 1
            time.sleep(config.REQUEST_DELAY)
    
    save_json(config.LAST_COMMITS_FILE, last_commits)
    log(f"GitHub checks complete. Checked {repos_checked} repos, found {total_alerts} alerts.")
    return total_alerts
