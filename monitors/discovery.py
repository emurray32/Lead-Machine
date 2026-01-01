"""
GitHub i18n Discovery Engine
Proactively discovers repos, companies, and i18n signals across GitHub.
Features:
- Trending i18n repos
- Similar company recommendations
- Dependency graph discovery
- Global PR firehose
- Auto-enrichment
- Language expansion alerts
- Smart search with AI suggestions
"""

import os
import time
import json
import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from .common import (
    log, get_headers, is_localization_file, extract_language_from_file,
    contains_keywords, load_json, save_json
)

# Industry taxonomy for similar company recommendations
INDUSTRY_TAXONOMY = {
    'fintech': {
        'keywords': ['payment', 'bank', 'finance', 'money', 'credit', 'wallet', 'trading'],
        'companies': ['stripe', 'square', 'paypal', 'plaid', 'wise', 'revolut', 'robinhood', 'coinbase', 'brex', 'affirm'],
    },
    'e-commerce': {
        'keywords': ['shop', 'store', 'commerce', 'retail', 'marketplace', 'cart'],
        'companies': ['shopify', 'bigcommerce', 'woocommerce', 'magento', 'etsy', 'ebay', 'amazon'],
    },
    'streaming': {
        'keywords': ['video', 'stream', 'media', 'music', 'entertainment', 'content'],
        'companies': ['netflix', 'spotify', 'hulu', 'twitch', 'vimeo', 'soundcloud', 'tidal'],
    },
    'delivery': {
        'keywords': ['delivery', 'food', 'logistics', 'courier', 'shipping'],
        'companies': ['doordash', 'uber', 'lyft', 'instacart', 'postmates', 'grubhub', 'deliveroo'],
    },
    'travel': {
        'keywords': ['travel', 'hotel', 'booking', 'flight', 'vacation', 'rental'],
        'companies': ['airbnb', 'booking', 'expedia', 'tripadvisor', 'vrbo', 'kayak'],
    },
    'communication': {
        'keywords': ['chat', 'message', 'video call', 'communication', 'collaborate'],
        'companies': ['slack', 'discord', 'zoom', 'twilio', 'sendgrid', 'intercom', 'zendesk'],
    },
    'developer_tools': {
        'keywords': ['api', 'sdk', 'developer', 'platform', 'infrastructure', 'cloud'],
        'companies': ['github', 'gitlab', 'atlassian', 'vercel', 'netlify', 'heroku', 'digitalocean'],
    },
    'social': {
        'keywords': ['social', 'network', 'community', 'connect', 'share'],
        'companies': ['twitter', 'meta', 'linkedin', 'reddit', 'pinterest', 'snapchat'],
    },
    'productivity': {
        'keywords': ['productivity', 'workspace', 'document', 'collaborate', 'project'],
        'companies': ['notion', 'airtable', 'asana', 'monday', 'clickup', 'figma', 'miro'],
    },
    'security': {
        'keywords': ['security', 'auth', 'identity', 'encryption', 'protection'],
        'companies': ['okta', 'auth0', '1password', 'cloudflare', 'crowdstrike', 'datadog'],
    },
}

# Popular i18n libraries to track
I18N_LIBRARIES = [
    'i18next', 'react-intl', 'formatjs', 'vue-i18n', 'ngx-translate',
    'polyglot.js', 'messageformat', 'globalize', 'gettext', 'fluent',
    'typesafe-i18n', 'lingui', 'rosetta', 'next-intl', 'paraglide-js'
]

# Discovery data cache file
DISCOVERY_CACHE_FILE = os.path.join(config.DATA_DIR, "discovery_cache.json")
SUGGESTIONS_FILE = os.path.join(config.DATA_DIR, "suggestions.json")


def get_github_headers():
    """Get headers for GitHub API requests."""
    headers = {'Accept': 'application/vnd.github.v3+json'}
    github_token = os.environ.get('GITHUB_TOKEN')
    if github_token:
        headers['Authorization'] = f'token {github_token}'
    return headers


# ============================================================
# 1. TRENDING I18N REPOS
# ============================================================

def search_trending_i18n_repos(days: int = 7, min_stars: int = 100) -> List[Dict]:
    """
    Search for trending repos with recent i18n activity.
    Uses GitHub search API to find repos with localization-related commits.
    """
    results = []
    date_threshold = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    # Search queries for i18n-related activity
    search_queries = [
        f'locales language:JSON pushed:>{date_threshold} stars:>{min_stars}',
        f'i18n translation pushed:>{date_threshold} stars:>{min_stars}',
        f'path:locales pushed:>{date_threshold} stars:>{min_stars}',
        f'path:translations pushed:>{date_threshold} stars:>{min_stars}',
    ]

    seen_repos = set()

    for query in search_queries:
        try:
            url = "https://api.github.com/search/repositories"
            params = {
                'q': query,
                'sort': 'updated',
                'order': 'desc',
                'per_page': 30
            }

            response = requests.get(url, headers=get_github_headers(), params=params, timeout=30)

            if response.status_code == 403:
                log("GitHub rate limit hit for trending search", "WARNING")
                time.sleep(60)
                continue

            if response.status_code == 200:
                data = response.json()
                for repo in data.get('items', []):
                    repo_key = repo['full_name']
                    if repo_key not in seen_repos:
                        seen_repos.add(repo_key)
                        results.append({
                            'full_name': repo['full_name'],
                            'name': repo['name'],
                            'owner': repo['owner']['login'],
                            'description': repo.get('description', ''),
                            'stars': repo['stargazers_count'],
                            'language': repo.get('language', ''),
                            'url': repo['html_url'],
                            'updated_at': repo['updated_at'],
                            'topics': repo.get('topics', []),
                            'source': 'trending'
                        })

            time.sleep(config.REQUEST_DELAY)

        except Exception as e:
            log(f"Error in trending search: {e}", "WARNING")

    # Sort by stars
    results.sort(key=lambda x: x['stars'], reverse=True)
    return results[:50]


def get_repo_i18n_signals(owner: str, repo: str) -> Dict:
    """
    Analyze a repo for i18n signals - check if it has localization files.
    Returns signal strength and detected languages.
    """
    signals = {
        'has_locales': False,
        'languages': [],
        'i18n_files': [],
        'signal_strength': 0
    }

    try:
        # Check repo contents for common i18n paths
        i18n_paths = ['locales', 'locale', 'i18n', 'translations', 'lang', 'languages']

        for path in i18n_paths:
            url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
            response = requests.get(url, headers=get_github_headers(), timeout=15)

            if response.status_code == 200:
                signals['has_locales'] = True
                contents = response.json()

                for item in contents:
                    if item['type'] == 'file':
                        filename = item['name']
                        signals['i18n_files'].append(filename)
                        lang = extract_language_from_file(filename)
                        if lang and lang not in signals['languages']:
                            signals['languages'].append(lang)

                signals['signal_strength'] = min(len(signals['languages']) * 10, 100)
                break

            time.sleep(0.5)

    except Exception as e:
        log(f"Error checking i18n signals for {owner}/{repo}: {e}", "WARNING")

    return signals


def discover_trending_i18n_companies() -> List[Dict]:
    """
    Main function to discover trending repos with i18n activity.
    Returns list of company suggestions.
    """
    log("Discovering trending i18n repos...")

    trending_repos = search_trending_i18n_repos()
    suggestions = []

    for repo in trending_repos[:20]:
        # Get detailed i18n signals
        signals = get_repo_i18n_signals(repo['owner'], repo['name'])

        if signals['has_locales'] or signals['signal_strength'] > 0:
            suggestions.append({
                'company_name': repo['owner'],
                'github_org': repo['owner'],
                'repo_name': repo['name'],
                'full_name': repo['full_name'],
                'description': repo['description'],
                'stars': repo['stars'],
                'languages_detected': signals['languages'],
                'i18n_files': signals['i18n_files'][:10],
                'signal_strength': signals['signal_strength'],
                'url': repo['url'],
                'source': 'trending',
                'reason': f"Trending repo with {len(signals['languages'])} languages detected"
            })

        time.sleep(config.REQUEST_DELAY)

    log(f"Found {len(suggestions)} trending i18n repos")
    return suggestions


# ============================================================
# 2. SIMILAR COMPANIES RECOMMENDATIONS
# ============================================================

def get_company_industry(company_name: str, github_org: str = None) -> Optional[str]:
    """
    Determine a company's industry based on their name, org, and repo topics.
    """
    company_lower = company_name.lower()

    # Direct match in taxonomy
    for industry, data in INDUSTRY_TAXONOMY.items():
        if company_lower in [c.lower() for c in data['companies']]:
            return industry
        for keyword in data['keywords']:
            if keyword in company_lower:
                return industry

    # Check GitHub org topics if available
    if github_org:
        try:
            url = f"https://api.github.com/orgs/{github_org}"
            response = requests.get(url, headers=get_github_headers(), timeout=15)
            if response.status_code == 200:
                org_data = response.json()
                description = (org_data.get('description') or '').lower()

                for industry, data in INDUSTRY_TAXONOMY.items():
                    for keyword in data['keywords']:
                        if keyword in description:
                            return industry
        except Exception:
            pass

    return None


def get_similar_companies(company_name: str, github_org: str = None, limit: int = 10) -> List[Dict]:
    """
    Get similar companies based on industry taxonomy.
    """
    industry = get_company_industry(company_name, github_org)

    if not industry:
        return []

    similar = []
    industry_data = INDUSTRY_TAXONOMY.get(industry, {})
    company_lower = company_name.lower()

    for similar_company in industry_data.get('companies', []):
        if similar_company.lower() != company_lower:
            similar.append({
                'company_name': similar_company.capitalize(),
                'github_org': similar_company,
                'industry': industry,
                'source': 'similar',
                'reason': f"Same industry: {industry}"
            })

    return similar[:limit]


def discover_similar_companies_for_all(followed_companies: List[Dict]) -> List[Dict]:
    """
    Get similar company suggestions for all followed companies.
    """
    all_suggestions = []
    seen_orgs = set()

    # Get orgs of already followed companies
    for company in followed_companies:
        seen_orgs.add(company.get('github_org', '').lower())
        seen_orgs.add(company.get('name', '').lower())

    for company in followed_companies:
        similar = get_similar_companies(
            company.get('name', ''),
            company.get('github_org', '')
        )

        for suggestion in similar:
            org_lower = suggestion['github_org'].lower()
            if org_lower not in seen_orgs:
                seen_orgs.add(org_lower)
                suggestion['based_on'] = company.get('name')
                all_suggestions.append(suggestion)

    return all_suggestions


# ============================================================
# 3. DEPENDENCY GRAPH DISCOVERY
# ============================================================

def search_repos_using_library(library: str, min_stars: int = 500) -> List[Dict]:
    """
    Find repos that use a specific i18n library.
    """
    results = []

    try:
        # Search for repos with the library in package.json or requirements
        url = "https://api.github.com/search/code"
        params = {
            'q': f'"{library}" filename:package.json',
            'per_page': 30
        }

        response = requests.get(url, headers=get_github_headers(), params=params, timeout=30)

        if response.status_code == 200:
            data = response.json()
            seen_repos = set()

            for item in data.get('items', []):
                repo = item.get('repository', {})
                full_name = repo.get('full_name', '')

                if full_name and full_name not in seen_repos:
                    seen_repos.add(full_name)
                    results.append({
                        'full_name': full_name,
                        'owner': repo.get('owner', {}).get('login', ''),
                        'name': repo.get('name', ''),
                        'description': repo.get('description', ''),
                        'url': repo.get('html_url', ''),
                        'library': library
                    })

        time.sleep(2)  # Code search has stricter rate limits

    except Exception as e:
        log(f"Error searching for {library} users: {e}", "WARNING")

    return results[:20]


def discover_by_i18n_dependencies() -> List[Dict]:
    """
    Discover companies using popular i18n libraries.
    """
    log("Discovering repos by i18n library usage...")

    all_repos = []
    seen_orgs = set()

    for library in I18N_LIBRARIES[:5]:  # Limit to avoid rate limits
        repos = search_repos_using_library(library)

        for repo in repos:
            org = repo['owner']
            if org and org not in seen_orgs:
                seen_orgs.add(org)
                all_repos.append({
                    'company_name': org,
                    'github_org': org,
                    'repo_name': repo['name'],
                    'full_name': repo['full_name'],
                    'description': repo['description'],
                    'url': repo['url'],
                    'i18n_library': library,
                    'source': 'dependency',
                    'reason': f"Uses {library} i18n library"
                })

        time.sleep(config.REQUEST_DELAY)

    log(f"Found {len(all_repos)} repos using i18n libraries")
    return all_repos


# ============================================================
# 4. GLOBAL I18N PR FIREHOSE
# ============================================================

def search_recent_i18n_prs(hours: int = 24) -> List[Dict]:
    """
    Search for recent PRs with i18n-related keywords across all of GitHub.
    """
    results = []
    date_threshold = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%dT%H:%M:%SZ')

    # PR search queries
    search_queries = [
        'is:pr is:open translation in:title created:>' + date_threshold[:10],
        'is:pr is:open localization in:title created:>' + date_threshold[:10],
        'is:pr is:open i18n in:title created:>' + date_threshold[:10],
        'is:pr is:open "add language" in:title created:>' + date_threshold[:10],
    ]

    seen_prs = set()

    for query in search_queries:
        try:
            url = "https://api.github.com/search/issues"
            params = {
                'q': query,
                'sort': 'created',
                'order': 'desc',
                'per_page': 30
            }

            response = requests.get(url, headers=get_github_headers(), params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()

                for pr in data.get('items', []):
                    pr_id = pr['id']
                    if pr_id not in seen_prs:
                        seen_prs.add(pr_id)

                        # Extract repo info from URL
                        repo_url = pr.get('repository_url', '')
                        repo_parts = repo_url.replace('https://api.github.com/repos/', '').split('/')
                        owner = repo_parts[0] if len(repo_parts) > 0 else ''
                        repo = repo_parts[1] if len(repo_parts) > 1 else ''

                        results.append({
                            'title': pr['title'],
                            'url': pr['html_url'],
                            'owner': owner,
                            'repo': repo,
                            'full_name': f"{owner}/{repo}",
                            'author': pr['user']['login'],
                            'created_at': pr['created_at'],
                            'state': pr['state'],
                            'source': 'pr_firehose'
                        })

            time.sleep(config.REQUEST_DELAY)

        except Exception as e:
            log(f"Error in PR firehose search: {e}", "WARNING")

    # Sort by creation date
    results.sort(key=lambda x: x['created_at'], reverse=True)
    return results[:50]


def discover_from_pr_firehose() -> List[Dict]:
    """
    Discover companies from the global i18n PR firehose.
    Returns unique company suggestions from recent PRs.
    """
    log("Scanning global i18n PR firehose...")

    prs = search_recent_i18n_prs()
    suggestions = []
    seen_orgs = set()

    for pr in prs:
        org = pr['owner']
        if org and org not in seen_orgs:
            seen_orgs.add(org)
            suggestions.append({
                'company_name': org,
                'github_org': org,
                'repo_name': pr['repo'],
                'full_name': pr['full_name'],
                'latest_pr': pr['title'],
                'pr_url': pr['url'],
                'pr_author': pr['author'],
                'source': 'pr_firehose',
                'reason': f"Recent i18n PR: {pr['title'][:50]}..."
            })

    log(f"Found {len(suggestions)} companies from PR firehose")
    return suggestions


# ============================================================
# 5. AUTO-ENRICHMENT
# ============================================================

def enrich_company_data(github_org: str) -> Dict:
    """
    Auto-enrich company data by detecting:
    - Company name
    - Play Store package
    - Documentation URLs
    - Available repos with i18n activity
    """
    enriched = {
        'github_org': github_org,
        'company_name': github_org,
        'github_repos': [],
        'play_package': None,
        'doc_urls': [],
        'languages_detected': [],
        'total_stars': 0
    }

    try:
        # Get org info
        url = f"https://api.github.com/orgs/{github_org}"
        response = requests.get(url, headers=get_github_headers(), timeout=15)

        if response.status_code == 200:
            org_data = response.json()
            enriched['company_name'] = org_data.get('name') or github_org

            blog = org_data.get('blog', '')
            if blog and blog.startswith('http'):
                enriched['doc_urls'].append(blog)

        time.sleep(config.REQUEST_DELAY)

        # Get repos with i18n activity
        url = f"https://api.github.com/orgs/{github_org}/repos"
        params = {'sort': 'updated', 'per_page': 30}
        response = requests.get(url, headers=get_github_headers(), params=params, timeout=15)

        if response.status_code == 200:
            repos = response.json()

            for repo in repos[:10]:
                enriched['total_stars'] += repo.get('stargazers_count', 0)

                # Check for i18n signals
                signals = get_repo_i18n_signals(github_org, repo['name'])
                if signals['has_locales']:
                    enriched['github_repos'].append(repo['name'])
                    enriched['languages_detected'].extend(signals['languages'])

                time.sleep(0.5)

        # Deduplicate languages
        enriched['languages_detected'] = list(set(enriched['languages_detected']))

        # Try to guess Play Store package
        common_patterns = [
            f"com.{github_org.lower()}.android",
            f"com.{github_org.lower()}",
            f"com.{github_org.lower().replace('-', '')}",
        ]
        enriched['play_package_suggestions'] = common_patterns

    except Exception as e:
        log(f"Error enriching {github_org}: {e}", "WARNING")

    return enriched


# ============================================================
# 6. LANGUAGE EXPANSION ALERTS
# ============================================================

def search_new_language_additions(min_stars: int = 1000) -> List[Dict]:
    """
    Search for repos that recently added new language files.
    Focus on high-star repos that are likely real companies.
    """
    results = []
    date_threshold = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    # Search for recently added locale files
    search_queries = [
        f'path:locales extension:json pushed:>{date_threshold} stars:>{min_stars}',
        f'path:translations extension:json pushed:>{date_threshold} stars:>{min_stars}',
        f'path:i18n extension:json pushed:>{date_threshold} stars:>{min_stars}',
    ]

    seen_repos = set()

    for query in search_queries:
        try:
            url = "https://api.github.com/search/repositories"
            params = {
                'q': query,
                'sort': 'updated',
                'order': 'desc',
                'per_page': 20
            }

            response = requests.get(url, headers=get_github_headers(), params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()

                for repo in data.get('items', []):
                    full_name = repo['full_name']
                    if full_name not in seen_repos:
                        seen_repos.add(full_name)
                        results.append({
                            'full_name': full_name,
                            'owner': repo['owner']['login'],
                            'name': repo['name'],
                            'description': repo.get('description', ''),
                            'stars': repo['stargazers_count'],
                            'url': repo['html_url'],
                            'updated_at': repo['updated_at'],
                        })

            time.sleep(config.REQUEST_DELAY)

        except Exception as e:
            log(f"Error in language expansion search: {e}", "WARNING")

    results.sort(key=lambda x: x['stars'], reverse=True)
    return results[:30]


def discover_language_expansions() -> List[Dict]:
    """
    Discover repos with recent language file additions.
    """
    log("Discovering language expansion signals...")

    repos = search_new_language_additions()
    suggestions = []

    for repo in repos:
        signals = get_repo_i18n_signals(repo['owner'], repo['name'])

        if signals['languages']:
            suggestions.append({
                'company_name': repo['owner'],
                'github_org': repo['owner'],
                'repo_name': repo['name'],
                'full_name': repo['full_name'],
                'description': repo['description'],
                'stars': repo['stars'],
                'languages_detected': signals['languages'],
                'url': repo['url'],
                'source': 'expansion',
                'reason': f"Recently expanded to {len(signals['languages'])} languages"
            })

        time.sleep(0.5)

    log(f"Found {len(suggestions)} language expansion signals")
    return suggestions


# ============================================================
# 7. SMART SEARCH WITH AI
# ============================================================

def search_companies(query: str, limit: int = 20) -> List[Dict]:
    """
    Smart search for companies by name, industry, or keywords.
    """
    results = []
    query_lower = query.lower()

    # Check industry keywords first
    for industry, data in INDUSTRY_TAXONOMY.items():
        if query_lower in industry or any(kw in query_lower for kw in data['keywords']):
            for company in data['companies'][:limit]:
                results.append({
                    'company_name': company.capitalize(),
                    'github_org': company,
                    'industry': industry,
                    'source': 'search',
                    'reason': f"Industry match: {industry}"
                })

    # Search GitHub orgs
    try:
        url = "https://api.github.com/search/users"
        params = {
            'q': f'{query} type:org',
            'per_page': limit
        }

        response = requests.get(url, headers=get_github_headers(), params=params, timeout=15)

        if response.status_code == 200:
            data = response.json()
            for user in data.get('items', []):
                results.append({
                    'company_name': user['login'],
                    'github_org': user['login'],
                    'avatar_url': user.get('avatar_url', ''),
                    'url': user['html_url'],
                    'source': 'search',
                    'reason': f"GitHub org match: {user['login']}"
                })

    except Exception as e:
        log(f"Error in company search: {e}", "WARNING")

    return results[:limit]


def get_ai_search_suggestions(query: str) -> List[str]:
    """
    Get AI-powered search suggestions based on query.
    Returns list of suggested search terms.
    """
    # Simple suggestion logic - can be enhanced with AI
    suggestions = []
    query_lower = query.lower()

    # Industry suggestions
    for industry in INDUSTRY_TAXONOMY.keys():
        if query_lower in industry or industry.startswith(query_lower):
            suggestions.append(industry)

    # Company suggestions from taxonomy
    for industry, data in INDUSTRY_TAXONOMY.items():
        for company in data['companies']:
            if query_lower in company:
                suggestions.append(company)

    return suggestions[:10]


# ============================================================
# MAIN DISCOVERY FUNCTIONS
# ============================================================

def run_full_discovery(followed_companies: List[Dict] = None) -> Dict:
    """
    Run all discovery methods and aggregate suggestions.
    Returns dict with categorized suggestions.
    """
    log("Running full discovery scan...")

    followed = followed_companies or []
    followed_orgs = set(c.get('github_org', '').lower() for c in followed)

    all_suggestions = {
        'trending': [],
        'similar': [],
        'dependencies': [],
        'pr_firehose': [],
        'expansions': [],
        'last_updated': datetime.now().isoformat()
    }

    # Run discovery methods in parallel where possible
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(discover_trending_i18n_companies): 'trending',
            executor.submit(discover_from_pr_firehose): 'pr_firehose',
            executor.submit(discover_language_expansions): 'expansions',
        }

        for future in as_completed(futures):
            category = futures[future]
            try:
                results = future.result()
                # Filter out already followed companies
                filtered = [
                    r for r in results
                    if r.get('github_org', '').lower() not in followed_orgs
                ]
                all_suggestions[category] = filtered
            except Exception as e:
                log(f"Error in {category} discovery: {e}", "ERROR")

    # Similar companies (needs followed list)
    if followed:
        similar = discover_similar_companies_for_all(followed)
        all_suggestions['similar'] = [
            s for s in similar
            if s.get('github_org', '').lower() not in followed_orgs
        ]

    # Dependencies discovery (slower, run separately)
    try:
        deps = discover_by_i18n_dependencies()
        all_suggestions['dependencies'] = [
            d for d in deps
            if d.get('github_org', '').lower() not in followed_orgs
        ][:20]
    except Exception as e:
        log(f"Error in dependency discovery: {e}", "ERROR")

    # Save to cache
    try:
        save_json(SUGGESTIONS_FILE, all_suggestions)
    except Exception as e:
        log(f"Error saving suggestions cache: {e}", "WARNING")

    total = sum(len(v) for k, v in all_suggestions.items() if isinstance(v, list))
    log(f"Discovery complete. Found {total} total suggestions.")

    return all_suggestions


def get_cached_suggestions() -> Dict:
    """
    Get cached suggestions if available.
    """
    try:
        if os.path.exists(SUGGESTIONS_FILE):
            return load_json(SUGGESTIONS_FILE)
    except Exception:
        pass
    return {}


def get_quick_suggestions(followed_companies: List[Dict] = None, limit: int = 20) -> List[Dict]:
    """
    Get quick suggestions without running full discovery.
    Combines cached data and similar company logic.
    """
    suggestions = []
    followed = followed_companies or []
    followed_orgs = set(c.get('github_org', '').lower() for c in followed)

    # Load cached suggestions
    cached = get_cached_suggestions()

    for category in ['trending', 'similar', 'pr_firehose', 'expansions']:
        for item in cached.get(category, [])[:5]:
            if item.get('github_org', '').lower() not in followed_orgs:
                item['category'] = category
                suggestions.append(item)

    # Add similar companies if we have followed companies
    if followed:
        similar = discover_similar_companies_for_all(followed)[:10]
        for s in similar:
            if s.get('github_org', '').lower() not in followed_orgs:
                s['category'] = 'similar'
                suggestions.append(s)

    return suggestions[:limit]
