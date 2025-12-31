"""
Centralized configuration for the Localization Monitor.
"""
import os
import sys


# Database
DATABASE_URL = os.environ.get("DATABASE_URL")

# Secrets
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
SLACK_WEBHOOK = os.environ.get("SLACK_WEBHOOK")

# Monitoring Intervals (in seconds)
GITHUB_CHECK_INTERVAL = 6 * 60 * 60
RSS_DOCS_CHECK_INTERVAL = 24 * 60 * 60
MAIN_LOOP_SLEEP = 60
GITHUB_RATE_LIMIT_SLEEP = 60
REQUEST_DELAY = 1

# Files and Directories
DATA_DIR = "monitoring_data"
LAST_COMMITS_FILE = os.path.join(DATA_DIR, "last_commits.json")
SEEN_RSS_FILE = os.path.join(DATA_DIR, "seen_rss.json")
DOC_HASHES_FILE = os.path.join(DATA_DIR, "doc_hashes.json")
PLAY_STORE_LANGS_FILE = os.path.join(DATA_DIR, "play_store_langs.json")
PREVIOUS_TEXTS_DIR = os.path.join(DATA_DIR, "previous_texts")
WEBHOOKS_FILE = os.path.join(DATA_DIR, "webhooks.json")
COMPANIES_FILE = "companies.yaml"

# Constants
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

BOT_PATTERNS = [
    "[bot]", "dependabot", "github-actions", "renovate", "greenkeeper",
    "snyk-bot", "codecov", "semantic-release", "auto-merge"
]

LOCALIZATION_DIRS = [
    "locales/", "locale/", "i18n/", "l10n/", "translations/", "lang/",
    "languages/", "res/values-", "strings/", "messages/", "intl/"
]

LOCALIZATION_FILE_PATTERNS = [
    ".json", ".yaml", ".yml", ".properties", ".po", ".pot", ".xliff",
    ".strings", ".resx", ".arb"
]

LANGUAGE_CODES = [
    "ar", "zh", "cs", "da", "nl", "fi", "fr", "de", "el", "he", "hi",
    "hu", "id", "it", "ja", "ko", "ms", "no", "pl", "pt", "pt-br",
    "ro", "ru", "sk", "es", "sv", "th", "tr", "uk", "vi", "bn", "ta",
    "te", "mr", "gu", "kn", "ml", "pa", "sw", "zu", "af", "sq", "am",
    "hy", "az", "eu", "be", "bs", "bg", "ca", "hr", "et", "fil", "gl",
    "ka", "is", "lv", "lt", "mk", "mt", "mn", "ne", "fa", "sr", "si", "sl"
]


def validate_config() -> bool:
    """
    Validate that critical environment variables are configured.
    Returns True if all required config is present, False otherwise.
    Prints warnings for missing optional config.
    """
    warnings = []

    # Required for database operations
    if not DATABASE_URL:
        warnings.append("DATABASE_URL not set - alerts will only be logged to console")

    # Required for AI features
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("AI_INTEGRATIONS_GEMINI_API_KEY")
    if not gemini_key:
        warnings.append("GEMINI_API_KEY not set - AI summaries will be disabled")

    # Production security check
    if SECRET_KEY == 'dev-secret-key' and os.environ.get('FLASK_ENV') == 'production':
        warnings.append("Using default SECRET_KEY in production - this is a security risk")

    for warning in warnings:
        print(f"[CONFIG WARNING] {warning}", file=sys.stderr)

    return True
