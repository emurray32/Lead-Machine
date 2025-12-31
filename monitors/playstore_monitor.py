"""
Google Play Store Language Monitoring
Detects new language support added to apps.
"""

import time
from typing import Dict, List, Optional

import config
from .common import (
    log, alert, load_json, save_json
)

try:
    from google_play_scraper import app as gplay_app
    GPLAY_AVAILABLE = True
except ImportError:
    GPLAY_AVAILABLE = False

try:
    import storage
    DB_AVAILABLE = True
except:
    DB_AVAILABLE = False


def check_play_store_package(company: str, package_id: str, stored_langs: Dict) -> int:
    """
    Check a Play Store package for new language support.
    Returns the number of alerts generated.
    """
    if not GPLAY_AVAILABLE:
        return 0
    
    alert_count = 0
    
    try:
        app_info = gplay_app(package_id, lang='en', country='us')
        
        if not app_info:
            log(f"Could not fetch Play Store info for {package_id}", "WARNING")
            return 0
        
        app_title = app_info.get('title', package_id)
        installs = app_info.get('installs', 'Unknown')
        
        previous_langs = set(stored_langs.get(package_id, []))
        
        test_langs = ["en", "es", "fr", "de", "ja", "ko", "zh", "pt", "ru", "ar", "hi", "it", "nl", "pl", "tr", "vi", "th", "id"]
        current_langs = set()
        
        for lang in test_langs:
            try:
                lang_app = gplay_app(package_id, lang=lang, country='us')
                if lang_app and lang_app.get('description'):
                    current_langs.add(lang)
                time.sleep(0.3)
            except:
                pass
        
        new_langs = current_langs - previous_langs
        
        if new_langs and previous_langs:
            signal_type = "NEW_APP_LANG"
            new_langs_list = list(new_langs)
            
            play_url = f"https://play.google.com/store/apps/details?id={package_id}"
            
            alert_msg = (
                f"PLAY STORE [{signal_type}] [{company}]:\n"
                f"  App: {app_title}\n"
                f"  New languages: {', '.join(new_langs_list)}\n"
                f"  Total languages: {len(current_langs)}\n"
                f"  Installs: {installs}\n"
                f"  URL: {play_url}"
            )
            alert(alert_msg)
            
            if DB_AVAILABLE:
                try:
                    storage.save_alert(
                        source="playstore",
                        company=company,
                        title=f"[{signal_type}] {app_title}: +{len(new_langs_list)} languages",
                        message=f"Added: {', '.join(new_langs_list)}. Total: {len(current_langs)} languages. {installs} installs.",
                        keywords=new_langs_list,
                        url=play_url,
                        metadata={
                            "package": package_id,
                            "signal_type": signal_type,
                            "new_langs": new_langs_list,
                            "total_langs": len(current_langs),
                            "previous_lang_count": len(previous_langs)
                        }
                    )
                except Exception as e:
                    log(f"Failed to save Play Store alert: {e}", "WARNING")
            
            alert_count += 1
        
        stored_langs[package_id] = list(current_langs)
        
    except Exception as e:
        log(f"Error checking Play Store for {package_id}: {e}", "WARNING")
    
    return alert_count


def check_all_play_store(targets: List[Dict]) -> int:
    """Check all configured Play Store packages."""
    if not GPLAY_AVAILABLE:
        log("google-play-scraper not available, skipping Play Store checks")
        return 0
    
    log("Starting Play Store checks...")
    stored_langs = load_json(config.PLAY_STORE_LANGS_FILE)
    total_alerts = 0
    packages_checked = 0
    
    for target in targets:
        company = target.get("company", "Unknown")
        package_id = target.get("play_package")
        
        if not package_id:
            continue
        
        alerts = check_play_store_package(company, package_id, stored_langs)
        total_alerts += alerts
        packages_checked += 1
    
    save_json(config.PLAY_STORE_LANGS_FILE, stored_langs)
    log(f"Play Store checks complete. Checked {packages_checked} packages, found {total_alerts} alerts.")
    return total_alerts
