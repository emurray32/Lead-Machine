"""
Documentation URL Monitoring
Detects hreflang changes and keyword additions in developer docs.
"""

import hashlib
import os
import re
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Set, Tuple

from .common import (
    log, alert, load_json, save_json, sanitize_filename,
    DOC_HASHES_FILE, PREVIOUS_TEXTS_DIR, KEYWORDS, contains_keywords
)

try:
    import storage
    DB_AVAILABLE = True
except:
    DB_AVAILABLE = False


def sanitize_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in '-_' else '_' for c in name)


def fetch_doc_page(url: str) -> Tuple[Optional[str], Optional[str], Set[str]]:
    """
    Fetch a documentation page and extract text content, hash, and hreflang values.
    Returns (text_content, content_hash, hreflang_set)
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; LocalizationMonitor/1.0)"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        hreflang_tags = soup.find_all('link', rel='alternate', hreflang=True)
        hreflangs = set()
        for tag in hreflang_tags:
            lang = tag.get('hreflang', '').lower()
            if lang and lang != 'x-default':
                hreflangs.add(lang)
        
        for script in soup(["script", "style"]):
            script.decompose()
        
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        content_hash = hashlib.md5(text.encode()).hexdigest()
        
        return text, content_hash, hreflangs
        
    except Exception as e:
        log(f"Error fetching {url}: {e}", "WARNING")
        return None, None, set()


def check_doc_url(company: str, url: str, doc_hashes: Dict, prev_hreflangs: Dict) -> int:
    """
    Check a documentation URL for changes.
    Primary: New hreflang tags (indicating new regional versions)
    Secondary: Keyword changes in text content
    Returns the number of alerts generated.
    """
    alert_count = 0
    url_key = hashlib.md5(url.encode()).hexdigest()[:16]
    
    text, content_hash, current_hreflangs = fetch_doc_page(url)
    
    if text is None:
        return 0
    
    previous_hreflangs = set(prev_hreflangs.get(url_key, []))
    new_hreflangs = current_hreflangs - previous_hreflangs
    
    if new_hreflangs and previous_hreflangs:
        signal_type = "NEW_HREFLANG"
        new_langs = list(new_hreflangs)
        
        alert_msg = (
            f"DOCS [{signal_type}] [{company}]:\n"
            f"  URL: {url}\n"
            f"  New regional versions: {', '.join(new_langs)}\n"
            f"  Total regions: {len(current_hreflangs)}"
        )
        alert(alert_msg)
        
        if DB_AVAILABLE:
            try:
                storage.save_alert(
                    source="docs",
                    company=company,
                    title=f"[{signal_type}] New regional docs: {', '.join(new_langs[:3])}",
                    message=f"Doc change detected: {url}",
                    keywords=new_langs,
                    url=url,
                    metadata={
                        "signal_type": signal_type,
                        "new_hreflangs": new_langs,
                        "total_hreflangs": len(current_hreflangs),
                        "previous_hreflang_count": len(previous_hreflangs)
                    }
                )
            except Exception as e:
                log(f"Failed to save docs alert: {e}", "WARNING")
        
        alert_count += 1
    
    prev_hreflangs[url_key] = list(current_hreflangs)
    
    previous_hash = doc_hashes.get(url_key)
    
    if previous_hash is None:
        keywords_found = contains_keywords(text)
        if keywords_found:
            signal_type = "KEYWORD"
            alert_msg = (
                f"DOCS [{signal_type}] [{company}]:\n"
                f"  Doc change detected: {url}\n"
                f"  New keywords: First scan"
            )
            alert(alert_msg)
            
            if DB_AVAILABLE:
                try:
                    storage.save_alert(
                        source="docs",
                        company=company,
                        title=f"Doc change detected: {url}",
                        message=f"New keywords: First scan",
                        keywords=keywords_found[:10],
                        url=url,
                        metadata={"signal_type": signal_type}
                    )
                except Exception as e:
                    log(f"Failed to save docs alert: {e}", "WARNING")
            
            alert_count += 1
    elif content_hash != previous_hash:
        prev_text_file = os.path.join(PREVIOUS_TEXTS_DIR, f"{url_key}.txt")
        previous_text = ""
        if os.path.exists(prev_text_file):
            try:
                with open(prev_text_file, 'r') as f:
                    previous_text = f.read()
            except:
                pass
        
        prev_keywords = set(contains_keywords(previous_text)) if previous_text else set()
        curr_keywords = set(contains_keywords(text))
        new_keywords = curr_keywords - prev_keywords
        
        if new_keywords:
            signal_type = "KEYWORD"
            new_kw_list = list(new_keywords)
            
            alert_msg = (
                f"DOCS [{signal_type}] [{company}]:\n"
                f"  Doc change detected: {url}\n"
                f"  New keywords: {', '.join(new_kw_list)}"
            )
            alert(alert_msg)
            
            if DB_AVAILABLE:
                try:
                    storage.save_alert(
                        source="docs",
                        company=company,
                        title=f"Doc change detected: {url}",
                        message=f"New keywords: {', '.join(new_kw_list)}",
                        keywords=new_kw_list,
                        url=url,
                        metadata={"signal_type": signal_type}
                    )
                except Exception as e:
                    log(f"Failed to save docs alert: {e}", "WARNING")
            
            alert_count += 1
        
        try:
            with open(prev_text_file, 'w') as f:
                f.write(text)
        except:
            pass
    
    doc_hashes[url_key] = content_hash
    
    return alert_count


def check_all_docs(targets: List[Dict]) -> int:
    """Check all configured documentation URLs."""
    log("Starting documentation checks...")
    doc_hashes = load_json(DOC_HASHES_FILE)
    prev_hreflangs = load_json(DOC_HASHES_FILE.replace('.json', '_hreflangs.json'))
    total_alerts = 0
    urls_checked = 0
    
    for target in targets:
        company = target.get("company", "Unknown")
        doc_urls = target.get("doc_urls", [])
        
        for url in doc_urls:
            alerts = check_doc_url(company, url, doc_hashes, prev_hreflangs)
            total_alerts += alerts
            urls_checked += 1
    
    save_json(DOC_HASHES_FILE, doc_hashes)
    save_json(DOC_HASHES_FILE.replace('.json', '_hreflangs.json'), prev_hreflangs)
    log(f"Documentation checks complete. Checked {urls_checked} URLs, found {total_alerts} alerts.")
    return total_alerts
