import asyncio
import logging
import os
from collections import OrderedDict

import httpx

logger = logging.getLogger(__name__)
SUPPORTED_LANGS = ["en", "nb", "ru"]

_client: httpx.AsyncClient | None = None

# LRU translation cache — keyed by (text, source, target)
_cache: OrderedDict[tuple, str] = OrderedDict()
_CACHE_MAX = 500


def _cache_get(text: str, source: str, target: str) -> str | None:
    key = (text, source, target)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    return None


def _cache_set(text: str, source: str, target: str, value: str) -> None:
    key = (text, source, target)
    _cache[key] = value
    _cache.move_to_end(key)
    if len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=10.0)
    return _client


async def close_client():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()


async def _translate_one(text: str, source: str, target: str) -> tuple[str, str]:
    cached = _cache_get(text, source, target)
    if cached is not None:
        return target, cached

    url = os.getenv("LIBRETRANSLATE_URL", "http://libretranslate:5000").rstrip("/")
    api_key = os.getenv("LIBRETRANSLATE_API_KEY", "")
    payload = {"q": text, "source": source, "target": target, "format": "text"}
    if api_key:
        payload["api_key"] = api_key
    try:
        resp = await get_client().post(f"{url}/translate", json=payload)
        resp.raise_for_status()
        result = resp.json().get("translatedText", text)
        if result != text:
            _cache_set(text, source, target, result)
        return target, result
    except Exception as e:
        logger.error("Translation failed %s→%s: %s", source, target, e)
        return target, text


async def detect_language(text: str) -> str:
    """Returns a LibreTranslate language code (en, nb, ru, ...). Falls back to 'nb'."""
    url = os.getenv("LIBRETRANSLATE_URL", "http://libretranslate:5000").rstrip("/")
    api_key = os.getenv("LIBRETRANSLATE_API_KEY", "")
    payload = {"q": text}
    if api_key:
        payload["api_key"] = api_key
    try:
        resp = await get_client().post(f"{url}/detect", json=payload)
        resp.raise_for_status()
        results = resp.json()
        if results:
            return results[0]["language"]
    except Exception as e:
        logger.error("Language detection failed: %s", e)
    return "nb"


async def prewarm() -> None:
    """Translate a short dummy phrase so the models are hot before any real request."""
    try:
        await translate_all("hello", source="en", needed={"no", "ru"})
        logger.info("LibreTranslate prewarm complete")
    except Exception as e:
        logger.warning("LibreTranslate prewarm failed: %s", e)


async def translate_all(text: str, source: str = "auto", needed: set[str] | None = None) -> dict[str, str]:
    """Translate text into needed languages. `needed` uses output keys: en, no, ru.
    Pass source='auto' to detect the language automatically."""
    if source == "auto":
        source = await detect_language(text)

    lt_source = source  # LibreTranslate code (en/nb/ru)

    # Map output keys to LibreTranslate target codes
    key_to_lt = {"en": "en", "no": "nb", "ru": "ru"}
    lt_to_key = {"en": "en", "nb": "no", "ru": "ru"}
    source_output_key = lt_to_key.get(source, source)

    if needed is None:
        needed = {"en", "no", "ru"}

    targets = [
        key_to_lt[k] for k in needed
        if k != source_output_key and k in key_to_lt
    ]

    results = await asyncio.gather(*[_translate_one(text, lt_source, t) for t in targets])

    translations: dict[str, str] = {source_output_key: text}
    for lt_code, translated in results:
        translations[lt_to_key[lt_code]] = translated

    # Fill any remaining keys with original text as fallback
    for key in ("en", "no", "ru"):
        translations.setdefault(key, text)

    return translations
