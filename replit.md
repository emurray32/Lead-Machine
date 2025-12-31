# Localization Monitoring Application

## Overview
A unified Python monitoring application that tracks multiple target companies for early localization/phrase-string intent signals across three integrated sources:
- **GitHub Repositories**: Monitors for new localization files, commits, and open PRs
- **Google Play Store**: Compares app language lists over time to detect new language additions
- **API/Developer Docs**: Detects new hreflang tags and keyword changes

## Signal Types
The monitor uses intelligent signal detection to reduce noise:

### High-Value Signals (Primary)
- **NEW_LANG_FILE**: New files added to localization directories (e.g., `locales/fr.json`)
- **NEW_HREFLANG**: New regional site versions detected via HTML hreflang tags
- **NEW_APP_LANG**: New languages added to Play Store app listings
- **OPEN_PR**: Open pull requests with localization keywords (early intent signal)

### Secondary Signals
- **KEYWORD**: Keyword matches in commit messages or documentation (filtered for bots)

## Project Structure
```
.
├── main.py                 # Main orchestrator with parallel processing
├── dashboard.py            # Flask web dashboard
├── storage.py              # PostgreSQL database layer
├── ai_summary.py           # Gemini Pro AI summaries with language context
├── companies.yaml          # Company configuration
├── monitors/               # Modular monitor implementations
│   ├── __init__.py
│   ├── common.py           # Shared utilities
│   ├── github_monitor.py   # GitHub commits & PRs
│   ├── playstore_monitor.py # Play Store language tracking
│   ├── docs_monitor.py     # Documentation hreflang detection
│   └── webhooks.py         # Generic webhook system
├── templates/
│   ├── dashboard.html
│   └── admin.html
└── monitoring_data/        # State tracking JSON files
```

## Web Dashboard
Access the dashboard at port 5000:
- **Card-based layout** - Clean, scannable alerts
- **Friendly timestamps** - "1h ago", "Yesterday", "Dec 27"
- Stats bar showing alerts by source
- **AI Explain button** - Get plain-English summaries with language context
- **Export Leads** - CRM-ready export of high-value signals only
- **Export All** - Full alert dump
- Filter by source or company
- Auto-refresh every 2 minutes

## Admin Panel
Access at `/admin` to:
- **Add new companies** to monitor
- **Quick Scan** - Test a company before adding
- **Remove companies** from monitoring
- **Signal explanations** - Understand each signal type

## New Features (v2.1)

### Sales Intelligence Narratives
AI-powered "Explain" button generates rich sales narratives:
- "Walmart already supports 10 languages and just added French, signaling expansion into France or Canada"
- Includes geographic market context (language → target markets mapping)
- Shows PR reviewers as potential sales contacts
- Uses Gemini 2.5 Flash for contextual business intelligence

### Geo-Market Mapping
Automatic language-to-market inference:
- French → France, Canada (Quebec), Belgium, Switzerland
- Spanish → Spain, Latin America, Mexico, US Hispanic market
- Arabic → Middle East, North Africa, UAE, Saudi Arabia
- 40+ language mappings for accurate market targeting

### PR Reviewer Tracking
Captures PR reviewers as potential sales leads:
- Fetches assigned reviewers from GitHub API
- Shows reviewers in alert metadata
- AI narratives mention contacts by name

### Enhanced AI Context
AI summaries now include language count context:
- "This company already supports 20 languages and just added Arabic"
- Helps assess if expansion is major or niche

### Lead Export Filtering
Export only high-value signals for CRM import:
- `/export/csv?high_value=true` - Leads only
- `/export/csv` - All alerts

### Pull Request Monitoring
Detects open PRs with localization intent before they merge:
- Titles containing "translation", "localization", etc.
- Provides weeks of early notice

### Parallel Processing
Uses `concurrent.futures` for faster monitoring:
- GitHub repos checked in parallel (5 workers)
- All sources (GitHub, Play Store, Docs) run concurrently

### Generic Webhooks
Push alerts to external services:
```python
from monitors.webhooks import register_webhook

register_webhook(
    name="Zapier",
    url="https://hooks.zapier.com/...",
    events=["NEW_LANG_FILE", "NEW_APP_LANG"]
)
```

## Configuration

### Editing Companies
1. **Admin Panel**: `/admin` (no code needed)
2. **YAML file**: Edit `companies.yaml` directly

### Check Intervals
- GitHub: Every 6 hours
- Play Store/Docs: Every 24 hours

## Authentication
- **GitHub**: Connected via Replit integration
- **Gemini AI**: Connected via Replit AI Integrations
- **SLACK_WEBHOOK**: Optional for push notifications
- **Custom Webhooks**: Configure via `monitors/webhooks.py`

## Workflows
- **Dashboard**: Flask web server on port 5000
- **Localization Monitor**: Runs monitoring checks

## Company Pages
Access at `/company/<name>` for detailed company profiles:
- **AI Sales Intelligence Summary** - Comprehensive sales narrative generated by Gemini
- **Stats Grid** - Total signals, high-value signals, languages detected
- **Signal Timeline** - Full history of all detected localization activity
- **Key Contributors** - GitHub authors and reviewers as potential contacts
- Clickable company names on dashboard link to company pages

## Recent Changes
- 2025-12-31: Added Company Pages with AI-generated sales intelligence profiles
- 2025-12-31: Enhanced AI "Explain" to generate sales intelligence narratives
- 2025-12-31: Added geo-market mapping (40+ languages → target markets)
- 2025-12-31: Added PR reviewer tracking as potential sales contacts
- 2025-12-31: Updated AI model to Gemini 2.5 Flash
- 2025-12-28: Refactored monitors into modular `monitors/` directory
- 2025-12-28: Added parallel processing with concurrent.futures
- 2025-12-28: Added PR monitoring for early localization signals
- 2025-12-28: Added generic webhook system for Zapier/Make.com
- 2025-12-28: Added high-value lead export filtering for CRM
- 2025-12-28: Enhanced AI summaries with language count context
- 2025-12-27: Redesigned dashboard with card layout, friendly timestamps
- 2025-12-27: Added AI-powered alert summaries using Gemini Pro
- 2025-12-27: Added Admin Panel for managing companies
- 2025-12-27: Created companies.yaml config file
- 2025-12-21: Initial implementation with 15 target companies
