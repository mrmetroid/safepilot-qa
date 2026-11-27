"""Prompt-injection scanner, URL policy and the irreversible-action gate (BUILD_SPEC 3.3, 3.7, 5.1)."""

from __future__ import annotations

import ipaddress
import re
import socket
from typing import Any
from urllib.parse import urlparse

INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ignore previous instructions", re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.I)),
    ("system prompt exfil", re.compile(r"(reveal|print|show|leak)\s+(your\s+)?(the\s+)?system\s+prompt", re.I)),
    ("process.env exfil", re.compile(r"process\.env", re.I)),
    ("inference key exfil", re.compile(r"VULTR_INFERENCE_API_KEY|VULTR_API_KEY", re.I)),
    ("api key exfil", re.compile(r"(print|reveal|send|paste|leak)\s+(all\s+)?(your\s+)?(api\s*keys|secrets|credentials|environment variables)", re.I)),
    ("docker socket", re.compile(r"docker\.sock|:2375/", re.I)),
    ("cloud metadata", re.compile(r"169\.254\.169\.254|metadata\.google\.internal", re.I)),
    ("host env files", re.compile(r"/proc/1/environ|/etc/environment", re.I)),
    ("system override", re.compile(r"SYSTEM\s+OVERRIDE", re.I)),
]

IRREVERSIBLE_TEXT = re.compile(
    r"^\s*(place\s+(my\s+)?order|pay(\s+now)?|buy\s+now|complete\s+(purchase|order)|confirm\s+(purchase|order|payment)|"
    r"submit\s+order|purchase|checkout\s+now|delete(\s+account)?|order\s+now)\b",
    re.I,
)
IRREVERSIBLE_SELECTOR = re.compile(r"place[-_]?order|submit[-_]?order|pay[-_]?now|confirm[-_]?(purchase|order|payment)|delete", re.I)


def scan_text(*chunks: str | None) -> str | None:
    """Return a short description of the first injection pattern found, else None."""
    blob = "\n".join(c for c in chunks if c)
    for label, pat in INJECTION_PATTERNS:
        m = pat.search(blob)
        if m:
            start = max(0, m.start() - 60)
            return f"{label}: \"...{blob[start:m.end() + 60].strip()}...\""
    return None


def _is_private_host(host: str, approved_host: str) -> bool:
    host = (host or "").strip("[]").lower()
    if not host:
        return True
    if host == approved_host.lower():
        return False
    if host in {"localhost", "metadata", "metadata.google.internal"} or host.endswith(".localhost") or host.endswith(".internal"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified or ip.is_multicast


def check_navigation(url: str, approved_host: str) -> str | None:
    """Block private/metadata targets. Returns reason when the URL is forbidden."""
    try:
        p = urlparse(url)
    except ValueError:
        return "unparseable url"
    if p.scheme not in ("http", "https"):
        return f"forbidden scheme {p.scheme!r}"
    if _is_private_host(p.hostname or "", approved_host):
        return f"forbidden host {p.hostname!r} (metadata / loopback / RFC1918)"
    return None


def validate_public_url(url: str) -> str | None:
    """API-level check for custom runs: public http(s) only, resolve DNS to catch rebinding to private IPs."""
    reason = check_navigation(url, approved_host="__none__")
    if reason:
        return reason
    host = urlparse(url).hostname or ""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return f"cannot resolve {host}"
    for info in infos:
        addr = info[4][0]
        if _is_private_host(addr, "__none__"):
            return f"{host} resolves to a private address"
    return None


def same_site(url: str, target_url: str) -> bool:
    a, b = urlparse(url).hostname or "", urlparse(target_url).hostname or ""
    root = lambda h: ".".join(h.split(".")[-2:])  # noqa: E731 - good enough for a demo
    return root(a) == root(b)


def scan_action(action: dict[str, Any], approved_host: str, target_url: str) -> tuple[str, str] | None:
    """Return (kind, reason) when a model-proposed action must not run. kind: injection | off_origin."""
    text_fields = " ".join(str(action.get(k) or "") for k in ("selector", "value", "url", "thought", "notes"))
    hit = scan_text(text_fields)
    # A planner *noticing* an injection in its thought is fine; acting on it is not.
    if hit and scan_text(" ".join(str(action.get(k) or "") for k in ("selector", "value", "url"))):
        return ("injection", f"model action carried exfil content: {hit}")
    if action.get("action") == "goto" and action.get("url"):
        reason = check_navigation(action["url"], approved_host)
        if reason:
            return ("injection", f"navigation blocked: {reason}")
        if not same_site(action["url"], target_url):
            return ("off_origin", f"stays on target origin; refused {action['url']}")
    return None


def is_irreversible(action: dict[str, Any], dom_summary: list[dict[str, Any]], page_url: str) -> str | None:
    """Control-plane enforced approval gate. Does not trust the model's own flag alone."""
    kind = action.get("action")
    if kind == "hold_for_approval" or action.get("requires_human_approval"):
        return action.get("approval_reason") or "Planner flagged an irreversible action"
    sel = str(action.get("selector") or "")
    if kind in ("click", "press"):
        if IRREVERSIBLE_SELECTOR.search(sel):
            return f"Irreversible submit ({sel})"
        for el in dom_summary or []:
            if el.get("sel") == sel and IRREVERSIBLE_TEXT.search(el.get("text") or ""):
                return f"Irreversible button \"{el.get('text')}\""
        m = re.search(r"has-text\(\"([^\"]+)\"\)", sel)
        if m and IRREVERSIBLE_TEXT.search(m.group(1)):
            return f"Irreversible button \"{m.group(1)}\""
        if kind == "press" and "checkout" in page_url.lower() and str(action.get("value") or "Enter").lower() == "enter":
            return "Enter on checkout form submits the order"
    return None
