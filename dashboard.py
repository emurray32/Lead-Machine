"""
Flask Web Dashboard for GitHub i18n Timeline Intelligence
Focused on tracking company internationalization journeys through GitHub activity.
Features discovery engine for proactive company suggestions.
"""

from flask import Flask, render_template, jsonify, request, Response
import storage
import os
import csv
import io
import yaml
import config
from datetime import datetime, timezone
from monitors import discovery

def friendly_time(dt):
    """Convert datetime to friendly format like '2 hours ago' or 'Dec 27'."""
    if not dt:
        return ''
    
    now = datetime.now()
    if dt.tzinfo:
        dt = dt.replace(tzinfo=None)
    
    diff = now - dt
    seconds = diff.total_seconds()
    
    if seconds < 0:
        return 'Just now'
    elif seconds < 60:
        return 'Just now'
    elif seconds < 3600:
        mins = int(seconds / 60)
        return f'{mins}m ago'
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f'{hours}h ago'
    elif seconds < 172800:
        return 'Yesterday'
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f'{days}d ago'
    else:
        return dt.strftime('%b %d')

try:
    import ai_summary
    AI_AVAILABLE = ai_summary.is_available()
except Exception:
    AI_AVAILABLE = False
    ai_summary = None

app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRET_KEY

storage.init_database()

def load_companies_yaml():
    """Load companies from YAML config file."""
    if not os.path.exists(config.COMPANIES_FILE):
        return []
    try:
        with open(config.COMPANIES_FILE, 'r') as f:
            yaml_config = yaml.safe_load(f)
        return yaml_config.get('companies', [])
    except Exception:
        return []

def save_companies_yaml(companies):
    """Save companies to YAML config file."""
    try:
        yaml_config = {'companies': companies}
        with open(config.COMPANIES_FILE, 'w') as f:
            f.write("# Localization Monitor - Company Configuration\n")
            f.write("# Edit this file or use the dashboard admin panel to add/remove companies\n\n")
            yaml.dump(yaml_config, f, default_flow_style=False, sort_keys=False)
        return True
    except Exception:
        return False

@app.route('/')
def index():
    """Main dashboard page - GitHub i18n focused."""
    company_filter = request.args.get('company', '')
    search_query = request.args.get('search', '')
    signal_type_filter = request.args.get('signal_type', '')

    alerts = storage.get_alerts(
        limit=500,
        source='github',
        company=company_filter if company_filter else None,
        search=search_query if search_query else None,
        signal_type=signal_type_filter if signal_type_filter else None
    )

    for alert in alerts:
        alert['friendly_time'] = friendly_time(alert.get('created_at'))

    companies_summary = storage.get_all_companies_summary()
    companies = [c['company'] for c in companies_summary]
    stats = storage.get_alert_stats()

    return render_template('dashboard.html',
                         alerts=alerts,
                         companies=companies,
                         companies_summary=companies_summary,
                         stats=stats,
                         current_company=company_filter,
                         ai_available=AI_AVAILABLE)

@app.route('/api/alerts')
def api_alerts():
    """API endpoint for alerts."""
    source = request.args.get('source')
    company = request.args.get('company')
    limit = request.args.get('limit', 100, type=int)
    
    alerts = storage.get_alerts(limit=limit, source=source, company=company)
    
    for alert in alerts:
        if alert.get('created_at'):
            alert['created_at'] = alert['created_at'].isoformat()
    
    return jsonify(alerts)

@app.route('/api/stats')
def api_stats():
    """API endpoint for statistics."""
    return jsonify(storage.get_alert_stats())

HIGH_VALUE_SIGNALS = ['NEW_LANG_FILE', 'NEW_HREFLANG', 'NEW_APP_LANG', 'OPEN_PR']

def filter_high_value_alerts(alerts: list) -> list:
    """Filter alerts to only include high-value signals."""
    filtered = []
    for alert in alerts:
        metadata = alert.get('metadata', {})
        if isinstance(metadata, dict):
            signal_type = metadata.get('signal_type', '')
            if signal_type in HIGH_VALUE_SIGNALS:
                filtered.append(alert)
    return filtered

@app.route('/export/csv')
def export_csv():
    """Export alerts as CSV file. Use ?high_value=true for CRM-ready leads."""
    source = request.args.get('source')
    company = request.args.get('company')
    high_value_only = request.args.get('high_value', '').lower() == 'true'
    
    alerts = storage.get_alerts(limit=10000, source=source, company=company)
    
    if high_value_only:
        alerts = filter_high_value_alerts(alerts)
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    if high_value_only:
        writer.writerow(['Time', 'Source', 'Company', 'Signal Type', 'Title', 'Message', 'Keywords', 'URL'])
        for alert in alerts:
            metadata = alert.get('metadata', {}) or {}
            writer.writerow([
                alert.get('created_at', '').strftime('%Y-%m-%d %H:%M:%S') if alert.get('created_at') else '',
                alert.get('source', ''),
                alert.get('company', ''),
                metadata.get('signal_type', '') if isinstance(metadata, dict) else '',
                alert.get('title', ''),
                alert.get('message', ''),
                alert.get('keywords', ''),
                alert.get('url', '')
            ])
    else:
        writer.writerow(['Time', 'Source', 'Company', 'Title', 'Message', 'Keywords', 'URL'])
        for alert in alerts:
            writer.writerow([
                alert.get('created_at', '').strftime('%Y-%m-%d %H:%M:%S') if alert.get('created_at') else '',
                alert.get('source', ''),
                alert.get('company', ''),
                alert.get('title', ''),
                alert.get('message', ''),
                alert.get('keywords', ''),
                alert.get('url', '')
            ])
    
    output.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'localization_leads_{timestamp}.csv' if high_value_only else f'localization_alerts_{timestamp}.csv'
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route('/export/json')
def export_json():
    """Export alerts as JSON file."""
    source = request.args.get('source')
    company = request.args.get('company')
    
    alerts = storage.get_alerts(limit=10000, source=source, company=company)
    
    for alert in alerts:
        if alert.get('created_at'):
            alert['created_at'] = alert['created_at'].isoformat()
    
    import json
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return Response(
        json.dumps(alerts, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename=localization_alerts_{timestamp}.json'}
    )

SIGNAL_EXPLANATIONS = {
    'NEW_LANG_FILE': {
        'title': 'New Language File',
        'description': 'A new translation file was added to the codebase',
        'value': 'HIGH',
        'meaning': 'The company is actively translating their product into a new language. This is strong evidence of expansion plans.'
    },
    'NEW_HREFLANG': {
        'title': 'New Regional Site',
        'description': 'A new regional website version was detected',
        'value': 'HIGH',
        'meaning': 'The company created a localized version of their website for a new region. This shows they are expanding into that market.'
    },
    'NEW_APP_LANG': {
        'title': 'New App Language',
        'description': 'A new language was added to their mobile app',
        'value': 'HIGH',
        'meaning': 'Their Android app now supports a new language. This means they are targeting users who speak that language.'
    },
    'KEYWORD': {
        'title': 'Keyword Match',
        'description': 'Localization-related keywords were found',
        'value': 'LOW',
        'meaning': 'Someone mentioned localization in their code or docs. This could mean they are planning to expand, but it could also be routine maintenance.'
    }
}

@app.route('/admin')
def admin():
    """Admin panel for managing companies."""
    companies = load_companies_yaml()
    return render_template('admin.html', 
                         companies=companies,
                         signal_explanations=SIGNAL_EXPLANATIONS)

@app.route('/api/companies', methods=['GET'])
def api_get_companies():
    """Get all monitored companies."""
    companies = load_companies_yaml()
    return jsonify(companies)

@app.route('/api/companies', methods=['POST'])
def api_add_company():
    """Add a new company to monitor."""
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'error': 'Company name is required'}), 400
    
    company = {
        'name': data['name']
    }
    if data.get('github_org'):
        company['github_org'] = data['github_org']
    if data.get('github_repos'):
        repos = [r.strip() for r in data['github_repos'].split(',') if r.strip()]
        if repos:
            company['github_repos'] = repos
    if data.get('play_package'):
        company['play_package'] = data['play_package']
    if data.get('doc_urls'):
        urls = [u.strip() for u in data['doc_urls'].split(',') if u.strip()]
        if urls:
            company['doc_urls'] = urls
    
    companies = load_companies_yaml()
    companies.append(company)
    
    if save_companies_yaml(companies):
        return jsonify({'success': True, 'company': company})
    return jsonify({'error': 'Failed to save'}), 500

@app.route('/api/companies/<name>', methods=['DELETE'])
def api_delete_company(name):
    """Delete a company from monitoring."""
    companies = load_companies_yaml()
    companies = [c for c in companies if c.get('name') != name]
    
    if save_companies_yaml(companies):
        return jsonify({'success': True})
    return jsonify({'error': 'Failed to save'}), 500

@app.route('/api/quick-scan', methods=['POST'])
def api_quick_scan():
    """Run a quick scan for a company without saving."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    results = {
        'company': data.get('name', 'Unknown'),
        'github': None,
        'playstore': None,
        'docs': None,
        'signals': []
    }
    
    import requests as http_requests
    
    if data.get('github_org'):
        try:
            org = data['github_org']
            url = f"https://api.github.com/orgs/{org}/repos?per_page=5&sort=updated"
            resp = http_requests.get(url, timeout=10)
            if resp.status_code == 200:
                repos = resp.json()
                results['github'] = {
                    'status': 'found',
                    'org': org,
                    'recent_repos': [r['name'] for r in repos[:5]]
                }
            else:
                results['github'] = {'status': 'not_found', 'error': f'Org not found or private'}
        except Exception as e:
            results['github'] = {'status': 'error', 'error': str(e)}
    
    if data.get('play_package'):
        try:
            from google_play_scraper import app as gplay_app
            package = data['play_package']
            app_info = gplay_app(package, lang='en', country='us')
            languages = app_info.get('descriptionTranslations', [])
            results['playstore'] = {
                'status': 'found',
                'title': app_info.get('title', 'Unknown'),
                'developer': app_info.get('developer', 'Unknown'),
                'languages_detected': len(languages) if languages else 'Unknown'
            }
        except Exception as e:
            results['playstore'] = {'status': 'not_found', 'error': str(e)}
    
    if data.get('doc_urls'):
        urls = [u.strip() for u in data['doc_urls'].split(',') if u.strip()]
        doc_results = []
        for url in urls[:3]:
            try:
                resp = http_requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                if resp.status_code == 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    hreflangs = []
                    for link in soup.find_all('link', rel='alternate'):
                        hl = link.get('hreflang')
                        if hl:
                            hreflangs.append(hl)
                    doc_results.append({
                        'url': url,
                        'status': 'accessible',
                        'hreflangs': hreflangs[:10]
                    })
                else:
                    doc_results.append({'url': url, 'status': 'error', 'code': resp.status_code})
            except Exception as e:
                doc_results.append({'url': url, 'status': 'error', 'error': str(e)})
        results['docs'] = doc_results
    
    return jsonify(results)

@app.route('/api/signal-explanations')
def api_signal_explanations():
    """Get explanations for signal types."""
    return jsonify(SIGNAL_EXPLANATIONS)

@app.route('/api/summarize', methods=['POST'])
def api_summarize():
    """Generate AI summary for an alert with full context."""
    if not AI_AVAILABLE or not ai_summary:
        return jsonify({'error': 'AI summaries not available', 'available': False}), 503
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    try:
        metadata = data.get('metadata', {}) or {}
        
        language_context = ai_summary.get_company_language_context(
            data.get('company', ''),
            metadata
        )
        
        reviewers = ai_summary.get_reviewers_from_metadata(metadata)
        
        summary = ai_summary.generate_alert_summary(
            source=data.get('source', ''),
            company=data.get('company', ''),
            title=data.get('title', ''),
            message=data.get('message', ''),
            keywords=data.get('keywords', []),
            signal_type=data.get('signal_type'),
            language_context=language_context,
            reviewers=reviewers
        )
        
        if summary:
            return jsonify({'summary': summary, 'available': True})
        return jsonify({'error': 'Failed to generate summary', 'available': True}), 500
        
    except Exception as e:
        return jsonify({'error': str(e), 'available': True}), 500

@app.route('/api/ai-status')
def api_ai_status():
    """Check if AI summaries are available."""
    return jsonify({'available': AI_AVAILABLE})


@app.route('/company/<company_name>')
def company_page(company_name):
    """Company detail page with i18n timeline and journey narrative."""
    timeline = storage.get_company_timeline(company_name)

    if not timeline:
        return render_template('company.html',
                             company_name=company_name,
                             timeline=[],
                             metrics={},
                             ai_available=AI_AVAILABLE,
                             not_found=True)

    for event in timeline:
        event['friendly_time'] = friendly_time(event.get('date'))

    metrics = storage.get_company_metrics(company_name)

    if metrics.get('first_seen'):
        metrics['first_seen_friendly'] = friendly_time(metrics['first_seen'])
    if metrics.get('last_activity'):
        metrics['last_activity_friendly'] = friendly_time(metrics['last_activity'])

    if timeline:
        first_date = timeline[0].get('date')
        last_date = timeline[-1].get('date')
        if first_date and last_date:
            days = (last_date - first_date).days
            if days > 365:
                metrics['journey_duration'] = f"{days // 365} year(s)"
            elif days > 30:
                metrics['journey_duration'] = f"{days // 30} month(s)"
            else:
                metrics['journey_duration'] = f"{days} days"

    return render_template('company.html',
                         company_name=company_name,
                         timeline=timeline,
                         metrics=metrics,
                         ai_available=AI_AVAILABLE,
                         not_found=False)


@app.route('/api/company/<company_name>/profile')
def api_company_profile(company_name):
    """Generate/refresh AI company profile."""
    if not AI_AVAILABLE or not ai_summary:
        return jsonify({'error': 'AI not available', 'available': False}), 503

    timeline = storage.get_company_timeline(company_name)
    if not timeline:
        return jsonify({'error': 'No data found for company'}), 404

    metrics = storage.get_company_metrics(company_name)

    try:
        alerts = storage.get_company_alerts(company_name)
        profile = ai_summary.generate_company_profile(company_name, alerts, metrics)
        if profile:
            return jsonify({'profile': profile, 'available': True})
        return jsonify({'error': 'Failed to generate profile', 'available': True}), 500
    except Exception as e:
        return jsonify({'error': str(e), 'available': True}), 500


@app.route('/api/company/<company_name>/journey')
def api_company_journey(company_name):
    """Generate AI narrative about the company's i18n journey."""
    if not AI_AVAILABLE or not ai_summary:
        return jsonify({'error': 'AI not available', 'available': False}), 503

    timeline = storage.get_company_timeline(company_name)
    if not timeline:
        return jsonify({'error': 'No data found for company'}), 404

    metrics = storage.get_company_metrics(company_name)

    try:
        narrative = ai_summary.generate_i18n_journey_narrative(company_name, timeline, metrics)
        if narrative:
            return jsonify({'narrative': narrative, 'available': True})
        return jsonify({'error': 'Failed to generate narrative', 'available': True}), 500
    except Exception as e:
        return jsonify({'error': str(e), 'available': True}), 500


# ============================================================
# DISCOVERY & SUGGESTIONS ROUTES
# ============================================================

@app.route('/discover')
def discover_page():
    """Discovery page with company suggestions."""
    companies = load_companies_yaml()
    cached = discovery.get_cached_suggestions()

    # Get quick suggestions
    suggestions = discovery.get_quick_suggestions(companies, limit=30)

    return render_template('discover.html',
                         suggestions=suggestions,
                         cached_data=cached,
                         companies_count=len(companies))


@app.route('/api/discover/suggestions')
def api_discover_suggestions():
    """Get discovery suggestions."""
    companies = load_companies_yaml()
    limit = request.args.get('limit', 20, type=int)
    category = request.args.get('category', '')

    suggestions = discovery.get_quick_suggestions(companies, limit=limit)

    if category:
        suggestions = [s for s in suggestions if s.get('category') == category]

    return jsonify({
        'suggestions': suggestions,
        'count': len(suggestions)
    })


@app.route('/api/discover/refresh', methods=['POST'])
def api_discover_refresh():
    """Run full discovery scan and refresh suggestions."""
    companies = load_companies_yaml()

    try:
        results = discovery.run_full_discovery(companies)
        return jsonify({
            'success': True,
            'trending': len(results.get('trending', [])),
            'similar': len(results.get('similar', [])),
            'pr_firehose': len(results.get('pr_firehose', [])),
            'expansions': len(results.get('expansions', [])),
            'dependencies': len(results.get('dependencies', [])),
            'last_updated': results.get('last_updated')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/discover/enrich/<org>')
def api_discover_enrich(org):
    """Auto-enrich company data for one-click follow."""
    try:
        enriched = discovery.enrich_company_data(org)
        return jsonify(enriched)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/discover/search')
def api_discover_search():
    """Smart search for companies."""
    query = request.args.get('q', '')
    limit = request.args.get('limit', 20, type=int)

    if not query or len(query) < 2:
        return jsonify({'results': [], 'suggestions': []})

    results = discovery.search_companies(query, limit=limit)
    suggestions = discovery.get_ai_search_suggestions(query)

    return jsonify({
        'results': results,
        'suggestions': suggestions,
        'query': query
    })


@app.route('/api/discover/trending')
def api_discover_trending():
    """Get trending i18n repos."""
    cached = discovery.get_cached_suggestions()
    trending = cached.get('trending', [])

    return jsonify({
        'trending': trending[:20],
        'count': len(trending)
    })


@app.route('/api/discover/firehose')
def api_discover_firehose():
    """Get recent i18n PRs from the firehose."""
    cached = discovery.get_cached_suggestions()
    firehose = cached.get('pr_firehose', [])

    return jsonify({
        'prs': firehose[:30],
        'count': len(firehose)
    })


@app.route('/api/discover/similar/<company>')
def api_discover_similar(company):
    """Get similar company suggestions."""
    similar = discovery.get_similar_companies(company)

    return jsonify({
        'company': company,
        'similar': similar,
        'count': len(similar)
    })


@app.route('/api/follow', methods=['POST'])
def api_follow_company():
    """One-click follow a suggested company."""
    data = request.get_json()
    if not data or not data.get('github_org'):
        return jsonify({'error': 'GitHub organization required'}), 400

    # Auto-enrich the company data
    enriched = discovery.enrich_company_data(data['github_org'])

    company = {
        'name': data.get('company_name') or enriched.get('company_name') or data['github_org'],
        'github_org': data['github_org']
    }

    # Add repos if discovered
    if enriched.get('github_repos'):
        company['github_repos'] = enriched['github_repos'][:5]
    elif data.get('repo_name'):
        company['github_repos'] = [data['repo_name']]

    # Add doc URLs if discovered
    if enriched.get('doc_urls'):
        company['doc_urls'] = enriched['doc_urls']

    # Load existing companies and check for duplicates
    companies = load_companies_yaml()
    existing_orgs = [c.get('github_org', '').lower() for c in companies]

    if company['github_org'].lower() in existing_orgs:
        return jsonify({'error': 'Company already being followed', 'exists': True}), 409

    companies.append(company)

    if save_companies_yaml(companies):
        return jsonify({
            'success': True,
            'company': company,
            'enriched': enriched
        })

    return jsonify({'error': 'Failed to save'}), 500


if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)
