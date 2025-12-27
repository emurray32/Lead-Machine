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
import yaml
from datetime import datetime
from typing import Optional, Dict, List, Any

try:
    from google_play_scraper import app as gplay_app
    GPLAY_AVAILABLE = True
except ImportError:
    GPLAY_AVAILABLE = False

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

# Bot patterns to filter out - these are maintenance noise, not expansion intent
BOT_PATTERNS = [
    "[bot]", "dependabot", "github-actions", "renovate", "greenkeeper",
    "snyk-bot", "codecov", "semantic-release", "auto-merge"
]

# Localization directory patterns - files in these dirs indicate true intent
LOCALIZATION_DIRS = [
    "locales/", "locale/", "i18n/", "l10n/", "translations/", "lang/",
    "languages/", "res/values-", "strings/", "messages/", "intl/"
]

# Localization file extensions
LOCALIZATION_FILE_PATTERNS = [
    ".json", ".yaml", ".yml", ".properties", ".po", ".pot", ".xliff",
    ".strings", ".resx", ".arb"
]

# Language codes that indicate new language files
LANGUAGE_CODES = [
    "ar", "zh", "cs", "da", "nl", "fi", "fr", "de", "el", "he", "hi",
    "hu", "id", "it", "ja", "ko", "ms", "no", "pl", "pt", "pt-br",
    "ro", "ru", "sk", "es", "sv", "th", "tr", "uk", "vi", "bn", "ta",
    "te", "mr", "gu", "kn", "ml", "pa", "sw", "zu", "af", "sq", "am",
    "hy", "az", "eu", "be", "bs", "bg", "ca", "hr", "et", "fil", "gl",
    "ka", "is", "lv", "lt", "mk", "mt", "mn", "ne", "fa", "sr", "si", "sl"
]

# =============================================================================
# COMPANY CONFIGURATION - Loaded from companies.yaml
# =============================================================================

COMPANIES_FILE = "companies.yaml"

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

def save_companies(companies: List[Dict[str, Any]]) -> bool:
    """Save company configuration to YAML file."""
    try:
        yaml_companies = []
        for target in companies:
            company = {'name': target.get('company', 'Unknown')}
            if target.get('github_org'):
                company['github_org'] = target['github_org']
            if target.get('github_repos'):
                company['github_repos'] = target['github_repos']
            if target.get('play_package'):
                company['play_package'] = target['play_package']
            if target.get('doc_urls'):
                company['doc_urls'] = target['doc_urls']
            yaml_companies.append(company)
        
        config = {'companies': yaml_companies}
        
        with open(COMPANIES_FILE, 'w') as f:
            f.write("# Localization Monitor - Company Configuration\n")
            f.write("# Edit this file or use the dashboard admin panel to add/remove companies\n\n")
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        
        log(f"Saved {len(yaml_companies)} companies to {COMPANIES_FILE}")
        return True
    except Exception as e:
        log(f"Error saving {COMPANIES_FILE}: {e}", "ERROR")
        return False

def get_targets() -> List[Dict[str, Any]]:
    """Get current target list, loading from file."""
    return load_companies()

TARGETS = []

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
PLAY_STORE_LANGS_FILE = os.path.join(DATA_DIR, "play_store_langs.json")
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

def is_bot_author(author: str) -> bool:
    """Check if the commit author is a bot."""
    author_lower = author.lower()
    return any(bot.lower() in author_lower for bot in BOT_PATTERNS)

def is_localization_file(filepath: str) -> bool:
    """Check if a file path indicates a localization file."""
    filepath_lower = filepath.lower()
    in_l10n_dir = any(dir_pattern in filepath_lower for dir_pattern in LOCALIZATION_DIRS)
    has_l10n_ext = any(filepath_lower.endswith(ext) for ext in LOCALIZATION_FILE_PATTERNS)
    return in_l10n_dir and has_l10n_ext

def extract_language_from_file(filepath: str) -> Optional[str]:
    """Extract language code from a localization file path if present."""
    filepath_lower = filepath.lower()
    filename = os.path.basename(filepath_lower)
    name_without_ext = os.path.splitext(filename)[0]
    
    for code in LANGUAGE_CODES:
        if name_without_ext == code or name_without_ext.endswith(f"_{code}") or name_without_ext.endswith(f"-{code}"):
            return code
        if f"/{code}/" in filepath_lower or f"/{code}." in filepath_lower:
            return code
        if f"values-{code}" in filepath_lower:
            return code
    return None

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

_github_connection_cache = {"settings": None, "expires_at": None}

def get_github_access_token() -> Optional[str]:
    """Get GitHub access token from Replit connection or environment variable."""
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ.get("GITHUB_TOKEN")
    
    hostname = os.environ.get("REPLIT_CONNECTORS_HOSTNAME")
    repl_identity = os.environ.get("REPL_IDENTITY")
    web_repl_renewal = os.environ.get("WEB_REPL_RENEWAL")
    
    if not hostname:
        return None
    
    x_replit_token = None
    if repl_identity:
        x_replit_token = f"repl {repl_identity}"
    elif web_repl_renewal:
        x_replit_token = f"depl {web_repl_renewal}"
    
    if not x_replit_token:
        return None
    
    cached = _github_connection_cache
    if cached["settings"] and cached["expires_at"]:
        try:
            if datetime.fromisoformat(cached["expires_at"].replace("Z", "+00:00")) > datetime.now():
                return cached["settings"].get("access_token")
        except:
            pass
    
    try:
        response = requests.get(
            f"https://{hostname}/api/v2/connection?include_secrets=true&connector_names=github",
            headers={
                "Accept": "application/json",
                "X_REPLIT_TOKEN": x_replit_token
            },
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        connection = data.get("items", [{}])[0]
        settings = connection.get("settings", {})
        
        access_token = settings.get("access_token") or settings.get("oauth", {}).get("credentials", {}).get("access_token")
        
        if access_token:
            _github_connection_cache["settings"] = settings
            _github_connection_cache["expires_at"] = settings.get("expires_at")
            return access_token
    except Exception as e:
        log(f"Error fetching GitHub connection: {e}", "WARNING")
    
    return None

def get_headers() -> Dict[str, str]:
    """Get headers for GitHub API requests."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Localization-Monitor-Bot"
    }
    github_token = get_github_access_token()
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    return headers

# =============================================================================
# GITHUB MONITORING
# =============================================================================

def check_github_repo(company: str, org: str, repo: str, last_commits: Dict) -> int:
    """
    Check a GitHub repository for new localization file additions.
    Primary signal: New files added to localization directories.
    Secondary signal: Keyword matches in commit messages (filtered for bots).
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
# PLAY STORE MONITORING (Language List Comparison)
# =============================================================================

def get_play_store_languages(package_id: str) -> Optional[List[str]]:
    """Fetch the list of supported languages for an app from Google Play Store."""
    if not GPLAY_AVAILABLE:
        return None
    
    try:
        app_info = gplay_app(package_id, lang='en', country='us')
        descriptions_languages = app_info.get('descriptionHTML', '')
        
        available_langs = []
        
        for lang_code in LANGUAGE_CODES:
            try:
                lang_app = gplay_app(package_id, lang=lang_code, country='us')
                if lang_app.get('description'):
                    available_langs.append(lang_code)
            except:
                pass
            time.sleep(0.2)
        
        return available_langs if available_langs else None
        
    except Exception as e:
        log(f"Error fetching Play Store info for {package_id}: {e}", "WARNING")
        return None

def check_play_store_package(company: str, package_id: str, stored_langs: Dict) -> int:
    """
    Check a Play Store package for new language support.
    Compares current language list against previously stored list.
    Returns the number of alerts generated.
    """
    if not GPLAY_AVAILABLE:
        return 0
    
    alert_count = 0
    
    try:
        app_info = gplay_app(package_id, lang='en', country='us')
        
        if not app_info:
            log(f"Could not fetch Play Store info for {package_id}", "WARNING")
            return 0
        
        app_title = app_info.get('title', package_id)
        installs = app_info.get('installs', 'Unknown')
        
        previous_langs = set(stored_langs.get(package_id, []))
        
        test_langs = ["en", "es", "fr", "de", "ja", "ko", "zh", "pt", "ru", "ar", "hi", "it", "nl", "pl", "tr", "vi", "th", "id"]
        current_langs = set()
        
        for lang in test_langs:
            try:
                lang_app = gplay_app(package_id, lang=lang, country='us')
                if lang_app and lang_app.get('description'):
                    current_langs.add(lang)
                time.sleep(0.3)
            except:
                pass
        
        new_langs = current_langs - previous_langs
        
        if new_langs and previous_langs:
            signal_type = "NEW_APP_LANG"
            new_langs_list = list(new_langs)
            
            play_url = f"https://play.google.com/store/apps/details?id={package_id}"
            
            alert_msg = (
                f"PLAY STORE [{signal_type}] [{company}]:\n"
                f"  App: {app_title}\n"
                f"  New languages: {', '.join(new_langs_list)}\n"
                f"  Total languages: {len(current_langs)}\n"
                f"  Installs: {installs}\n"
                f"  URL: {play_url}"
            )
            alert(alert_msg)
            
            if DB_AVAILABLE:
                try:
                    storage.save_alert(
                        source="playstore",
                        company=company,
                        title=f"[{signal_type}] {app_title}: +{', '.join(new_langs_list)}",
                        message=f"App now supports {len(current_langs)} languages. Installs: {installs}",
                        keywords=new_langs_list,
                        url=play_url,
                        metadata={"signal_type": signal_type, "package_id": package_id, "new_langs": new_langs_list}
                    )
                except Exception as e:
                    log(f"Failed to save alert to database: {e}", "WARNING")
            
            alert_count += 1
        
        stored_langs[package_id] = list(current_langs)
        
    except Exception as e:
        log(f"Error checking Play Store for {company} ({package_id}): {e}", "ERROR")
    
    return alert_count

def check_all_play_store(targets: List[Dict]) -> int:
    """Check all configured Play Store packages for new language support."""
    if not GPLAY_AVAILABLE:
        log("Play Store checks skipped (google-play-scraper not available)")
        return 0
    
    log("Starting Play Store language checks...")
    stored_langs = load_json(PLAY_STORE_LANGS_FILE)
    total_alerts = 0
    packages_checked = 0
    
    for target in targets:
        company = target.get("company", "Unknown")
        package_id = target.get("play_package")
        
        if not package_id:
            continue
        
        alerts = check_play_store_package(company, package_id, stored_langs)
        total_alerts += alerts
        packages_checked += 1
        time.sleep(REQUEST_DELAY * 2)
    
    save_json(PLAY_STORE_LANGS_FILE, stored_langs)
    log(f"Play Store checks complete. Checked {packages_checked} apps, found {total_alerts} alerts.")
    return total_alerts

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
                    f"RSS ALERT [{company}]:\n"
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
    """Check all configured RSS feeds (legacy, kept for backward compatibility)."""
    log("Starting RSS checks...")
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

def fetch_doc_page(url: str) -> Optional[Dict]:
    """Fetch a documentation URL and return parsed data including hreflang tags."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; LocalizationMonitor/1.0)"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        hreflang_tags = []
        for link in soup.find_all('link', rel='alternate'):
            hreflang = link.get('hreflang')
            href = link.get('href')
            if hreflang and href:
                hreflang_tags.append({"lang": hreflang, "href": href})
        
        for element in soup(['script', 'style', 'nav', 'header', 'footer']):
            element.decompose()
        
        text = soup.get_text(separator=' ', strip=True)
        
        return {
            "text": text,
            "hreflang_tags": hreflang_tags
        }
        
    except requests.RequestException as e:
        log(f"Error fetching doc URL {url}: {e}", "WARNING")
        return None

def fetch_doc_text(url: str) -> Optional[str]:
    """Fetch and extract clean text from a documentation URL (legacy wrapper)."""
    result = fetch_doc_page(url)
    return result["text"] if result else None

def check_doc_url(company: str, url: str, doc_hashes: Dict) -> int:
    """
    Check a documentation URL for hreflang changes (primary) and localization keywords (secondary).
    Returns the number of alerts generated.
    """
    alert_count = 0
    hash_key = f"{company}/{url}"
    hreflang_key = f"{company}/{url}/hreflang"
    
    try:
        page_data = fetch_doc_page(url)
        if not page_data:
            return 0
        
        current_text = page_data["text"]
        current_hreflangs = page_data["hreflang_tags"]
        
        current_hash = hashlib.md5(current_text.encode()).hexdigest()
        previous_hash = doc_hashes.get(hash_key)
        previous_hreflangs = doc_hashes.get(hreflang_key, [])
        
        previous_langs = set(h.get("lang", "") for h in previous_hreflangs if isinstance(h, dict))
        current_langs = set(h.get("lang", "") for h in current_hreflangs)
        new_langs = current_langs - previous_langs
        
        if new_langs and previous_hreflangs:
            signal_type = "NEW_HREFLANG"
            new_langs_list = list(new_langs)
            
            alert_msg = (
                f"DOCS [{signal_type}] [{company}]:\n"
                f"  New language versions detected!\n"
                f"  URL: {url}\n"
                f"  New languages: {', '.join(new_langs_list)}\n"
                f"  Total languages: {len(current_langs)}"
            )
            alert(alert_msg)
            
            if DB_AVAILABLE:
                try:
                    storage.save_alert(
                        source="docs",
                        company=company,
                        title=f"[{signal_type}] New regional site: {', '.join(new_langs_list)}",
                        message=f"New hreflang tags detected on {url[:60]}",
                        keywords=new_langs_list,
                        url=url,
                        metadata={"signal_type": signal_type, "new_langs": new_langs_list, "total_langs": len(current_langs)}
                    )
                except Exception as e:
                    log(f"Failed to save alert to database: {e}", "WARNING")
            
            alert_count += 1
        
        safe_filename = sanitize_filename(f"{company}_{url[:50]}")
        previous_text_path = os.path.join(PREVIOUS_TEXTS_DIR, f"{safe_filename}.txt")
        
        previous_text = ""
        if os.path.exists(previous_text_path):
            try:
                with open(previous_text_path, 'r', encoding='utf-8') as f:
                    previous_text = f.read()
            except IOError:
                pass
        
        if current_hash != previous_hash and alert_count == 0:
            matched_keywords = contains_keywords(current_text)
            
            if matched_keywords:
                new_keywords = []
                if previous_text:
                    previous_keywords = set(contains_keywords(previous_text))
                    new_keywords = [kw for kw in matched_keywords if kw not in previous_keywords]
                else:
                    new_keywords = matched_keywords
                
                if new_keywords or not previous_hash:
                    signal_type = "KEYWORD"
                    alert_msg = (
                        f"DOCS [{signal_type}] [{company}]:\n"
                        f"  Possible new localization content detected\n"
                        f"  URL: {url}\n"
                        f"  New keywords: {', '.join(new_keywords) if new_keywords else 'First scan - all found'}"
                    )
                    alert(alert_msg)
                    
                    if DB_AVAILABLE:
                        try:
                            storage.save_alert(
                                source="docs",
                                company=company,
                                title=f"[{signal_type}] Doc change: {url[:60]}",
                                message=f"New keywords: {', '.join(new_keywords) if new_keywords else 'First scan'}",
                                keywords=new_keywords if new_keywords else matched_keywords[:10],
                                url=url,
                                metadata={"signal_type": signal_type}
                            )
                        except Exception as e:
                            log(f"Failed to save alert to database: {e}", "WARNING")
                    
                    alert_count += 1
        
        doc_hashes[hash_key] = current_hash
        doc_hashes[hreflang_key] = current_hreflangs
        
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
    
    targets = get_targets()
    
    if current_time - last_github_check >= GITHUB_CHECK_INTERVAL:
        github_alerts = check_all_github(targets)
        last_github_check = current_time
    
    if current_time - last_rss_docs_check >= RSS_DOCS_CHECK_INTERVAL:
        rss_alerts = check_all_rss(targets)
        docs_alerts = check_all_docs(targets)
        last_rss_docs_check = current_time
    
    total_alerts = github_alerts + rss_alerts + docs_alerts
    if total_alerts > 0:
        log(f"Cycle complete. Total alerts this cycle: {total_alerts}")
    
    return last_github_check, last_rss_docs_check

def print_banner(targets: List[Dict]) -> None:
    """Print startup banner with configuration summary."""
    print("\n" + "="*60)
    print(" LOCALIZATION MONITORING APPLICATION")
    print(" Version 1.0")
    print("="*60)
    print(f"\nStarted at: {get_timestamp()}")
    print(f"\nMonitoring {len(targets)} target companies:")
    
    github_count = sum(1 for t in targets if t.get("github_repos"))
    playstore_count = sum(1 for t in targets if t.get("play_package"))
    docs_count = sum(1 for t in targets if t.get("doc_urls"))
    
    print(f"  - GitHub repos configured: {github_count} companies")
    print(f"  - Play Store apps configured: {playstore_count} companies")
    print(f"  - Doc pages configured: {docs_count} companies")
    print(f"  - Play Store scraper: {'Available' if GPLAY_AVAILABLE else 'Not available'}")
    
    print(f"\nCheck intervals:")
    print(f"  - GitHub: Every {GITHUB_CHECK_INTERVAL // 3600} hours")
    print(f"  - RSS/Docs: Every {RSS_DOCS_CHECK_INTERVAL // 3600} hours")
    
    github_token = get_github_access_token()
    slack_webhook = os.environ.get("SLACK_WEBHOOK")
    has_replit_connection = os.environ.get("REPLIT_CONNECTORS_HOSTNAME") is not None
    print(f"\nAuthentication configured:")
    if github_token:
        print(f"  - GitHub: Yes (via {'Replit connection' if has_replit_connection else 'token'})")
    else:
        print(f"  - GitHub: No (using anonymous access - lower rate limits)")
    print(f"  - SLACK_WEBHOOK: {'Yes' if slack_webhook else 'No (console only)'}")
    
    print("\n" + "="*60 + "\n")

def main() -> None:
    """Main entry point for the monitoring application."""
    targets = get_targets()
    print_banner(targets)
    ensure_directories()
    
    log("Running scheduled monitoring check...")
    
    try:
        github_alerts = check_all_github(targets)
        playstore_alerts = check_all_play_store(targets)
        docs_alerts = check_all_docs(targets)
        
        total_alerts = github_alerts + playstore_alerts + docs_alerts
        log(f"Monitoring complete. Total alerts: {total_alerts}")
        
    except Exception as e:
        log(f"Error during monitoring: {e}", "ERROR")
    
    log("Check finished. Exiting.")

if __name__ == "__main__":
    main()
