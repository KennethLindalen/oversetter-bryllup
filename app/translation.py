import asyncio
import logging
import os
import httpx

logger = logging.getLogger(__name__)
SUPPORTED_LANGS = ["en", "nb", "ru"]


async def _translate_one(client: httpx.AsyncClient, text: str, source: str, target: str) -> tuple[str, str]:
    url = os.getenv("LIBRETRANSLATE_URL", "https://translate.argosopentech.com").rstrip("/")
    api_key = os.getenv("LIBRETRANSLATE_API_KEY", "")
    payload = {"q": text, "source": source, "target": target, "format": "text"}
    if api_key:
        payload["api_key"] = api_key
    try:
        resp = await client.post(f"{url}/translate", json=payload, timeout=10.0)
        resp.raise_for_status()
        return target, resp.json().get("translatedText", text)
    except Exception as e:
        logger.error("Translation failed %s→%s: %s", source, target, e)
        return target, text


async def translate_all(text: str, source: str = "en") -> dict[str, str]:
    """Translate text into all supported languages concurrently. Maps 'nb' → 'no' in output."""
    targets = [lang for lang in SUPPORTED_LANGS if lang != source]
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_translate_one(client, text, source, t) for t in targets])
    translations: dict[str, str] = {source: text}
    for lang, translated in results:
        out_key = "no" if lang == "nb" else lang
        translations[out_key] = translated
    # ensure all three output keys exist
    for key in ("en", "no", "ru"):
        translations.setdefault(key, text)
    return translations
