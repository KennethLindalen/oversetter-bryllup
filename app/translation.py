import asyncio
import logging
import os
from collections import OrderedDict

import httpx

logger = logging.getLogger(__name__)

DEEPL_SOURCE = {"en": "EN", "no": "NB", "ru": "RU"}
DEEPL_TARGET = {"en": "EN-US", "no": "NB", "ru": "RU"}

_client: httpx.AsyncClient | None = None

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


async def prewarm() -> None:
    pass


def _deepl_base() -> str:
    key = os.getenv("DEEPL_API_KEY", "")
    return "https://api-free.deepl.com" if key.endswith(":fx") else "https://api.deepl.com"


async def _translate_one(text: str, source: str, target_key: str) -> tuple[str, str]:
    cached = _cache_get(text, source, target_key)
    if cached is not None:
        return target_key, cached

    api_key = os.getenv("DEEPL_API_KEY", "")
    source_code = DEEPL_SOURCE.get(source, "EN")
    target_code = DEEPL_TARGET.get(target_key, "EN-US")
    try:
        resp = await get_client().post(
            f"{_deepl_base()}/v2/translate",
            headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
            json={"text": [text], "source_lang": source_code, "target_lang": target_code},
        )
        resp.raise_for_status()
        result = resp.json()["translations"][0]["text"]
        _cache_set(text, source, target_key, result)
        return target_key, result
    except Exception as e:
        logger.error("DeepL translation failed %s->%s: %s", source, target_key, e)
        return target_key, text


async def translate_all(text: str, source: str = "en", needed: set[str] | None = None) -> dict[str, str]:
    if needed is None:
        needed = {"en", "no", "ru"}

    targets = [k for k in needed if k != source and k in DEEPL_TARGET]
    results = await asyncio.gather(*[_translate_one(text, source, t) for t in targets])

    translations: dict[str, str] = {source: text}
    for key, translated in results:
        translations[key] = translated

    for key in ("en", "no", "ru"):
        translations.setdefault(key, text)

    return translations
