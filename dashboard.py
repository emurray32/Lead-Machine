"""
Flask Web Dashboard for Localization Monitoring Alerts
"""

from flask import Flask, render_template, jsonify, request, Response
import storage
import os
import csv
import io
import yaml
from datetime import datetime, timezone

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
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

storage.init_database()

COMPANIES_FILE = "companies.yaml"

def load_companies_yaml():
    """Load companies from YAML config file."""
    if not os.path.exists(COMPANIES_FILE):
        return []
    try:
        with open(COMPANIES_FILE, 'r') as f:
            config = yaml.safe_load(f)
        return config.get('companies', [])
    except Exception:
        return []

def save_companies_yaml(companies):
    """Save companies to YAML config file."""
    try:
        config = {'companies': companies}
        with open(COMPANIES_FILE, 'w') as f:
            f.write("# Localization Monitor - Company Configuration\n")
            f.write("# Edit this file or use the dashboard admin panel to add/remove companies\n\n")
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        return True
    except Exception:
        return False

@app.route('/')
def index():
    """Main dashboard page."""
    source_filter = request.args.get('source', '')
    company_filter = request.args.get('company', '')
    
    alerts = storage.get_alerts(
        limit=100,
        source=source_filter if source_filter else None,
        company=company_filter if company_filter else None
    )
    
    for alert in alerts:
        alert['friendly_time'] = friendly_time(alert.get('created_at'))
    
    companies = storage.get_companies()
    stats = storage.get_alert_stats()
    
    return render_template('dashboard.html', 
                         alerts=alerts,
                         companies=companies,
                         stats=stats,
                         current_source=source_filter,
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

@app.route('/export/csv')
def export_csv():
    """Export alerts as CSV file."""
    source = request.args.get('source')
    company = request.args.get('company')
    
    alerts = storage.get_alerts(limit=10000, source=source, company=company)
    
    output = io.StringIO()
    writer = csv.writer(output)
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
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=localization_alerts_{timestamp}.csv'}
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
    """Generate AI summary for an alert."""
    if not AI_AVAILABLE or not ai_summary:
        return jsonify({'error': 'AI summaries not available', 'available': False}), 503
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    try:
        summary = ai_summary.generate_alert_summary(
            source=data.get('source', ''),
            company=data.get('company', ''),
            title=data.get('title', ''),
            message=data.get('message', ''),
            keywords=data.get('keywords', []),
            signal_type=data.get('signal_type')
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
