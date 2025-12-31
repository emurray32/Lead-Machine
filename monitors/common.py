"""
Shared utilities and configuration for monitors.
"""

import os
import json
import time
import logging
import requests
from datetime import datetime
from typing import List, Dict, Optional, Any
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)



_github_connection_cache = {"settings": None, "expires_at": None}

def get_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(message: str, level: str = "INFO") -> None:
    """Legacy log function wrapper around logging module."""
    lvl = getattr(logging, level.upper(), logging.INFO)
    logger.log(lvl, message)

def alert(message: str) -> None:
    print(f"\n{'='*60}")
    print(f"[{get_timestamp()}] ALERT")
    print(message)
    print(f"{'='*60}\n")
    
    slack_webhook = config.SLACK_WEBHOOK
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
    os.makedirs(config.DATA_DIR, exist_ok=True)
    os.makedirs(config.PREVIOUS_TEXTS_DIR, exist_ok=True)

def load_json(filepath: str) -> Dict:
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            log(f"Error loading {filepath}: {e}", "WARNING")
    return {}

def save_json(filepath: str, data: Dict) -> None:
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        log(f"Error saving {filepath}: {e}", "ERROR")

def contains_keywords(text: str, keywords: List[str] = None) -> List[str]:
    if keywords is None:
        keywords = config.KEYWORDS
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]

def is_bot_author(author: str) -> bool:
    author_lower = author.lower()
    return any(bot.lower() in author_lower for bot in config.BOT_PATTERNS)

def is_localization_file(filepath: str) -> bool:
    filepath_lower = filepath.lower()
    in_l10n_dir = any(dir_pattern in filepath_lower for dir_pattern in config.LOCALIZATION_DIRS)
    has_l10n_ext = any(filepath_lower.endswith(ext) for ext in config.LOCALIZATION_FILE_PATTERNS)
    return in_l10n_dir and has_l10n_ext

def extract_language_from_file(filepath: str) -> Optional[str]:
    filepath_lower = filepath.lower()
    filename = os.path.basename(filepath_lower)
    name_without_ext = os.path.splitext(filename)[0]
    
    for code in config.LANGUAGE_CODES:
        if name_without_ext == code or name_without_ext.endswith(f"_{code}") or name_without_ext.endswith(f"-{code}"):
            return code
        if f"/{code}/" in filepath_lower or f"/{code}." in filepath_lower:
            return code
        if f"values-{code}" in filepath_lower:
            return code
    return None

def sanitize_filename(name: str) -> str:
    """Create a safe filename from a string."""
    return "".join(c if c.isalnum() or c in '-_' else '_' for c in name)

def get_github_access_token() -> Optional[str]:
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
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Localization-Monitor-Bot"
    }
    github_token = get_github_access_token()
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    return headers
