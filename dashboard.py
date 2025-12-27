"""
Flask Web Dashboard for Localization Monitoring Alerts
"""

from flask import Flask, render_template, jsonify, request
import storage
import os

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
    
    return render_template('dashboard.html', 
                         alerts=alerts,
                         companies=companies,
                         stats=stats,
                         current_source=source_filter,
                         current_company=company_filter)

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
