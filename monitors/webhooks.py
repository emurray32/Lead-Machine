"""
Generic Webhook System
Allows pushing alerts to external services like Zapier, Make.com, or custom endpoints.
"""

import os
import json
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any

from .common import log, load_json, save_json, WEBHOOKS_FILE

WEBHOOKS_FILE = os.path.join("monitoring_data", "webhooks.json")


def get_webhooks() -> List[Dict]:
    """Get all registered webhooks."""
    data = load_json(WEBHOOKS_FILE)
    return data.get("webhooks", [])


def register_webhook(name: str, url: str, events: List[str] = None, headers: Dict = None) -> bool:
    """
    Register a new webhook endpoint.
    
    Args:
        name: Friendly name for the webhook
        url: The webhook URL to POST to
        events: List of event types to trigger on (e.g., ["NEW_LANG_FILE", "NEW_HREFLANG"])
                If None, triggers on all events
        headers: Optional custom headers to include
    
    Returns:
        True if registered successfully
    """
    try:
        data = load_json(WEBHOOKS_FILE)
        webhooks = data.get("webhooks", [])
        
        existing = next((w for w in webhooks if w.get("name") == name), None)
        if existing:
            existing["url"] = url
            existing["events"] = events
            existing["headers"] = headers or {}
            existing["updated_at"] = datetime.now().isoformat()
        else:
            webhooks.append({
                "name": name,
                "url": url,
                "events": events,
                "headers": headers or {},
                "created_at": datetime.now().isoformat(),
                "enabled": True
            })
        
        data["webhooks"] = webhooks
        save_json(WEBHOOKS_FILE, data)
        log(f"Webhook registered: {name}")
        return True
        
    except Exception as e:
        log(f"Error registering webhook: {e}", "ERROR")
        return False


def remove_webhook(name: str) -> bool:
    """Remove a webhook by name."""
    try:
        data = load_json(WEBHOOKS_FILE)
        webhooks = data.get("webhooks", [])
        data["webhooks"] = [w for w in webhooks if w.get("name") != name]
        save_json(WEBHOOKS_FILE, data)
        return True
    except Exception as e:
        log(f"Error removing webhook: {e}", "ERROR")
        return False


def send_webhook(alert_data: Dict, signal_type: str = None) -> int:
    """
    Send an alert to all matching webhooks.
    
    Args:
        alert_data: Dictionary containing alert information
        signal_type: The type of signal (e.g., "NEW_LANG_FILE", "NEW_HREFLANG")
    
    Returns:
        Number of webhooks successfully notified
    """
    webhooks = get_webhooks()
    success_count = 0
    
    for webhook in webhooks:
        if not webhook.get("enabled", True):
            continue
        
        allowed_events = webhook.get("events")
        if allowed_events and signal_type and signal_type not in allowed_events:
            continue
        
        try:
            payload = {
                "event": signal_type or "ALERT",
                "timestamp": datetime.now().isoformat(),
                "data": alert_data
            }
            
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "LocalizationMonitor/1.0"
            }
            headers.update(webhook.get("headers", {}))
            
            response = requests.post(
                webhook["url"],
                json=payload,
                headers=headers,
                timeout=10
            )
            
            if response.status_code < 300:
                success_count += 1
                log(f"Webhook sent to {webhook['name']}: {response.status_code}")
            else:
                log(f"Webhook {webhook['name']} returned {response.status_code}", "WARNING")
                
        except Exception as e:
            log(f"Error sending to webhook {webhook['name']}: {e}", "WARNING")
    
    return success_count


def send_alert_to_webhooks(
    source: str,
    company: str,
    title: str,
    message: str,
    keywords: List[str],
    url: str,
    metadata: Dict = None
) -> int:
    """
    Convenience function to send a full alert to all webhooks.
    """
    signal_type = None
    if metadata and isinstance(metadata, dict):
        signal_type = metadata.get("signal_type")
    
    alert_data = {
        "source": source,
        "company": company,
        "title": title,
        "message": message,
        "keywords": keywords,
        "url": url,
        "metadata": metadata or {}
    }
    
    return send_webhook(alert_data, signal_type)
