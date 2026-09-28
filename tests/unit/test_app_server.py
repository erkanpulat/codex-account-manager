import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from codex_account_manager.adapters.app_server import CodexAppServer
from codex_account_manager.core.errors import AppServerError


async def test_failed_send_cleans_pending_request(monkeypatch):
    server = CodexAppServer("test", timeout=0.02)
    monkeypatch.setattr(server, "_send", AsyncMock(side_effect=AppServerError("broken pipe")))
    with pytest.raises(AppServerError):
        await server._request("account/read")
    assert server._pending == {}


async def test_timeout_cleans_pending_request(monkeypatch):
    server = CodexAppServer("test", timeout=0.01)
    monkeypatch.setattr(server, "_send", AsyncMock())
    with pytest.raises(AppServerError, match="timed out"):
        await server._request("account/read")
    assert server._pending == {}


async def test_reader_ignores_nonobjects_and_server_request_id_collision(monkeypatch):
    server = CodexAppServer("test")
    stream = asyncio.StreamReader()
    for payload in [[], None, {"id": 1, "method": "approval"}, {"id": 1, "result": {"ok": True}}]:
        stream.feed_data((json.dumps(payload) + "\n").encode())
    stream.feed_eof()
    server._proc = SimpleNamespace(stdout=stream)
    pending = asyncio.get_running_loop().create_future()
    server._pending[1] = pending
    send = AsyncMock()
    monkeypatch.setattr(server, "_send", send)
    await server._read_loop()
    assert await pending == {"ok": True}
    assert send.call_args.args[0]["error"]["code"] == -32601


async def test_multibucket_limits_preferred(monkeypatch):
    server = CodexAppServer("test")
    monkeypatch.setattr(
        server,
        "_request",
        AsyncMock(
            side_effect=[
                {"account": {"type": "chatgpt", "accountId": "account"}},
                {
                    "rateLimits": {"primary": {"usedPercent": 99}},
                    "rateLimitsByLimitId": {"codex": {"primary": {"usedPercent": 12}}},
                },
            ]
        ),
    )
    snapshot = await server.read_account()
    assert snapshot.primary_used_percent == 12
    assert snapshot.account_id == "account"


async def test_capabilities_do_not_claim_unprobed_methods(monkeypatch):
    server = CodexAppServer("test")
    monkeypatch.setattr(server, "_request", AsyncMock(return_value={}))
    capabilities = await server.capabilities()
    assert "thread/goal/set" not in capabilities.methods


async def test_list_threads_collects_pages(monkeypatch):
    server = CodexAppServer("test")
    request = AsyncMock(
        side_effect=[{"data": [{"id": "one"}], "nextCursor": "next"}, {"data": [{"id": "two"}]}]
    )
    monkeypatch.setattr(server, "_request", request)
    assert [thread.id for thread in await server.list_threads()] == ["one", "two"]
    assert request.call_args.args[1]["cursor"] == "next"


async def test_monitoring_thread_query_is_bounded_and_excludes_subagents(monkeypatch):
    server = CodexAppServer("test")
    request = AsyncMock(
        return_value={
            "data": [{"id": str(index)} for index in range(30)],
            "nextCursor": "another-page",
        }
    )
    monkeypatch.setattr(server, "_request", request)
    threads = await server.list_threads(max_items=30, include_subagents=False)
    assert len(threads) == 30
    request.assert_awaited_once()
    params = request.call_args.args[1]
    assert params["limit"] == 30
    assert params["useStateDbOnly"] is True
    assert "subAgent" not in params["sourceKinds"]


async def test_observation_recognizes_live_turn_misreported_as_interrupted(tmp_path, monkeypatch):
    import json

    sessions = tmp_path / "sessions"
    sessions.mkdir()
    rollout = sessions / "rollout.jsonl"
    rollout.write_text(
        json.dumps({"type": "event_msg", "payload": {"type": "task_started", "turn_id": "turn"}})
        + "\n"
    )
    server = CodexAppServer(tmp_path)
    request = AsyncMock(
        side_effect=[
            {"data": [{"id": "turn", "status": "interrupted"}]},
            {"thread": {"id": "thread", "path": str(rollout)}},
        ]
    )
    monkeypatch.setattr(server, "_request", request)
    observed = await server.observed_turn("thread")
    assert observed["id"] == "turn"
    assert observed["status"] == "inProgress"


async def test_observation_does_not_guess_when_lifecycle_is_unreadable(monkeypatch):
    server = CodexAppServer("missing")
    request = AsyncMock(
        side_effect=[
            {"data": [{"id": "turn", "status": "interrupted"}]},
            {"thread": {"id": "thread", "path": None}},
        ]
    )
    monkeypatch.setattr(server, "_request", request)
    with pytest.raises(AppServerError, match="live conversation state"):
        await server.observed_turn("thread")


async def test_repeated_cursor_fails_instead_of_looping(monkeypatch):
    server = CodexAppServer("test")
    monkeypatch.setattr(
        server, "_request", AsyncMock(return_value={"data": [], "nextCursor": "same"})
    )
    with pytest.raises(AppServerError, match="repeated"):
        await server.list_threads()


async def test_thread_metadata_and_all_sources_request(monkeypatch):
    server = CodexAppServer("test")
    request = AsyncMock(
        return_value={
            "data": [
                {
                    "id": "desktop",
                    "name": "Actual title",
                    "source": "vscode",
                    "projectId": "project",
                    "modelProvider": "openai",
                },
                {"id": "agent", "source": {"subAgent": {"review": {}}}},
                {"id": "unknown"},
            ]
        }
    )
    monkeypatch.setattr(server, "_request", request)
    threads = await server.list_threads()
    assert threads[0].title == "Actual title"
    assert threads[0].project_id == "project"
    assert threads[0].model_provider == "openai"
    assert [t.source for t in threads] == ["vscode", "subAgent", "unknown"]
    params = request.call_args.args[1]
    assert {"vscode", "cli", "appServer", "subAgent", "unknown"} <= set(params["sourceKinds"])
    assert params["modelProviders"] == []
    assert params["sortKey"] == "updated_at" and params["sortDirection"] == "desc"


@pytest.mark.parametrize("response", [{}, [], {"goal": {}}, {"goal": "invalid"}])
async def test_malformed_native_goal_is_unknown_not_missing(monkeypatch, response):
    server = CodexAppServer("test")
    monkeypatch.setattr(server, "_request", AsyncMock(return_value=response))
    assert await server.get_goal("thread") is None


async def test_only_explicit_null_confirms_absent_native_goal(monkeypatch):
    server = CodexAppServer("test")
    monkeypatch.setattr(server, "_request", AsyncMock(return_value={"goal": None}))
    goal = await server.get_goal("thread")
    assert goal is not None and not goal.present


@pytest.mark.parametrize(
    "response", [{}, {"goal": None}, {"goal": {"objective": "Different goal"}}]
)
async def test_goal_write_requires_server_confirmation(monkeypatch, response):
    server = CodexAppServer("test")
    monkeypatch.setattr(server, "_request", AsyncMock(return_value=response))
    with pytest.raises(AppServerError, match="did not confirm"):
        await server.set_goal("thread", "Requested goal")


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"data": None},
        {"data": {}},
        {"data": [None]},
        {"data": [{"id": ""}]},
        {"data": [{"id": 7}]},
        {"data": [], "nextCursor": {}},
    ],
)
async def test_malformed_conversation_page_is_rejected(monkeypatch, response):
    server = CodexAppServer("test")
    monkeypatch.setattr(server, "_request", AsyncMock(return_value=response))
    with pytest.raises(AppServerError, match="invalid"):
        await server.list_threads()


@pytest.mark.parametrize("event_kind", ["complete", "approval", "disconnect", "cancel"])
async def test_continuation_waits_for_terminal_event_and_interrupts_when_needed(
    monkeypatch, event_kind
):
    server = CodexAppServer("test", experimental=True)
    sent = []
    started = asyncio.Event()

    async def request(method, params):
        sent.append((method, params))
        if method == "thread/read":
            return {"thread": {"id": "t", "status": {"type": "idle"}}}
        if method == "turn/interrupt":
            return {}
        assert method == "turn/start"
        assert set(params) == {"threadId", "clientUserMessageId", "input"}
        assert params["threadId"] == "t"
        events = server._turn_events
        if event_kind == "complete":
            events.put_nowait({"threadId": "other", "turn": {"id": "other", "status": "completed"}})
            events.put_nowait({"threadId": "t", "turn": {"id": "turn", "status": "completed"}})
        elif event_kind == "approval":
            events.put_nowait({"request": True, "method": "item/commandExecution/requestApproval"})
        elif event_kind == "disconnect":
            events.put_nowait({"closed": True})
        started.set()
        return {"turn": {"id": "turn", "status": "inProgress"}}

    monkeypatch.setattr(server, "_request", request)
    if event_kind == "complete":
        assert (await server.run_continuation_turn("t", "message"))["status"] == "completed"
        assert not any(method == "turn/interrupt" for method, _ in sent)
    elif event_kind == "cancel":
        task = asyncio.create_task(server.run_continuation_turn("t", "message"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(AppServerError):
            await server.run_continuation_turn("t", "message")
    if event_kind != "complete":
        assert sent[-1] == ("turn/interrupt", {"threadId": "t", "turnId": "turn"})
    assert server._turn_events is None


async def test_continuation_does_not_steer_an_already_running_turn(monkeypatch):
    server = CodexAppServer("test")
    request = AsyncMock(return_value={"thread": {"id": "t", "status": {"type": "active"}}})
    monkeypatch.setattr(server, "_request", request)
    with pytest.raises(AppServerError, match="already running"):
        await server.run_continuation_turn("t", "message")
    assert request.await_count == 1
    assert server._turn_events is None


async def test_usage_goal_reactivation_only_updates_status_and_preserves_budget(monkeypatch):
    from codex_account_manager.adapters.interfaces import GoalInfo

    server = CodexAppServer("test")
    request = AsyncMock(return_value={})
    monkeypatch.setattr(server, "_request", request)
    previous = GoalInfo("t", "Task", "usageLimited", True, 1234, 456)
    monkeypatch.setattr(
        server, "get_goal", AsyncMock(return_value=GoalInfo("t", "Task", "active", True, 1234, 456))
    )
    await server.reactivate_usage_limited_goal("t", previous)
    request.assert_awaited_once_with("thread/goal/set", {"threadId": "t", "status": "active"})
    monkeypatch.setattr(
        server, "get_goal", AsyncMock(return_value=GoalInfo("t", "Task", "active", True, 1234, 0))
    )
    with pytest.raises(AppServerError, match="verify"):
        await server.reactivate_usage_limited_goal("t", previous)


async def test_continuation_reader_discards_content_and_rejects_approval(monkeypatch):
    server = CodexAppServer("test")
    server._turn_events = asyncio.Queue(maxsize=16)
    stream = asyncio.StreamReader()
    for payload in [
        {"method": "item/agentMessage/delta", "params": {"delta": "private conversation"}},
        {
            "id": 2,
            "method": "item/commandExecution/requestApproval",
            "params": {"threadId": "t", "command": "private command"},
        },
        {
            "method": "turn/completed",
            "params": {
                "threadId": "t",
                "turn": {"id": "turn", "status": "completed", "items": ["private output"]},
            },
        },
    ]:
        stream.feed_data((json.dumps(payload) + "\n").encode())
    stream.feed_eof()
    server._proc = SimpleNamespace(stdout=stream)
    send = AsyncMock()
    monkeypatch.setattr(server, "_send", send)
    await server._read_loop()
    messages = []
    while not server._turn_events.empty():
        messages.append(server._turn_events.get_nowait())
    assert "private" not in json.dumps(messages)
    assert "result" not in send.call_args.args[0]
    assert send.call_args.args[0]["error"]["code"] == -32601


@pytest.mark.parametrize("source", ["vscode", "unknown", None, {"subAgent": "spawn"}])
async def test_desktop_and_unknown_conversations_are_not_taken_over(monkeypatch, source):
    server = CodexAppServer("test")
    request = AsyncMock(return_value={"thread": {"id": "t", "source": source}})
    monkeypatch.setattr(server, "_request", request)
    with pytest.raises(AppServerError, match="Desktop tools"):
        await server.resume_for_continuation("t")
    request.assert_awaited_once_with("thread/read", {"threadId": "t", "includeTurns": False})


@pytest.mark.parametrize("source", ["cli", "exec", "appServer"])
async def test_cli_conversations_allow_headless_compatibility_check(monkeypatch, source):
    server = CodexAppServer("test")
    monkeypatch.setattr(
        server, "_request", AsyncMock(return_value={"thread": {"id": "t", "source": source}})
    )
    await server.require_headless_compatible("t")
