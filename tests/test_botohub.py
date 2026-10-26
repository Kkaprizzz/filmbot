import asyncio
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import aiohttp
import pytest
from aiohttp import web

from core.botohub import BotoHubClient, BotoHubUnavailable, parse_result

PENDING = {
    "tasks": [{"url": "https://t.me/channel", "resource_id": "-100123", "completed": False}],
    "completed": False, "skip": False,
}
SUCCESS = {"tasks": [], "completed": True, "skip": False}
SKIP = {"tasks": [], "completed": False, "skip": True}


@asynccontextmanager
async def api(responses, **client_options):
    calls = []

    async def endpoint(request):
        calls.append({"auth": request.headers.get("Auth"), "json": await request.json()})
        status, payload = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(payload, str):
            return web.Response(text=payload, status=status)
        return web.json_response(payload, status=status)

    app = web.Application()
    app.router.add_post("/get-tasks-extended", endpoint)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        async with aiohttp.ClientSession() as session:
            client = BotoHubClient(session, "private-test-token",
                                   endpoint=f"http://127.0.0.1:{port}/get-tasks-extended",
                                   **client_options)
            yield client, calls
    finally:
        await runner.cleanup()


async def test_extended_contract_header_and_configuration_from_botohub():
    async with api([(200, PENDING)]) as (client, calls):
        result = await client.check(777)
        assert not result.allowed
        assert result.tasks[0].resource_id == "-100123"
        assert calls == [{"auth": "private-test-token", "json": {
            "chat_id": 777, "only_has_check": True,
        }}]


@pytest.mark.parametrize("payload", [SUCCESS, SKIP, {**SKIP, "fake": True}])
async def test_success_and_no_offers_allow_access(payload):
    async with api([(200, payload)]) as (client, _):
        assert (await client.check(777)).allowed


async def test_check_button_forces_refresh_and_caches_are_per_user():
    async with api([(200, PENDING), (200, SUCCESS), (200, PENDING)]) as (client, calls):
        assert not (await client.check(777)).allowed
        assert (await client.check(777, force=True)).allowed
        assert (await client.check(777)).allowed
        assert not (await client.check(888)).allowed
        assert len(calls) == 3


async def test_cache_expires_and_concurrent_requests_share_a_check():
    now = [0.0]
    async with api([(200, SUCCESS), (200, PENDING)], clock=lambda: now[0]) as (client, calls):
        results = await asyncio.gather(*[client.check(777) for _ in range(10)])
        assert all(result.allowed for result in results)
        assert len(calls) == 1
        now[0] = 31
        assert not (await client.check(777)).allowed
        assert len(calls) == 2


@pytest.mark.parametrize("status", [400, 401, 429, 500, 302])
async def test_http_errors_do_not_authorize_or_expose_response_body(status):
    async with api([(status, {"error": "sensitive-provider-details"})]) as (client, _):
        with pytest.raises(BotoHubUnavailable) as error:
            await client.check(777)
        assert str(error.value) == f"http_{status}"


async def test_failed_explicit_recheck_invalidates_old_success():
    async with api([(200, SUCCESS), (401, {})]) as (client, calls):
        assert (await client.check(777)).allowed
        with pytest.raises(BotoHubUnavailable):
            await client.check(777, force=True)
        with pytest.raises(BotoHubUnavailable):
            await client.check(777)
        assert len(calls) == 3


async def test_non_json_is_not_a_success():
    async with api([(200, "<html>upstream error</html>")]) as (client, _):
        with pytest.raises(BotoHubUnavailable):
            await client.check(777)


@pytest.mark.parametrize("failure", [TimeoutError, aiohttp.ClientConnectionError])
async def test_network_errors_are_sanitized(failure):
    session = MagicMock()
    session.post.side_effect = failure("private-test-token")
    client = BotoHubClient(session, "private-test-token")
    with pytest.raises(BotoHubUnavailable) as error:
        await client.check(777)
    assert "private-test-token" not in str(error.value)


@pytest.mark.parametrize("payload", [
    {}, {"tasks": []}, {"error": "Unauthorized"}, [],
    {**SUCCESS, "completed": "true"}, {**SUCCESS, "skip": 1},
    {**SUCCESS, "tasks": None},
    {**PENDING, "tasks": []},
    {**PENDING, "tasks": ["https://t.me/channel"]},
    {**PENDING, "tasks": [{"url": "javascript:bad", "resource_id": "1", "completed": False}]},
    {**PENDING, "tasks": [{"url": "https://t.me/channel", "resource_id": "1"}]},
])
def test_ambiguous_or_invalid_payload_is_closed(payload):
    with pytest.raises(BotoHubUnavailable):
        parse_result(payload)


def test_completed_sponsors_remain_visible():
    payload = {**PENDING, "tasks": [
        {"url": "https://t.me/done", "resource_id": "1", "completed": True},
        {"url": "https://t.me/pending", "resource_id": "2", "completed": False},
    ]}
    result = parse_result(payload)
    assert not result.allowed
    assert len(result.tasks) == 2
    assert result.tasks[0].completed


def test_missing_token_fails_without_dumping_configuration():
    with pytest.raises(RuntimeError, match="BOTOHUB_TOKEN is required"):
        BotoHubClient(MagicMock(), "")
