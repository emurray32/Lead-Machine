"""
AI Summary Service for Localization Alerts
Uses Gemini Pro to generate plain-English explanations of alerts.
Enhanced with company language context for richer summaries.
"""

import os
from typing import Optional, Dict, List

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
    'OPEN_PR': 'An open pull request with localization keywords was detected - this is an early signal before the change is merged.',
    'KEYWORD': 'Localization-related keywords were found in code or documentation.'
}

HIGH_VALUE_SIGNALS = ['NEW_LANG_FILE', 'NEW_HREFLANG', 'NEW_APP_LANG', 'OPEN_PR']


def generate_alert_summary(
    source: str,
    company: str,
    title: str,
    message: str,
    keywords: list,
    signal_type: str = None,
    language_context: Dict = None
) -> Optional[str]:
    """
    Generate a plain-English summary of an alert using Gemini Pro.
    
    Args:
        source: Alert source (github, playstore, docs)
        company: Company name
        title: Alert title
        message: Alert message
        keywords: Detected keywords
        signal_type: Type of signal detected
        language_context: Optional dict with 'current_count', 'previous_count', 'new_languages'
    
    Returns:
        Summary string or None if unavailable
    """
    if not GEMINI_AVAILABLE or not client:
        return None
    
    signal_info = ""
    if signal_type and signal_type in SIGNAL_CONTEXT:
        signal_info = f"Signal type context: {SIGNAL_CONTEXT[signal_type]}"
    
    language_info = ""
    if language_context:
        current = language_context.get('current_count', 0)
        previous = language_context.get('previous_count', 0)
        new_langs = language_context.get('new_languages', [])
        
        if current and previous:
            if current > 20:
                language_info = f"\nContext: This company already supports {previous} languages and just added {len(new_langs)} more ({', '.join(new_langs)}). With {current} languages, this is a mature global operation - this addition could be targeting a specific niche market."
            elif current > 10:
                language_info = f"\nContext: This company now supports {current} languages (up from {previous}). They're in active expansion mode - new languages indicate growing international revenue potential."
            else:
                language_info = f"\nContext: This company is early in their localization journey with {current} languages. Each new language is a significant investment signal."
    
    is_high_value = signal_type in HIGH_VALUE_SIGNALS
    priority_note = "\nThis is a HIGH-VALUE signal indicating concrete localization action." if is_high_value else ""
    
    prompt = f"""You are helping a business development person understand localization monitoring alerts.

Explain this alert in 1-2 simple sentences. Focus on what it means for their business - is this company expanding to new markets? Is this a sales opportunity?

Alert details:
- Company: {company}
- Source: {source}
- Title: {title}
- Details: {message}
- Keywords detected: {', '.join(keywords) if keywords else 'none'}
{signal_info}
{language_info}
{priority_note}

Write a brief, actionable explanation (1-2 sentences) of what this means and why it matters for a salesperson tracking localization opportunities."""

    try:
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


def get_company_language_context(company: str, metadata: Dict = None) -> Dict:
    """
    Extract language context from alert metadata.
    """
    if not metadata:
        return {}
    
    context = {}
    
    if 'total_langs' in metadata:
        context['current_count'] = metadata.get('total_langs', 0)
    if 'previous_lang_count' in metadata:
        context['previous_count'] = metadata.get('previous_lang_count', 0)
    if 'new_langs' in metadata:
        context['new_languages'] = metadata.get('new_langs', [])
    elif 'new_hreflangs' in metadata:
        context['new_languages'] = metadata.get('new_hreflangs', [])
    
    return context


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
        
        language_context = get_company_language_context(alert.get('company'), metadata)
        
        summary = generate_alert_summary(
            source=alert.get('source', ''),
            company=alert.get('company', ''),
            title=alert.get('title', ''),
            message=alert.get('message', ''),
            keywords=keywords,
            signal_type=signal_type,
            language_context=language_context
        )
        
        if summary:
            summaries[alert_id] = summary
    
    return summaries


def is_high_value_signal(signal_type: str) -> bool:
    """Check if a signal type is considered high-value."""
    return signal_type in HIGH_VALUE_SIGNALS


def is_available() -> bool:
    """Check if AI summary is available."""
    return GEMINI_AVAILABLE
