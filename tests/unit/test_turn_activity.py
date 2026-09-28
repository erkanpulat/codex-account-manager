import json
import os
import time

import pytest

from codex_account_manager.codex.turn_activity import read_turn_activity


def event(kind, turn="turn"):
    return json.dumps({"type": "event_msg", "payload": {"type": kind, "turn_id": turn}}) + "\n"


@pytest.fixture
def rollout(tmp_path):
    folder = tmp_path / "sessions"
    folder.mkdir()
    return folder / "rollout.jsonl"


def test_running_turn_is_read_from_lifecycle_without_returning_content(rollout, tmp_path):
    rollout.write_text(
        event("task_started")
        + json.dumps({"type": "response_item", "payload": {"text": "private message"}})
        + "\n"
    )
    assert read_turn_activity(str(rollout), tmp_path, "turn") == "inProgress"


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("turn_aborted", "interrupted"),
        ("task_complete", "completed"),
        ("task_completed", "completed"),
    ],
)
def test_terminal_event_wins_over_start(rollout, tmp_path, kind, expected):
    rollout.write_text(event("task_started") + event(kind))
    assert read_turn_activity(str(rollout), tmp_path, "turn") == expected


@pytest.mark.parametrize("ending", ['{"type":', "invalid\n", event("task_started", "new-turn")])
def test_partial_corrupt_or_different_turn_cannot_prove_activity(rollout, tmp_path, ending):
    rollout.write_text(event("task_started") + ending)
    assert read_turn_activity(str(rollout), tmp_path, "turn") == "unknown"


def test_stale_unfinished_record_is_not_claimed_to_be_running(rollout, tmp_path):
    rollout.write_text(event("task_started"))
    old = time.time() - 300
    os.utime(rollout, (old, old))
    assert read_turn_activity(str(rollout), tmp_path, "turn") == "unknown"


def test_paths_outside_sessions_are_not_read(tmp_path):
    outside = tmp_path / "credentials.jsonl"
    outside.write_text(event("task_started"))
    assert read_turn_activity(str(outside), tmp_path, "turn") == "unknown"


def test_tail_budget_does_not_invent_a_missing_start(rollout, tmp_path, monkeypatch):
    import codex_account_manager.codex.turn_activity as module

    monkeypatch.setattr(module, "_MAX_TAIL_BYTES", 128)
    rollout.write_text(
        event("task_started") + json.dumps({"type": "response_item", "payload": "x" * 500}) + "\n"
    )
    assert read_turn_activity(str(rollout), tmp_path, "turn") == "unknown"


def test_missing_rollout_is_unknown(rollout, tmp_path):
    assert read_turn_activity(str(rollout), tmp_path, "turn") == "unknown"


@pytest.mark.skipif(os.name != "nt", reason="Windows extended paths")
def test_windows_extended_path_is_validated_and_read(rollout, tmp_path):
    rollout.write_text(event("task_started"))
    assert read_turn_activity("\\\\?\\" + str(rollout), tmp_path, "turn") == "inProgress"


@pytest.mark.parametrize(
    "ahead,expected", [(0.01, "inProgress"), (0.5, "inProgress"), (2, "unknown")]
)
def test_filesystem_clock_skew_is_bounded(rollout, tmp_path, monkeypatch, ahead, expected):
    import codex_account_manager.codex.turn_activity as module

    rollout.write_text(event("task_started"))
    modified = rollout.stat().st_mtime
    monkeypatch.setattr(module.time, "time", lambda: modified - ahead)
    assert read_turn_activity(str(rollout), tmp_path, "turn") == expected
