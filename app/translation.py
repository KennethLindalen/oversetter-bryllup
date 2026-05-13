import asyncio
import logging
import os
import httpx

logger = logging.getLogger(__name__)
SUPPORTED_LANGS = ["en", "nb", "ru"]

_client: httpx.AsyncClient | None = None


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
    url = os.getenv("LIBRETRANSLATE_URL", "http://libretranslate:5000").rstrip("/")
    api_key = os.getenv("LIBRETRANSLATE_API_KEY", "")
    payload = {"q": text, "source": source, "target": target, "format": "text"}
    if api_key:
        payload["api_key"] = api_key
    try:
        resp = await get_client().post(f"{url}/translate", json=payload)
        resp.raise_for_status()
        return target, resp.json().get("translatedText", text)
    except Exception as e:
        logger.error("Translation failed %s→%s: %s", source, target, e)
        return target, text


async def translate_all(text: str, source: str = "en", needed: set[str] | None = None) -> dict[str, str]:
    """Translate text into needed languages. `needed` uses output keys: en, no, ru."""
    lt_source = source  # source is already a LibreTranslate code (en/nb/ru)

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
