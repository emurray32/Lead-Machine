"""
AI Summary Service for Localization Alerts
Uses Gemini Pro to generate plain-English explanations of alerts.
"""

import os
from typing import Optional

try:
    from google import genai
    
    AI_INTEGRATIONS_GEMINI_API_KEY = os.environ.get("AI_INTEGRATIONS_GEMINI_API_KEY")
    AI_INTEGRATIONS_GEMINI_BASE_URL = os.environ.get("AI_INTEGRATIONS_GEMINI_BASE_URL")
    
    if AI_INTEGRATIONS_GEMINI_API_KEY and AI_INTEGRATIONS_GEMINI_BASE_URL:
        client = genai.Client(
            api_key=AI_INTEGRATIONS_GEMINI_API_KEY,
            http_options={"base_url": AI_INTEGRATIONS_GEMINI_BASE_URL}
        )
        GEMINI_AVAILABLE = True
    else:
        GEMINI_AVAILABLE = False
        client = None
except Exception as e:
    print(f"Gemini not available: {e}")
    GEMINI_AVAILABLE = False
    client = None

SIGNAL_CONTEXT = {
    'NEW_LANG_FILE': 'A new translation file was added to the codebase, indicating the company is actively translating their product.',
    'NEW_HREFLANG': 'A new regional website version was detected via hreflang tags, showing expansion to a new market.',
    'NEW_APP_LANG': 'A new language was added to their mobile app on the Play Store.',
    'KEYWORD': 'Localization-related keywords were found in code or documentation.'
}

def generate_alert_summary(
    source: str,
    company: str,
    title: str,
    message: str,
    keywords: list,
    signal_type: str = None
) -> Optional[str]:
    """
    Generate a plain-English summary of an alert using Gemini Pro.
    Returns None if AI is not available or fails.
    """
    if not GEMINI_AVAILABLE or not client:
        return None
    
    signal_info = ""
    if signal_type and signal_type in SIGNAL_CONTEXT:
        signal_info = f"Signal type context: {SIGNAL_CONTEXT[signal_type]}"
    
    prompt = f"""You are helping a non-technical business person understand localization monitoring alerts.

Explain this alert in 1-2 simple sentences that a non-technical person can understand. Focus on what it means for their business - is this company expanding to new markets?

Alert details:
- Company: {company}
- Source: {source}
- Title: {title}
- Details: {message}
- Keywords detected: {', '.join(keywords) if keywords else 'none'}
{signal_info}

Write a brief, clear explanation (1-2 sentences) of what this alert means and why it matters. Be specific about the company and what action they're taking."""

    try:
        # the newest Gemini model for this use case is gemini-2.5-pro
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt
        )
        
        if response and response.text:
            return response.text.strip()
        return None
        
    except Exception as e:
        print(f"Error generating summary: {e}")
        return None

def generate_batch_summaries(alerts: list) -> dict:
    """
    Generate summaries for a batch of alerts.
    Returns a dict mapping alert IDs to summaries.
    """
    if not GEMINI_AVAILABLE:
        return {}
    
    summaries = {}
    for alert in alerts[:10]:
        alert_id = alert.get('id')
        if not alert_id:
            continue
            
        metadata = alert.get('metadata', {}) or {}
        signal_type = metadata.get('signal_type') if isinstance(metadata, dict) else None
        keywords = alert.get('keywords', '').split(', ') if alert.get('keywords') else []
        
        summary = generate_alert_summary(
            source=alert.get('source', ''),
            company=alert.get('company', ''),
            title=alert.get('title', ''),
            message=alert.get('message', ''),
            keywords=keywords,
            signal_type=signal_type
        )
        
        if summary:
            summaries[alert_id] = summary
    
    return summaries

def is_available() -> bool:
    """Check if AI summary is available."""
    return GEMINI_AVAILABLE
