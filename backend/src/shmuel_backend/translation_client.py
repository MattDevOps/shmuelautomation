"""OpenAI translation client — graceful no-op when unconfigured.

Mirrors the pattern of `email_client.py`: dev/CI runs without
OPENAI_API_KEY just log the would-be call and return None. Errors are
logged but never raised — a translation failure for one field should
never break the sync run.
"""
from __future__ import annotations

import logging

import httpx

from shmuel_backend.config import settings

log = logging.getLogger(__name__)

OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

LANG_NAMES = {
    "es": "Spanish",
    "fr": "French",
    "he": "Hebrew",
}

SYSTEM_PROMPT = (
    "You are a professional translator for a Jerusalem real-estate brokerage. "
    "Translate the user's text from English to {target_lang}. "
    "Preserve real-estate terminology, neighborhood names, street names, and prices verbatim. "
    "Output only the translation — no quotes, no commentary, no preamble. "
    "Match the source's tone and formatting (paragraph breaks, lists)."
)


async def translate(*, text: str, target_lang: str) -> str | None:
    """Translate `text` from English to `target_lang` ('es' | 'fr' | 'he').

    Returns the translated string, or None if no-op / failed. Never raises.
    Caller decides whether to retry, skip, or fall back.
    """
    text = text.strip()
    if not text:
        return ""
    if target_lang not in LANG_NAMES:
        log.warning("translate: unsupported target_lang=%s", target_lang)
        return None
    if not settings.openai_api_key:
        log.info(
            "OpenAI not configured; would have translated %d chars to %s",
            len(text),
            target_lang,
        )
        return None

    lang_name = LANG_NAMES[target_lang]
    payload = {
        "model": settings.openai_translate_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.format(target_lang=lang_name)},
            {"role": "user", "content": text},
        ],
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(OPENAI_ENDPOINT, json=payload, headers=headers)
        if resp.status_code >= 400:
            log.warning(
                "OpenAI %s for target=%s: %s",
                resp.status_code,
                target_lang,
                resp.text[:500],
            )
            return None
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            log.warning("OpenAI returned no choices for target=%s", target_lang)
            return None
        translated = (choices[0].get("message") or {}).get("content")
        if not translated:
            log.warning("OpenAI choice missing message.content for target=%s", target_lang)
            return None
        return translated.strip()
    except httpx.HTTPError as exc:
        log.warning("OpenAI request failed for target=%s: %s", target_lang, exc)
        return None
