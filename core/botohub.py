"""BotoHub mandatory subscriptions: https://botohub.me/integration."""

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit
from weakref import WeakValueDictionary

import aiohttp

ENDPOINT = "https://botohub.me/get-tasks-extended"


class BotoHubUnavailable(Exception):
    """Only a sanitized reason; never include headers or response bodies."""


@dataclass(frozen=True)
class Sponsor:
    url: str
    resource_id: str
    completed: bool


@dataclass(frozen=True)
class SubscriptionResult:
    tasks: tuple[Sponsor, ...]
    completed: bool
    skip: bool

    @property
    def allowed(self) -> bool:
        return self.completed or self.skip


def parse_result(payload: object) -> SubscriptionResult:
    # BotoHub also returns {"tasks": []} for a blocked bot/invalid request.
    # Missing flags must therefore never be interpreted as successful access.
    if not isinstance(payload, dict):
        raise BotoHubUnavailable("invalid_response")
    if any(type(payload.get(key)) is not bool for key in ("completed", "skip")):
        raise BotoHubUnavailable("invalid_flags")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        raise BotoHubUnavailable("invalid_tasks")
    sponsors = []
    for task in tasks:
        if not isinstance(task, dict) or type(task.get("completed")) is not bool:
            raise BotoHubUnavailable("invalid_sponsor")
        url = task.get("url")
        resource_id = task.get("resource_id")
        if not isinstance(url, str) or not isinstance(resource_id, str):
            raise BotoHubUnavailable("invalid_sponsor")
        try:
            parsed = urlsplit(url)
            valid = (parsed.scheme in {"http", "https"} and parsed.hostname
                     and not parsed.username and not parsed.password
                     and not any(char.isspace() for char in url))
        except ValueError:
            valid = False
        if not valid:
            raise BotoHubUnavailable("invalid_sponsor_url")
        sponsors.append(Sponsor(url, resource_id, task["completed"]))
    result = SubscriptionResult(tuple(sponsors), payload["completed"], payload["skip"])
    if not result.allowed and not sponsors:
        raise BotoHubUnavailable("empty_unconfirmed_response")
    return result


class BotoHubClient:
    def __init__(self, session: aiohttp.ClientSession, token: str, *,
                 cache_seconds: float = 30, endpoint: str = ENDPOINT,
                 clock: Callable[[], float] = time.monotonic):
        if not token.strip():
            raise RuntimeError("BOTOHUB_TOKEN is required")
        self.session = session
        self._token = token.strip()
        self.endpoint = endpoint
        self.cache_seconds = cache_seconds
        self.clock = clock
        self._cache: OrderedDict[int, tuple[float, SubscriptionResult]] = OrderedDict()
        self._locks: WeakValueDictionary[int, asyncio.Lock] = WeakValueDictionary()

    def _cached(self, user_id: int) -> SubscriptionResult | None:
        entry = self._cache.get(user_id)
        if entry is not None:
            if entry[0] > self.clock():
                self._cache.move_to_end(user_id)
                return entry[1]
            del self._cache[user_id]
        return None

    async def check(self, user_id: int, *, force: bool = False) -> SubscriptionResult:
        if not force:
            cached = self._cached(user_id)
            if cached is not None:
                return cached
        lock = self._locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            if not force:
                cached = self._cached(user_id)
                if cached is not None:
                    return cached
            # A failed explicit recheck invalidates previous success too.
            self._cache.pop(user_id, None)
            result = await self._request(user_id)
            ttl = self.cache_seconds if result.allowed else 3
            self._cache[user_id] = (self.clock() + ttl, result)
            self._cache.move_to_end(user_id)
            while len(self._cache) > 4096:
                self._cache.popitem(last=False)
            return result

    async def _request(self, user_id: int) -> SubscriptionResult:
        try:
            async with self.session.post(
                self.endpoint,
                headers={"Auth": self._token},
                json={"chat_id": user_id, "only_has_check": True},
                timeout=aiohttp.ClientTimeout(total=8),
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    raise BotoHubUnavailable(f"http_{response.status}")
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as error:
            raise BotoHubUnavailable(type(error).__name__) from None
        return parse_result(payload)
