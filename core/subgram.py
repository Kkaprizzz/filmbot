"""Клиент сервиса обязательной подписки Subgram (https://api.subgram.org).

Заменяет самодельную проверку подписки на Telethon-юзерботе: Subgram сам
подбирает каналы-спонсоры и отслеживает, подписан ли на них пользователь.
"""
from typing import Optional

import aiohttp

from core.config import settings
from core.logger import get_logger

logger = get_logger(__name__)

BASE_URL = "https://api.subgram.org"


class Sponsor:
    """Один канал/бот, на который нужно подписаться."""

    def __init__(self, raw: dict):
        self.link: str = raw.get("link")
        self.text: str = raw.get("button_text") or raw.get("resource_name") or "Подписаться"
        self.name: str = raw.get("resource_name") or self.text
        self.status: str = raw.get("status")


class SubgramResult:
    """Результат обращения к Subgram.

    ok=True  -> пользователь может проходить дальше (подписан на всё либо
                подходящих спонсоров нет).
    ok=False -> нужно подписаться на каналы из sponsors.
    """

    def __init__(self, ok: bool, sponsors: Optional[list[Sponsor]] = None):
        self.ok = ok
        self.sponsors = sponsors or []


async def _post(path: str, payload: dict) -> Optional[dict]:
    headers = {
        "Auth": settings.SUBGRAM_API_KEY,
        "Content-Type": "application/json",
    }
    url = f"{BASE_URL}/{path}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                data = await resp.json(content_type=None)
                if resp.status != 200:
                    logger.warning("Subgram %s -> HTTP %s: %s", path, resp.status, data)
                return data
    except Exception as e:
        logger.error("Ошибка запроса к Subgram (%s): %s", path, e)
        return None


async def get_sponsors(
    user_id: int,
    chat_id: int,
    first_name: Optional[str] = None,
    username: Optional[str] = None,
    language_code: Optional[str] = None,
    is_premium: Optional[bool] = None,
    max_sponsors: int = 5,
) -> SubgramResult:
    """Запрашивает у Subgram список каналов для обязательной подписки.

    Возвращает SubgramResult: ok=True если подписка не нужна/уже выполнена,
    иначе ok=False со списком спонсоров.
    """
    payload = {
        "user_id": user_id,
        "chat_id": chat_id,
        "action": "subscribe",
        "get_links": 1,
        "max_sponsors": max_sponsors,
    }
    if first_name is not None:
        payload["first_name"] = first_name
    if username is not None:
        payload["username"] = username
    if language_code is not None:
        payload["language_code"] = language_code
    if is_premium is not None:
        payload["is_premium"] = is_premium

    data = await _post("get-sponsors", payload)

    # Если Subgram недоступен — не блокируем пользователя (fail-open).
    if data is None:
        return SubgramResult(ok=True)

    status = data.get("status")

    if status == "ok":
        return SubgramResult(ok=True)

    if status == "warning":
        raw_sponsors = (data.get("additional") or {}).get("sponsors") or []
        sponsors = [Sponsor(s) for s in raw_sponsors if s.get("link")]
        # Нет ссылок для показа — пропускаем, чтобы не запереть пользователя.
        if not sponsors:
            return SubgramResult(ok=True)
        return SubgramResult(ok=False, sponsors=sponsors)

    # status == "error" или неизвестный ответ — логируем и не блокируем.
    logger.warning("Неожиданный ответ Subgram: %s", data)
    return SubgramResult(ok=True)
