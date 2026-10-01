import json
import struct
import threading

import pytest

from codex_account_manager.adapters.native_ide import MAX_FRAME, MAX_RECEIVED, snapshot
from codex_account_manager.adapters.windows_pipe import FramedPipe
from codex_account_manager.core.errors import AppServerError
from tests.unit.test_native_ide import state_message


def wire_pipe(data, *, limit=MAX_FRAME, budget=MAX_RECEIVED):
    pipe = FramedPipe(None, threading.Event(), 12, limit, max_received=budget)
    remaining = bytearray(data)
    requests = []

    def transfer(count):
        requests.append(count)
        result = bytes(remaining[:count])
        del remaining[:count]
        assert result
        return result

    pipe.transfer = transfer
    return pipe, requests


def encoded(message):
    body = json.dumps(message).encode()
    return struct.pack("<I", len(body)) + body


def test_large_ide_history_preserves_latest_turn_and_approval_guard():
    message = state_message(requests=[{"id": "approval"}])
    message["params"]["change"]["conversationState"]["historyText"] = "x" * 7_200_000
    pipe, requests = wire_pipe(encoded(message))
    result = snapshot(pipe.receive(), "thread", "owner")
    assert result.turn == {"id": "last", "status": "failed"}
    assert result.blocked
    assert max(requests) <= 64 * 1024
    assert not hasattr(result, "historyText")


@pytest.mark.parametrize("size", [0, MAX_FRAME + 1, 0xFFFFFFFF])
def test_invalid_frame_rejected_before_body_allocation(size):
    pipe, requests = wire_pipe(struct.pack("<I", size))
    with pytest.raises(AppServerError):
        pipe.receive()
    assert requests == [4]


def test_total_budget_rejects_repeated_frames_before_body_read():
    frame = encoded({"value": "x" * 60})
    size = len(frame) - 4
    pipe, requests = wire_pipe(frame * 3, limit=100, budget=size * 2)
    pipe.receive()
    pipe.receive()
    with pytest.raises(AppServerError, match="total read budget"):
        pipe.receive()
    assert pipe.received == size * 2
    assert requests == [4, size, 4, size, 4]


def test_large_frame_can_arrive_in_small_partial_reads():
    data = bytearray(encoded({"value": "test"}))
    pipe = FramedPipe(None, threading.Event(), 12, 100, max_received=100)

    def transfer(count):
        chunk = bytes(data[: min(count, 2)])
        del data[: len(chunk)]
        return chunk

    pipe.transfer = transfer
    assert pipe.receive() == {"value": "test"}


@pytest.mark.parametrize("owner", ["desktop", "ide"])
async def test_oversized_owner_response_is_not_retried_as_a_connection_delay(owner):
    from unittest.mock import AsyncMock

    from codex_account_manager.adapters.native_desktop import NativeDesktop
    from codex_account_manager.adapters.native_ide import NativeIDE
    from codex_account_manager.core.errors import LocalResponseTooLargeError

    read = AsyncMock(side_effect=LocalResponseTooLargeError("frame size"))
    if owner == "desktop":
        client = NativeDesktop()
        client.latest_turn = read
        wait = client.wait_latest_turn
    else:
        client = NativeIDE()
        client.inspect = read
        wait = client.wait_inspect
    with pytest.raises(LocalResponseTooLargeError):
        await wait("thread", timeout=0.1)
    read.assert_awaited_once()
