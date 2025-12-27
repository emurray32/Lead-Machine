"""
Flask Web Dashboard for Localization Monitoring Alerts
"""

from flask import Flask, render_template, jsonify, request, Response
import storage
import os
import csv
import io
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

storage.init_database()

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
    
    companies = storage.get_companies()
    stats = storage.get_alert_stats()
    
    from datetime import datetime
    return render_template('dashboard.html', 
                         alerts=alerts,
                         companies=companies,
                         stats=stats,
                         current_source=source_filter,
                         current_company=company_filter,
                         now=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
