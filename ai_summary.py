"""
AI Summary Service for Localization Alerts
Uses Gemini to generate sales-oriented narratives about localization signals.
Enhanced with geo-market context and language inventory tracking.
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
            http_options={
                'api_version': '',
                'base_url': AI_INTEGRATIONS_GEMINI_BASE_URL
            }
        )
        GEMINI_AVAILABLE = True
    else:
        GEMINI_AVAILABLE = False
        client = None
except Exception as e:
    print(f"Gemini not available: {e}")
    GEMINI_AVAILABLE = False
    client = None

LANGUAGE_TO_MARKETS = {
    'fr': ['France', 'Canada (Quebec)', 'Belgium', 'Switzerland'],
    'french': ['France', 'Canada (Quebec)', 'Belgium', 'Switzerland'],
    'es': ['Spain', 'Latin America', 'Mexico', 'US Hispanic market'],
    'spanish': ['Spain', 'Latin America', 'Mexico', 'US Hispanic market'],
    'de': ['Germany', 'Austria', 'Switzerland'],
    'german': ['Germany', 'Austria', 'Switzerland'],
    'pt': ['Portugal', 'Brazil'],
    'pt-br': ['Brazil'],
    'portuguese': ['Portugal', 'Brazil'],
    'zh': ['China', 'Taiwan', 'Singapore'],
    'chinese': ['China', 'Taiwan', 'Singapore'],
    'ja': ['Japan'],
    'japanese': ['Japan'],
    'ko': ['South Korea'],
    'korean': ['South Korea'],
    'ar': ['Middle East', 'North Africa', 'UAE', 'Saudi Arabia'],
    'arabic': ['Middle East', 'North Africa', 'UAE', 'Saudi Arabia'],
    'hi': ['India'],
    'hindi': ['India'],
    'it': ['Italy', 'Switzerland'],
    'italian': ['Italy', 'Switzerland'],
    'nl': ['Netherlands', 'Belgium'],
    'dutch': ['Netherlands', 'Belgium'],
    'ru': ['Russia', 'Eastern Europe', 'CIS countries'],
    'russian': ['Russia', 'Eastern Europe', 'CIS countries'],
    'tr': ['Turkey'],
    'turkish': ['Turkey'],
    'pl': ['Poland'],
    'polish': ['Poland'],
    'vi': ['Vietnam'],
    'vietnamese': ['Vietnam'],
    'th': ['Thailand'],
    'thai': ['Thailand'],
    'id': ['Indonesia'],
    'indonesian': ['Indonesia'],
    'ms': ['Malaysia', 'Singapore'],
    'malay': ['Malaysia', 'Singapore'],
    'sv': ['Sweden'],
    'swedish': ['Sweden'],
    'no': ['Norway'],
    'norwegian': ['Norway'],
    'da': ['Denmark'],
    'danish': ['Denmark'],
    'fi': ['Finland'],
    'finnish': ['Finland'],
    'he': ['Israel'],
    'hebrew': ['Israel'],
    'uk': ['Ukraine'],
    'ukrainian': ['Ukraine'],
    'cs': ['Czech Republic'],
    'czech': ['Czech Republic'],
    'ro': ['Romania'],
    'romanian': ['Romania'],
    'hu': ['Hungary'],
    'hungarian': ['Hungary'],
    'el': ['Greece'],
    'greek': ['Greece'],
    'bn': ['Bangladesh', 'India (Bengal)'],
    'bengali': ['Bangladesh', 'India (Bengal)'],
    'ta': ['India (Tamil Nadu)', 'Sri Lanka', 'Singapore'],
    'tamil': ['India (Tamil Nadu)', 'Sri Lanka', 'Singapore'],
}

def get_market_context(languages: List[str]) -> str:
    """Get geographic market context for detected languages."""
    if not languages:
        return ""
    
    markets = []
    for lang in languages:
        lang_lower = lang.lower().strip()
        if lang_lower in LANGUAGE_TO_MARKETS:
            markets.extend(LANGUAGE_TO_MARKETS[lang_lower])
    
    if markets:
        unique_markets = list(dict.fromkeys(markets))
        return f"Target markets: {', '.join(unique_markets[:4])}"
    return ""

SIGNAL_CONTEXT = {
    'NEW_LANG_FILE': 'A new translation file was added to the codebase, indicating the company is actively translating their product.',
    'NEW_HREFLANG': 'A new regional website version was detected via hreflang tags, showing expansion to a new market.',
    'NEW_APP_LANG': 'A new language was added to their mobile app on the Play Store.',
    'OPEN_PR': 'An open pull request with localization keywords was detected - this is an early signal before the change is merged.',
    'KEYWORD': 'Localization-related keywords were found in code or documentation.'
}


def generate_alert_summary(
    source: str,
    company: str,
    title: str,
    message: str,
    keywords: list,
    signal_type: str = None,
    language_context: Dict = None,
    reviewers: List[str] = None
) -> Optional[str]:
    """
    Generate a sales-oriented narrative about a localization alert.
    
    Args:
        source: Alert source (github, playstore, docs)
        company: Company name
        title: Alert title
        message: Alert message
        keywords: Detected keywords (often language codes or names)
        signal_type: Type of signal detected
        language_context: Optional dict with 'current_count', 'previous_count', 'new_languages'
        reviewers: Optional list of PR reviewer usernames (potential contacts)
    
    Returns:
        Sales narrative string or None if unavailable
    """
    if not GEMINI_AVAILABLE or not client:
        return None
    
    signal_info = ""
    if signal_type and signal_type in SIGNAL_CONTEXT:
        signal_info = f"Signal type: {signal_type} - {SIGNAL_CONTEXT[signal_type]}"
    
    market_context = get_market_context(keywords)
    
    language_info = ""
    if language_context:
        current = language_context.get('current_count', 0)
        previous = language_context.get('previous_count', 0)
        new_langs = language_context.get('new_languages', [])
        
        if current and previous and new_langs:
            lang_list = ', '.join(new_langs[:3])
            if current > 20:
                language_info = f"Language inventory: This company already supports {previous} languages and just added {lang_list}. With {current} total languages, they're a mature global operation - this addition likely targets a specific high-value market."
            elif current > 10:
                language_info = f"Language inventory: Now at {current} languages (was {previous}), adding {lang_list}. Active expansion phase - strong localization investment appetite."
            else:
                language_info = f"Language inventory: Growing from {previous} to {current} languages with {lang_list}. Early-stage internationalization - each new language is a significant commitment."
        elif new_langs:
            language_info = f"New languages detected: {', '.join(new_langs[:3])}"
    
    reviewer_info = ""
    if reviewers and len(reviewers) > 0:
        reviewer_info = f"Potential contacts: {', '.join(reviewers[:3])} (PR reviewers who can discuss localization needs)"

    is_high_value = signal_type in config.HIGH_VALUE_SIGNALS
    priority_note = "PRIORITY: High-value signal - concrete action, not just discussion." if is_high_value else ""
    
    prompt = f"""You are a sales intelligence analyst helping a localization services salesperson understand market expansion signals.

Generate a 2-3 sentence sales narrative about this alert. Be specific about:
1. What the company is doing (adding French translation, expanding to Japan, etc.)
2. What markets this suggests they're targeting
3. Why this is a sales opportunity

Company: {company}
Source: {source}
Alert: {title}
Details: {message}
Languages/Keywords: {', '.join(keywords) if keywords else 'unknown'}
{signal_info}
{market_context}
{language_info}
{reviewer_info}
{priority_note}

Write a compelling 2-3 sentence narrative like: "{company} already supports X languages and has just added [language], signaling expansion into [specific markets]. This indicates [business insight]. [Call to action or opportunity assessment]."

Be specific and actionable. Use the language and market data provided."""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
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
    if 'lang_count' in metadata:
        context['current_count'] = metadata.get('lang_count', 0)
    if 'new_langs' in metadata:
        context['new_languages'] = metadata.get('new_langs', [])
    elif 'new_hreflangs' in metadata:
        context['new_languages'] = metadata.get('new_hreflangs', [])
    elif 'detected_languages' in metadata:
        context['new_languages'] = metadata.get('detected_languages', [])
    
    return context


def get_reviewers_from_metadata(metadata: Dict = None) -> List[str]:
    """
    Extract reviewer usernames from alert metadata.
    """
    if not metadata:
        return []
    
    reviewers = []
    
    if 'reviewers' in metadata:
        reviewers = metadata.get('reviewers', [])
    if 'author' in metadata and metadata.get('author'):
        author = metadata.get('author')
        if author not in reviewers:
            reviewers.append(author)
    
    return reviewers


def generate_batch_summaries(alerts: list) -> dict:
    """
    Generate summaries for a batch of alerts.
    Returns a dict mapping alert IDs to summaries.
    """
    if not GEMINI_AVAILABLE:
        return {}
    
    summaries = {}
    for alert in alerts[:config.MAX_ALERTS_AI_SUMMARY]:
        alert_id = alert.get('id')
        if not alert_id:
            continue
            
        metadata = alert.get('metadata', {}) or {}
        signal_type = metadata.get('signal_type') if isinstance(metadata, dict) else None
        keywords = alert.get('keywords', '').split(', ') if alert.get('keywords') else []
        
        language_context = get_company_language_context(alert.get('company'), metadata)
        reviewers = get_reviewers_from_metadata(metadata)
        
        summary = generate_alert_summary(
            source=alert.get('source', ''),
            company=alert.get('company', ''),
            title=alert.get('title', ''),
            message=alert.get('message', ''),
            keywords=keywords,
            signal_type=signal_type,
            language_context=language_context,
            reviewers=reviewers
        )
        
        if summary:
            summaries[alert_id] = summary
    
    return summaries


def is_high_value_signal(signal_type: str) -> bool:
    """Check if a signal type is considered high-value."""
    return signal_type in config.HIGH_VALUE_SIGNALS


def is_available() -> bool:
    """Check if AI summary is available."""
    return GEMINI_AVAILABLE


def generate_company_profile(company: str, alerts: List[Dict], metrics: Dict) -> Optional[str]:
    """
    Generate a comprehensive company profile summary based on all their alerts.
    Provides sales intelligence about their localization maturity and market expansion.
    """
    if not GEMINI_AVAILABLE or not client:
        return None

    if not alerts:
        return None

    total_alerts = metrics.get('total_alerts', len(alerts))
    github_count = metrics.get('github_count', 0)

    detected_languages = metrics.get('detected_languages', [])
    contributors = metrics.get('contributors', [])
    signal_types = metrics.get('signal_types', [])

    recent_alerts = alerts[:10]
    alert_summaries = []
    for alert in recent_alerts:
        signal_type = alert.get('metadata', {}).get('signal_type', '') if alert.get('metadata') else ''
        title = alert.get('title', '')[:100]
        alert_summaries.append(f"- [{signal_type}] {title}")

    market_context = get_market_context(detected_languages)

    lang_list = ', '.join(detected_languages[:10]) if detected_languages else 'Unknown'
    contributor_list = ', '.join(contributors[:5]) if contributors else 'No contributors tracked'

    maturity_assessment = ""
    if total_alerts > 20:
        maturity_assessment = "Very active in localization with frequent updates."
    elif total_alerts > 10:
        maturity_assessment = "Regularly investing in localization."
    elif total_alerts > 3:
        maturity_assessment = "Growing localization footprint."
    else:
        maturity_assessment = "Early stage in localization journey."

    high_value_count = sum(1 for a in alerts if a.get('metadata', {}).get('signal_type') in config.HIGH_VALUE_SIGNALS)

    prompt = f"""You are a sales intelligence analyst helping understand a company's internationalization journey based on their GitHub activity.

Generate a comprehensive 3-4 paragraph profile for {company} based on their i18n/localization GitHub activity. Include:

1. **Executive Summary**: Overall assessment of their internationalization maturity and what their GitHub activity reveals about their global expansion strategy
2. **Market Expansion Analysis**: What markets they're targeting based on detected languages and the order they added them
3. **Team Focus**: What the engineering team is prioritizing based on commit patterns
4. **Opportunity Assessment**: Why this company is interesting from an i18n perspective

Company Data:
- Total GitHub Signals: {total_alerts}
- High-Value Signals (new language files, PRs): {high_value_count}
- Languages Detected: {lang_list}
- {market_context}
- Key Contributors: {contributor_list}
- Maturity: {maturity_assessment}
- Signal Types: {', '.join(signal_types) if signal_types else 'Various'}

Recent Activity:
{chr(10).join(alert_summaries)}

Write a professional analysis focused on understanding their internationalization journey and team priorities."""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        if response and response.text:
            return response.text.strip()
        return None

    except Exception as e:
        print(f"Error generating company profile: {e}")
        return None


def generate_i18n_journey_narrative(company: str, timeline: List[Dict], metrics: Dict) -> Optional[str]:
    """
    Generate a narrative about a company's internationalization journey based on their timeline.
    """
    if not GEMINI_AVAILABLE or not client:
        return None

    if not timeline:
        return None

    detected_languages = metrics.get('detected_languages', [])
    contributors = metrics.get('contributors', [])

    timeline_events = []
    for event in timeline[:15]:
        date_str = event['date'].strftime('%b %Y') if event.get('date') else 'Unknown'
        signal = event.get('signal_type', 'UNKNOWN')
        langs = ', '.join(event.get('languages_added', [])) if event.get('languages_added') else ''
        author = event.get('author', 'Unknown')

        if signal == 'NEW_LANG_FILE' and langs:
            timeline_events.append(f"- {date_str}: Added {langs} language files (by {author})")
        elif signal == 'OPEN_PR':
            timeline_events.append(f"- {date_str}: Opened i18n PR #{event.get('pr_number', '?')} (by {author})")
        elif signal == 'KEYWORD':
            timeline_events.append(f"- {date_str}: i18n-related commit (by {author})")

    market_context = get_market_context(detected_languages)
    first_event = timeline[0] if timeline else None
    last_event = timeline[-1] if timeline else None

    duration = ""
    if first_event and last_event and first_event.get('date') and last_event.get('date'):
        days = (last_event['date'] - first_event['date']).days
        if days > 365:
            duration = f"over {days // 365} year(s)"
        elif days > 30:
            duration = f"over {days // 30} month(s)"
        else:
            duration = f"{days} days"

    prompt = f"""You are analyzing {company}'s internationalization journey based on their GitHub commit history.

Write a compelling 2-3 paragraph narrative about their i18n journey. Include:
1. How their internationalization started and evolved
2. What markets they seem to be prioritizing
3. The pace and pattern of their expansion
4. What this tells us about their global strategy

Timeline of i18n Events:
{chr(10).join(timeline_events) if timeline_events else 'Limited activity detected'}

Summary Data:
- Journey Duration: {duration}
- Total Languages Added: {len(detected_languages)}
- Languages: {', '.join(detected_languages[:10]) if detected_languages else 'Unknown'}
- {market_context}
- Key Contributors: {', '.join(contributors[:5]) if contributors else 'Unknown'}

Write an insightful narrative that tells the story of their internationalization journey. Focus on patterns and what this reveals about their strategy."""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        if response and response.text:
            return response.text.strip()
        return None

    except Exception as e:
        print(f"Error generating i18n journey narrative: {e}")
        return None
