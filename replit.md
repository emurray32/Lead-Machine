# Localization Monitoring Application

## Overview
A unified Python monitoring application that continuously tracks multiple target companies for early localization/phrase-string intent signals across three integrated sources:
- **GitHub Repositories**: Monitors commits for localization-related keywords
- **Google Play RSS Feeds**: Monitors app changelogs for new language support
- **API/Developer Docs**: Detects changes and scans for localization keywords

## Project Structure
- `main.py` - Main monitoring script that checks sources and saves alerts
- `dashboard.py` - Flask web dashboard for viewing alerts
- `storage.py` - Database layer for persisting alerts to PostgreSQL
- `templates/dashboard.html` - Dashboard UI template
- `monitoring_data/` - JSON files for tracking seen commits, RSS entries, doc hashes

## Web Dashboard
Access the dashboard at port 5000 to view all detected alerts with:
- Stats cards showing total alerts by source
- Filterable table with time, source, company, details, keywords, and links
- Auto-refresh every 60 seconds

## Configuration

### Editing Targets
Edit the `TARGETS` list in `main.py` to add/remove companies. Each entry can have:
- `company`: Company name for display
- `github_org`: GitHub organization name
- `github_repos`: List of repos to monitor
- `play_package`: Android package name (for reference)
- `rss_url`: RSS feed URL for Play Store updates
- `doc_urls`: List of documentation URLs to monitor

### Keywords
Edit the `KEYWORDS` list to customize what localization terms to search for.

### Check Intervals
- GitHub: Every 6 hours (configurable via `GITHUB_CHECK_INTERVAL`)
- RSS/Docs: Every 24 hours (configurable via `RSS_DOCS_CHECK_INTERVAL`)

## Optional Secrets
Add these in the Secrets tab for enhanced functionality:
- `GITHUB_TOKEN`: GitHub personal access token for higher API rate limits
- `SLACK_WEBHOOK`: Slack incoming webhook URL for notifications

## Workflows
- **Dashboard**: Runs the Flask web server on port 5000
- **Localization Monitor**: Runs the monitoring checks (can be run manually or scheduled)

## Deployment
- **Dashboard**: Configured for autoscale web deployment
- **Monitor**: Run as a scheduled task or manually trigger

## Recent Changes
- 2025-12-27: Added web dashboard with PostgreSQL alert storage
- 2025-12-21: Initial implementation with 15 target companies
