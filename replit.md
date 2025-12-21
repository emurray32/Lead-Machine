# Localization Monitoring Application

## Overview
A unified Python monitoring application that continuously tracks multiple target companies for early localization/phrase-string intent signals across three integrated sources:
- **GitHub Repositories**: Monitors commits for localization-related keywords
- **Google Play RSS Feeds**: Monitors app changelogs for new language support
- **API/Developer Docs**: Detects changes and scans for localization keywords

## Project Structure
- `main.py` - Main application with all monitoring logic
- `monitoring_data/` - Persisted state (JSON files for tracking seen commits, RSS entries, doc hashes)
- `.gitignore` - Ignores Python cache, virtual envs, and monitoring data

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

## Running
The app runs continuously via the "Localization Monitor" workflow. It will:
1. Check all configured GitHub repos for new commits with localization keywords
2. Parse any configured RSS feeds for language-related updates
3. Fetch and compare documentation pages for changes

## Recent Changes
- 2025-12-21: Initial implementation with 15 target companies
