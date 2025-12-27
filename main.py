#!/usr/bin/env python3
"""
Unified Localization/Phrase-String Intent Monitoring Application
================================================================
This application monitors multiple target companies for early localization
and phrase-string intent signals across three integrated sources:
1. Public GitHub repositories
2. Google Play App Store updates (via RSS)
3. Public API/Developer Documentation pages

Run continuously or on-demand. Free-tier friendly but ready for "Always On".
"""

import requests
import feedparser
from bs4 import BeautifulSoup
import hashlib
import json
import os
import time
from datetime import datetime
from typing import Optional, Dict, List, Any

try:
    import storage
    storage.init_database()
    DB_AVAILABLE = True
except Exception as e:
    print(f"[WARNING] Database not available, alerts will only be logged to console: {e}")
    DB_AVAILABLE = False

# =============================================================================
# CONFIGURATION - Edit this section to customize your monitoring targets
# =============================================================================

# Shared keyword list for detecting localization intent signals
# Add or remove keywords based on your monitoring needs
KEYWORDS = [
    "i18n", "l10n", "localization", "localisation", "translate", "translation",
    "rtl", "right-to-left", "pluralization", "language", "locale", "gettext",
    "es.json", "fr.json", "de.json", "ar.json", "ja.json", "ko.json", "zh.json",
    "arabic", "spanish", "french", "german", "korean", "hindi", "japanese",
    "chinese", "portuguese", "italian", "dutch", "russian", "turkish",
    "phrase", "strings", "string file", "translations", "multi-language",
    "international", "internationalization", "i18next", "formatjs", "intl",
    "polyglot", "globalize", "messageformat"
]

# Language indicators for Play Store RSS monitoring
LANGUAGE_INDICATORS = [
    "added", "support", "now available in", "introducing", "new language",
    "language support", "available in", "localized", "translated to"
]

# Target companies to monitor - Edit/expand this list with your targets
# Each entry can have any combination of: github_org, github_repos, rss_url, doc_urls
TARGETS = [
    {
        "company": "Walmart",
        "github_org": "walmartlabs",
        "github_repos": ["thorax", "electrode"],
        "play_package": "com.walmart.android",
        "rss_url": None,
        "doc_urls": []
    },
    {
        "company": "Spotify",
        "github_org": "spotify",
        "github_repos": ["web-api", "spotify-web-api-ts-sdk"],
        "play_package": "com.spotify.music",
        "rss_url": None,
        "doc_urls": ["https://developer.spotify.com/documentation/web-api"]
    },
    {
        "company": "Airbnb",
        "github_org": "airbnb",
        "github_repos": ["javascript", "lottie-android"],
        "play_package": "com.airbnb.android",
        "rss_url": None,
        "doc_urls": []
    },
    {
        "company": "Netflix",
        "github_org": "Netflix",
        "github_repos": ["zuul", "eureka"],
        "play_package": "com.netflix.mediaclient",
        "rss_url": None,
        "doc_urls": []
    },
    {
        "company": "Uber",
        "github_org": "uber",
        "github_repos": ["RIBs", "baseweb"],
        "play_package": "com.ubercab",
        "rss_url": None,
        "doc_urls": ["https://developer.uber.com/docs/riders/introduction"]
    },
    {
        "company": "Shopify",
        "github_org": "Shopify",
        "github_repos": ["polaris", "hydrogen"],
        "play_package": "com.shopify.mobile",
        "rss_url": None,
        "doc_urls": ["https://shopify.dev/docs/api"]
    },
    {
        "company": "Nike",
        "github_org": "Nike-Inc",
        "github_repos": ["koheesio"],
        "play_package": "com.nike.omega",
        "rss_url": None,
        "doc_urls": []
    },
    {
        "company": "Stripe",
        "github_org": "stripe",
        "github_repos": ["stripe-python", "stripe-node"],
        "play_package": None,
        "rss_url": None,
        "doc_urls": ["https://stripe.com/docs/api"]
    },
    {
        "company": "Twilio",
        "github_org": "twilio",
        "github_repos": ["twilio-python", "twilio-node"],
        "play_package": None,
        "rss_url": None,
        "doc_urls": ["https://www.twilio.com/docs/usage/api"]
    },
    {
        "company": "Slack",
        "github_org": "slackapi",
        "github_repos": ["bolt-python", "bolt-js"],
        "play_package": "com.Slack",
        "rss_url": None,
        "doc_urls": ["https://api.slack.com/"]
    },
    {
        "company": "Discord",
        "github_org": "discord",
        "github_repos": ["discord-api-docs"],
        "play_package": "com.discord",
        "rss_url": None,
        "doc_urls": ["https://discord.com/developers/docs/intro"]
    },
    {
        "company": "Zoom",
        "github_org": "zoom",
        "github_repos": ["meetingsdk-sample-signature-node.js"],
        "play_package": "us.zoom.videomeetings",
        "rss_url": None,
        "doc_urls": ["https://developers.zoom.us/docs/api/"]
    },
    {
        "company": "PayPal",
        "github_org": "paypal",
        "github_repos": ["PayPal-Python-SDK"],
        "play_package": "com.paypal.android.p2pmobile",
        "rss_url": None,
        "doc_urls": ["https://developer.paypal.com/docs/api/overview/"]
    },
    {
        "company": "Square",
        "github_org": "square",
        "github_repos": ["okhttp", "retrofit"],
        "play_package": "com.squareup",
        "rss_url": None,
        "doc_urls": ["https://developer.squareup.com/docs"]
    },
    {
        "company": "Doordash",
        "github_org": "doordash",
        "github_repos": [],
        "play_package": "com.dd.doordash",
        "rss_url": None,
        "doc_urls": []
    }
]

# Check intervals (in seconds)
GITHUB_CHECK_INTERVAL = 6 * 60 * 60  # 6 hours
RSS_DOCS_CHECK_INTERVAL = 24 * 60 * 60  # 24 hours
MAIN_LOOP_SLEEP = 60  # Sleep between main loop cycles (1 minute)

# Rate limiting settings
GITHUB_RATE_LIMIT_SLEEP = 60  # Sleep if rate limited
REQUEST_DELAY = 1  # Delay between API requests to be respectful

# Persistence file paths
DATA_DIR = "monitoring_data"
LAST_COMMITS_FILE = os.path.join(DATA_DIR, "last_commits.json")
SEEN_RSS_FILE = os.path.join(DATA_DIR, "seen_rss.json")
DOC_HASHES_FILE = os.path.join(DATA_DIR, "doc_hashes.json")
PREVIOUS_TEXTS_DIR = os.path.join(DATA_DIR, "previous_texts")

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_timestamp() -> str:
    """Return current timestamp in readable format."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(message: str, level: str = "INFO") -> None:
    """Print a formatted log message with timestamp."""
    print(f"[{get_timestamp()}] [{level}] {message}")

def alert(message: str) -> None:
    """Print an alert and optionally send to Slack."""
    print(f"\n{'='*60}")
    print(f"[{get_timestamp()}] ALERT")
    print(message)
    print(f"{'='*60}\n")
    
    slack_webhook = os.environ.get("SLACK_WEBHOOK")
    if slack_webhook:
        try:
            payload = {
                "text": f"[{get_timestamp()}] {message}",
                "username": "Localization Monitor",
                "icon_emoji": ":globe_with_meridians:"
            }
            requests.post(slack_webhook, json=payload, timeout=10)
        except Exception as e:
            log(f"Failed to send Slack notification: {e}", "WARNING")

def ensure_directories() -> None:
    """Create necessary directories if they don't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(PREVIOUS_TEXTS_DIR, exist_ok=True)

def load_json(filepath: str) -> Dict:
    """Load JSON data from file, return empty dict if not exists."""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            log(f"Error loading {filepath}: {e}", "WARNING")
    return {}

def save_json(filepath: str, data: Dict) -> None:
    """Save data to JSON file."""
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        log(f"Error saving {filepath}: {e}", "ERROR")

def sanitize_filename(name: str) -> str:
    """Create a safe filename from a string."""
    return "".join(c if c.isalnum() or c in '-_' else '_' for c in name)

def contains_keywords(text: str, keywords: List[str] = KEYWORDS) -> List[str]:
    """Check if text contains any keywords, return matched keywords."""
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]

def get_headers() -> Dict[str, str]:
    """Get headers for GitHub API requests."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Localization-Monitor-Bot"
    }
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    return headers

# =============================================================================
# GITHUB MONITORING
# =============================================================================

def check_github_repo(company: str, org: str, repo: str, last_commits: Dict) -> int:
    """
    Check a GitHub repository for new commits with localization keywords.
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
            time.sleep(GITHUB_RATE_LIMIT_SLEEP)
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
            
            message = commit.get("commit", {}).get("message", "")
            matched_keywords = contains_keywords(message)
            
            if matched_keywords:
                author = commit.get("commit", {}).get("author", {}).get("name", "Unknown")
                commit_url = commit.get("html_url", "")
                short_message = message.split('\n')[0][:100]
                
                alert_msg = (
                    f"GITHUB ALERT [{company}] {org}/{repo}:\n"
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
                            title=f"{org}/{repo}: {short_message}",
                            message=f"By {author}",
                            keywords=matched_keywords,
                            url=commit_url,
                            metadata={"sha": sha, "author": author}
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

def check_all_github(targets: List[Dict]) -> int:
    """Check all configured GitHub repositories."""
    log("Starting GitHub checks...")
    last_commits = load_json(LAST_COMMITS_FILE)
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
            total_alerts += alerts
            repos_checked += 1
            time.sleep(REQUEST_DELAY)
    
    save_json(LAST_COMMITS_FILE, last_commits)
    log(f"GitHub checks complete. Checked {repos_checked} repos, found {total_alerts} alerts.")
    return total_alerts

# =============================================================================
# RSS/PLAY STORE MONITORING
# =============================================================================

def check_rss_feed(company: str, rss_url: str, seen_rss: Dict) -> int:
    """
    Check an RSS feed for new entries with localization-related content.
    Returns the number of alerts generated.
    """
    alert_count = 0
    
    try:
        feed = feedparser.parse(rss_url)
        
        if feed.bozo and not feed.entries:
            log(f"Failed to parse RSS for {company}: {feed.bozo_exception}", "WARNING")
            return 0
        
        seen_ids = seen_rss.get(company, [])
        new_seen_ids = []
        
        for entry in feed.entries[:10]:
            entry_id = entry.get("id") or entry.get("link") or entry.get("title", "")
            new_seen_ids.append(entry_id)
            
            if entry_id in seen_ids:
                continue
            
            title = entry.get("title", "")
            summary = entry.get("summary", entry.get("description", ""))
            combined_text = f"{title} {summary}"
            
            matched_keywords = contains_keywords(combined_text)
            language_matches = contains_keywords(combined_text, LANGUAGE_INDICATORS)
            
            if matched_keywords or language_matches:
                link = entry.get("link", "")
                all_matches = matched_keywords + language_matches
                
                alert_msg = (
                    f"PLAY STORE ALERT [{company}]:\n"
                    f"  Title: {title[:100]}\n"
                    f"  Summary: {summary[:200]}...\n"
                    f"  Keywords: {', '.join(all_matches)}\n"
                    f"  Link: {link}"
                )
                alert(alert_msg)
                
                if DB_AVAILABLE:
                    try:
                        storage.save_alert(
                            source="rss",
                            company=company,
                            title=title[:100],
                            message=summary[:500],
                            keywords=all_matches,
                            url=link
                        )
                    except Exception as e:
                        log(f"Failed to save alert to database: {e}", "WARNING")
                
                alert_count += 1
        
        seen_rss[company] = new_seen_ids[:10]
        
    except Exception as e:
        log(f"Error checking RSS for {company}: {e}", "ERROR")
    
    return alert_count

def check_all_rss(targets: List[Dict]) -> int:
    """Check all configured RSS feeds."""
    log("Starting RSS/Play Store checks...")
    seen_rss = load_json(SEEN_RSS_FILE)
    total_alerts = 0
    feeds_checked = 0
    
    for target in targets:
        company = target.get("company", "Unknown")
        rss_url = target.get("rss_url")
        
        if not rss_url:
            continue
        
        alerts = check_rss_feed(company, rss_url, seen_rss)
        total_alerts += alerts
        feeds_checked += 1
        time.sleep(REQUEST_DELAY)
    
    save_json(SEEN_RSS_FILE, seen_rss)
    log(f"RSS checks complete. Checked {feeds_checked} feeds, found {total_alerts} alerts.")
    return total_alerts

# =============================================================================
# DOCUMENTATION PAGE MONITORING
# =============================================================================

def fetch_doc_text(url: str) -> Optional[str]:
    """Fetch and extract clean text from a documentation URL."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; LocalizationMonitor/1.0)"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for element in soup(['script', 'style', 'nav', 'header', 'footer']):
            element.decompose()
        
        return soup.get_text(separator=' ', strip=True)
        
    except requests.RequestException as e:
        log(f"Error fetching doc URL {url}: {e}", "WARNING")
        return None

def check_doc_url(company: str, url: str, doc_hashes: Dict) -> int:
    """
    Check a documentation URL for changes and localization keywords.
    Returns the number of alerts generated.
    """
    alert_count = 0
    hash_key = f"{company}/{url}"
    
    try:
        current_text = fetch_doc_text(url)
        if not current_text:
            return 0
        
        current_hash = hashlib.md5(current_text.encode()).hexdigest()
        previous_hash = doc_hashes.get(hash_key)
        
        safe_filename = sanitize_filename(f"{company}_{url[:50]}")
        previous_text_path = os.path.join(PREVIOUS_TEXTS_DIR, f"{safe_filename}.txt")
        
        previous_text = ""
        if os.path.exists(previous_text_path):
            try:
                with open(previous_text_path, 'r', encoding='utf-8') as f:
                    previous_text = f.read()
            except IOError:
                pass
        
        if current_hash != previous_hash:
            matched_keywords = contains_keywords(current_text)
            
            if matched_keywords:
                new_keywords = []
                if previous_text:
                    previous_keywords = set(contains_keywords(previous_text))
                    new_keywords = [kw for kw in matched_keywords if kw not in previous_keywords]
                else:
                    new_keywords = matched_keywords
                
                if new_keywords or not previous_hash:
                    alert_msg = (
                        f"DOCS ALERT [{company}]:\n"
                        f"  Possible new localization content detected\n"
                        f"  URL: {url}\n"
                        f"  New keywords: {', '.join(new_keywords) if new_keywords else 'First scan - all found'}\n"
                        f"  All keywords found: {', '.join(matched_keywords[:10])}..."
                    )
                    alert(alert_msg)
                    
                    if DB_AVAILABLE:
                        try:
                            storage.save_alert(
                                source="docs",
                                company=company,
                                title=f"Doc change detected: {url[:80]}",
                                message=f"New keywords: {', '.join(new_keywords) if new_keywords else 'First scan'}",
                                keywords=new_keywords if new_keywords else matched_keywords[:10],
                                url=url
                            )
                        except Exception as e:
                            log(f"Failed to save alert to database: {e}", "WARNING")
                    
                    alert_count += 1
        
        doc_hashes[hash_key] = current_hash
        try:
            with open(previous_text_path, 'w', encoding='utf-8') as f:
                f.write(current_text)
        except IOError as e:
            log(f"Error saving previous text for {url}: {e}", "WARNING")
        
    except Exception as e:
        log(f"Error checking doc URL {url}: {e}", "ERROR")
    
    return alert_count

def check_all_docs(targets: List[Dict]) -> int:
    """Check all configured documentation URLs."""
    log("Starting documentation page checks...")
    doc_hashes = load_json(DOC_HASHES_FILE)
    total_alerts = 0
    docs_checked = 0
    
    for target in targets:
        company = target.get("company", "Unknown")
        doc_urls = target.get("doc_urls", [])
        
        for url in doc_urls:
            alerts = check_doc_url(company, url, doc_hashes)
            total_alerts += alerts
            docs_checked += 1
            time.sleep(REQUEST_DELAY)
    
    save_json(DOC_HASHES_FILE, doc_hashes)
    log(f"Documentation checks complete. Checked {docs_checked} pages, found {total_alerts} alerts.")
    return total_alerts

# =============================================================================
# MAIN MONITORING LOOP
# =============================================================================

def run_monitoring_cycle(last_github_check: float, last_rss_docs_check: float) -> tuple:
    """
    Run a monitoring cycle, checking sources based on their schedules.
    Returns updated timestamps.
    """
    current_time = time.time()
    github_alerts = 0
    rss_alerts = 0
    docs_alerts = 0
    
    if current_time - last_github_check >= GITHUB_CHECK_INTERVAL:
        github_alerts = check_all_github(TARGETS)
        last_github_check = current_time
    
    if current_time - last_rss_docs_check >= RSS_DOCS_CHECK_INTERVAL:
        rss_alerts = check_all_rss(TARGETS)
        docs_alerts = check_all_docs(TARGETS)
        last_rss_docs_check = current_time
    
    total_alerts = github_alerts + rss_alerts + docs_alerts
    if total_alerts > 0:
        log(f"Cycle complete. Total alerts this cycle: {total_alerts}")
    
    return last_github_check, last_rss_docs_check

def print_banner() -> None:
    """Print startup banner with configuration summary."""
    print("\n" + "="*60)
    print(" LOCALIZATION MONITORING APPLICATION")
    print(" Version 1.0")
    print("="*60)
    print(f"\nStarted at: {get_timestamp()}")
    print(f"\nMonitoring {len(TARGETS)} target companies:")
    
    github_count = sum(1 for t in TARGETS if t.get("github_repos"))
    rss_count = sum(1 for t in TARGETS if t.get("rss_url"))
    docs_count = sum(1 for t in TARGETS if t.get("doc_urls"))
    
    print(f"  - GitHub repos configured: {github_count} companies")
    print(f"  - RSS feeds configured: {rss_count} companies")
    print(f"  - Doc pages configured: {docs_count} companies")
    
    print(f"\nCheck intervals:")
    print(f"  - GitHub: Every {GITHUB_CHECK_INTERVAL // 3600} hours")
    print(f"  - RSS/Docs: Every {RSS_DOCS_CHECK_INTERVAL // 3600} hours")
    
    github_token = os.environ.get("GITHUB_TOKEN")
    slack_webhook = os.environ.get("SLACK_WEBHOOK")
    print(f"\nSecrets configured:")
    print(f"  - GITHUB_TOKEN: {'Yes' if github_token else 'No (using anonymous access)'}")
    print(f"  - SLACK_WEBHOOK: {'Yes' if slack_webhook else 'No (console only)'}")
    
    print("\n" + "="*60 + "\n")

def main() -> None:
    """Main entry point for the monitoring application."""
    print_banner()
    ensure_directories()
    
    log("Running scheduled monitoring check...")
    
    try:
        github_alerts = check_all_github(TARGETS)
        rss_alerts = check_all_rss(TARGETS)
        docs_alerts = check_all_docs(TARGETS)
        
        total_alerts = github_alerts + rss_alerts + docs_alerts
        log(f"Monitoring complete. Total alerts: {total_alerts}")
        
    except Exception as e:
        log(f"Error during monitoring: {e}", "ERROR")
    
    log("Check finished. Exiting.")

if __name__ == "__main__":
    main()
