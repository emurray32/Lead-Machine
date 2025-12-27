# Localization Monitoring Application

## Overview
A unified Python monitoring application that tracks multiple target companies for early localization/phrase-string intent signals across three integrated sources:
- **GitHub Repositories**: Monitors for new localization files (primary) and keyword matches (secondary)
- **Google Play Store**: Compares app language lists over time to detect new language additions
- **API/Developer Docs**: Detects new hreflang tags (primary) and keyword changes (secondary)

## Signal Types
The monitor uses intelligent signal detection to reduce noise:

### High-Value Signals (Primary)
- **NEW_LANG_FILE**: New files added to localization directories (e.g., `locales/fr.json`)
- **NEW_HREFLANG**: New regional site versions detected via HTML hreflang tags
- **NEW_APP_LANG**: New languages added to Play Store app listings

### Secondary Signals
- **KEYWORD**: Keyword matches in commit messages or documentation (filtered for bots)

## Project Structure
- `main.py` - Main monitoring script with all detection logic
- `dashboard.py` - Flask web dashboard for viewing alerts
- `storage.py` - Database layer for persisting alerts to PostgreSQL
- `ai_summary.py` - Gemini Pro integration for AI-powered alert explanations
- `companies.yaml` - Company configuration file (edit via Admin Panel or directly)
- `templates/dashboard.html` - Dashboard UI template
- `templates/admin.html` - Admin panel template
- `monitoring_data/` - JSON files for tracking state between runs

## Web Dashboard
Access the dashboard at port 5000:
- Stats cards showing alerts by source (GitHub, Play Store, Documentation)
- Filterable table with signal type, company, details, and keywords
- **AI Explain button** - Get plain-English summaries of what each alert means
- Export to CSV or JSON
- Auto-refresh every 60 seconds
- Link to Admin Panel for managing companies

## Admin Panel
Access at `/admin` to:
- **Add new companies** to monitor with a simple form
- **Quick Scan** - Test a company before adding permanently
- **Remove companies** from monitoring
- **Signal explanations** - Understand what each signal type means

## Configuration

### Editing Companies
Two ways to manage monitored companies:
1. **Admin Panel**: Go to `/admin` and use the form (no code needed)
2. **YAML file**: Edit `companies.yaml` directly

Each company can have:
- `name`: Company name for display (required)
- `github_org`: GitHub organization name
- `github_repos`: List of repos to monitor
- `play_package`: Android package ID (e.g., `com.spotify.music`)
- `doc_urls`: List of documentation URLs to monitor

### Check Intervals
- GitHub: Every 6 hours (configurable via `GITHUB_CHECK_INTERVAL`)
- Play Store/Docs: Every 24 hours (configurable via `RSS_DOCS_CHECK_INTERVAL`)

## Filtering Logic
- **Bot Filtering**: Commits from dependabot, github-actions, and other bots are excluded
- **Localization Directories**: Monitors for file additions in `/locales`, `/i18n`, `/translations`, etc.
- **Language Detection**: Automatically extracts language codes from file paths (e.g., `fr`, `de`, `ja`)

## Authentication
- **GitHub**: Connected via Replit integration for higher rate limits (5000 requests/hour)
- **Gemini AI**: Connected via Replit AI Integrations for alert summaries
- **SLACK_WEBHOOK**: Optional for push notifications

## Workflows
- **Dashboard**: Runs the Flask web server on port 5000
- **Localization Monitor**: Runs the monitoring checks

## Recent Changes
- 2025-12-27: Added AI-powered alert summaries using Gemini Pro
- 2025-12-27: Added Admin Panel for managing companies without code
- 2025-12-27: Added Quick Scan feature to test companies before adding
- 2025-12-27: Created companies.yaml config file for easy company management
- 2025-12-27: Upgraded monitoring with structural change detection (file additions, hreflang parsing)
- 2025-12-27: Added bot filtering to exclude dependabot/automated commits
- 2025-12-27: Replaced RSS with Play Store language list comparison
- 2025-12-27: Added web dashboard with PostgreSQL alert storage
- 2025-12-21: Initial implementation with 15 target companies
