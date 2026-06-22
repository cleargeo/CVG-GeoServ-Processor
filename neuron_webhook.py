"""
CVG Neuron Webhook Client
(c) Clearview Geographic LLC -- Proprietary

Sends deployment and operational events to CVG Neuron's webhook receiver.
Import and use in deploy scripts, CI/CD pipelines, or application startup.

Usage:
    from neuron_webhook import notify_neuron
    notify_neuron("my-app", "success", "production")
"""

import json
import urllib.request
import urllib.error
import os

NEURON_URL = os.getenv("NEURON_URL", "http://10.10.10.200:8808")


def notify_neuron(
    app_name: str,
    status: str,
    environment: str = "production",
    message: str = "",
    metadata: dict = None,
) -> dict:
    """Send a deployment notification to CVG Neuron."""
    payload = {
        "app_name": app_name,
        "status": status,
        "environment": environment,
        "message": message,
        "metadata": metadata or {},
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{NEURON_URL}/api/webhook/deploy",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def notify_event(
    source: str,
    event_type: str,
    data: dict,
    severity: str = "info",
) -> dict:
    """Send a generic event to CVG Neuron via the edge connector."""
    payload = {
        "source": source,
        "event_type": event_type,
        "severity": severity,
        "data": data,
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{NEURON_URL}/api/webhook/deploy",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"status": "error", "detail": str(e)}
