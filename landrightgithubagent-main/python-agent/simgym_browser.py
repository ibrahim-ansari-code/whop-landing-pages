"""
SimGym browser runner: Playwright bots visit forced-variant URLs, use Llama 4 Scout (vision)
or Llama 3.1 8B (text) for scroll/click decisions, and send beacons with event_source=simgym.
Bots are assigned evenly across variants (1-4). Requires SIMGYM_BASE_URL and SIMGYM_BEACON_URL.
"""
from __future__ import annotations

import base64
import json
import logging
import random
import time
from typing import Any

import httpx

from config import (
    GROQ_API_KEY,
    SIMGYM_BASE_URL,
    SIMGYM_BEACON_URL,
    SIMGYM_BOT_DELAY_SECONDS,
    SIMGYM_HEADLESS,
    SIMGYM_PERSONAS_PATH_RESOLVED,
    SIMGYM_USE_VISION,
)

log = logging.getLogger(__name__)

# Model IDs
GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
GROQ_TEXT_MODEL = "llama-3.1-8b-instant"
GROQ_API_BASE = "https://api.groq.com/openai/v1"


def _load_personas() -> list[dict[str, Any]]:
    if not SIMGYM_PERSONAS_PATH_RESOLVED or not SIMGYM_PERSONAS_PATH_RESOLVED.exists():
        log.warning("No personas file at %s; using minimal default", SIMGYM_PERSONAS_PATH_RESOLVED)
        return [{"id": "default", "name": "Visitor", "role": "User", "intent": "Evaluate page", "behavior_profile": "scrolls and may click CTA"}]
    with open(SIMGYM_PERSONAS_PATH_RESOLVED, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def _assign_variants(n_bots: int) -> list[int]:
    """Assign each bot to variant 1-4 evenly (round-robin)."""
    return [(i % 4) + 1 for i in range(n_bots)]


def _call_groq_vision(image_base64: str, persona: dict[str, Any], variant_id: int) -> str:
    """Call Groq Llama 4 Scout with screenshot + persona; return scroll/click decision."""
    if not GROQ_API_KEY:
        log.warning("GROQ_API_KEY not set; returning default action")
        return "scroll"
    prompt = f"""You are a simulated visitor with this profile: {json.dumps(persona)}.
You are viewing landing page variant {variant_id}. Based on the screenshot, choose ONE action:
- "scroll" — scroll down to see more
- "click: <label>" — click the button/link with that text (use exact visible text)

Reply with only the action, e.g. scroll or click: Get started."""
    url = f"{GROQ_API_BASE}/chat/completions"
    payload = {
        "model": GROQ_VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                    },
                ],
            }
        ],
        "max_tokens": 64,
        "temperature": 0.3,
    }
    try:
        r = httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            timeout=30.0,
        )
        r.raise_for_status()
        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = (msg.get("content") or "").strip().lower()
        if "click:" in content:
            return content  # e.g. "click: get started"
        return "scroll"
    except Exception as e:
        log.warning("Groq vision call failed: %s", e)
        return "scroll"


def _call_groq_text(page_text: str, persona: dict[str, Any], variant_id: int) -> str:
    """Call Groq Llama 3.1 8B with extracted page text; return scroll/click decision."""
    if not GROQ_API_KEY:
        return "scroll"
    prompt = f"""You are a simulated visitor: {json.dumps(persona)}. Viewing variant {variant_id}. Page content:\n{page_text[:4000]}\nChoose ONE: "scroll" or "click: <button text>". Reply with only the action."""
    url = f"{GROQ_API_BASE}/chat/completions"
    payload = {
        "model": GROQ_TEXT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 64,
        "temperature": 0.3,
    }
    try:
        r = httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            timeout=30.0,
        )
        r.raise_for_status()
        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        content = ((choice.get("message") or {}).get("content") or "").strip().lower()
        if "click:" in content:
            return content
        return "scroll"
    except Exception as e:
        log.warning("Groq text call failed: %s", e)
        return "scroll"


def _send_beacon_cta(beacon_url: str, repo_full_name: str, layer: str, variant_id: int, cta_label: str | None = None) -> None:
    variant_str = f"variant-{variant_id}"
    payload = {
        "event": "button_click",
        "repo_full_name": repo_full_name,
        "layer": layer,
        "variant_id": variant_str,
        "cta_label": cta_label,
        "event_source": "simgym",
    }
    try:
        r = httpx.post(f"{beacon_url}/beacon", json=payload, timeout=10.0)
        if r.status_code >= 400:
            log.warning("beacon POST failed: %s %s", r.status_code, r.text)
    except Exception as e:
        log.warning("beacon POST error: %s", e)


def _send_beacon_time(
    beacon_url: str, repo_full_name: str, layer: str, variant_id: int, duration_seconds: float
) -> None:
    variant_str = f"variant-{variant_id}"
    payload = {
        "repo_full_name": repo_full_name,
        "layer": layer,
        "variant_id": variant_str,
        "duration_seconds": round(duration_seconds, 2),
        "event_source": "simgym",
    }
    try:
        r = httpx.post(f"{beacon_url}/beacon-time", json=payload, timeout=10.0)
        if r.status_code >= 400:
            log.warning("beacon-time POST failed: %s %s", r.status_code, r.text)
    except Exception as e:
        log.warning("beacon-time POST error: %s", e)


def run_one_bot(
    bot_index: int,
    variant_id: int,
    repo_full_name: str,
    layer: str,
    base_url: str,
    beacon_url: str,
    personas: list[dict[str, Any]],
    use_vision: bool,
) -> None:
    """Run a single bot: open page, get decision from Groq, simulate, send beacons."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return

    persona = random.choice(personas) if personas else {}
    url = f"{base_url}/?variant={variant_id}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=SIMGYM_HEADLESS)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(1500)

            start = time.monotonic()
            action: str

            if use_vision and GROQ_API_KEY:
                screenshot_bytes = page.screenshot(type="png", full_page=False)
                image_b64 = base64.standard_b64encode(screenshot_bytes).decode("ascii")
                action = _call_groq_vision(image_b64, persona, variant_id)
            else:
                page_text = page.evaluate(
                    """() => {
                    const body = document.body;
                    const walk = (n) => {
                        let s = '';
                        if (n.nodeType === 1) {
                            const tag = n.tagName.toLowerCase();
                            if (n.innerText) s += n.innerText + ' ';
                            for (const c of n.children) s += walk(c);
                        }
                        return s;
                    };
                    return walk(body).replace(/\\s+/g, ' ').trim().slice(0, 8000);
                }"""
                )
                action = _call_groq_text(page_text or "", persona, variant_id)

            if action.startswith("click:"):
                label = action.replace("click:", "").strip()
                try:
                    page.get_by_role("button", name=label).first.click(timeout=2000)
                    _send_beacon_cta(beacon_url, repo_full_name, layer, variant_id, cta_label=label or None)
                except Exception:
                    try:
                        page.get_by_role("link", name=label).first.click(timeout=2000)
                        _send_beacon_cta(beacon_url, repo_full_name, layer, variant_id, cta_label=label or None)
                    except Exception:
                        pass
                page.wait_for_timeout(500)
            else:
                page.evaluate("window.scrollBy(0, 400)")
                page.wait_for_timeout(800)

            duration = time.monotonic() - start
            _send_beacon_time(beacon_url, repo_full_name, layer, variant_id, duration)

        finally:
            browser.close()


def run_bots(
    n_bots: int,
    repo_full_name: str,
    layer: str = "1",
    base_url: str | None = None,
    beacon_url: str | None = None,
    use_vision: bool | None = None,
) -> None:
    """Run n_bots, assigned evenly across variants 1-4; each visits base_url/?variant=N and sends beacons."""
    base_url = (base_url or SIMGYM_BASE_URL).rstrip("/")
    beacon_url = (beacon_url or SIMGYM_BEACON_URL).rstrip("/")
    use_vision = use_vision if use_vision is not None else SIMGYM_USE_VISION
    personas = _load_personas()
    variants = _assign_variants(n_bots)

    for i, variant_id in enumerate(variants):
        log.info("SimGym bot %s/%s variant=%s", i + 1, n_bots, variant_id)
        run_one_bot(
            i,
            variant_id,
            repo_full_name,
            layer,
            base_url,
            beacon_url,
            personas,
            use_vision,
        )
        if SIMGYM_BOT_DELAY_SECONDS > 0 and i < len(variants) - 1:
            time.sleep(SIMGYM_BOT_DELAY_SECONDS)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    # Usage: python simgym_browser.py <repo_full_name> [n_bots] [layer]
    repo = (sys.argv[1] or "").strip() or "demo/repo"
    n = max(1, int(sys.argv[2]) if len(sys.argv) > 2 else 10)
    layer = (sys.argv[3] or "1").strip()
    run_bots(n, repo, layer=layer)
