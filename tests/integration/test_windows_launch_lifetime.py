"""Exercise real Windows job termination without touching Codex or user accounts."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows Explorer and job objects")


@pytest.mark.parametrize("through_explorer", [False, True])
def test_shell_launch_survives_only_when_delegated_to_explorer(tmp_path, through_explorer):
    import win32api
    import win32event
    import win32job
    import win32process

    marker = tmp_path / "ready.json"
    child = tmp_path / "child.py"
    child.write_text(
        "import os, json, time\nfrom pathlib import Path\n"
        f"Path({str(marker)!r}).write_text(json.dumps({{'pid': os.getpid()}}))\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    executable = sys._base_executable
    launcher = tmp_path / "launcher.py"
    root = Path(__file__).resolve().parents[2]
    launch = (
        "from codex_account_manager.core.windows_shell import launch_from_explorer\n"
        f"launch_from_explorer(Path({executable!r}), [{str(child)!r}], visible=False)\n"
        if through_explorer
        else "import win32com.client\n"
        f"win32com.client.Dispatch('Shell.Application').ShellExecute({executable!r}, "
        f"{subprocess.list2cmdline([str(child)])!r}, {str(tmp_path)!r}, 'open', 0)\n"
    )
    launcher.write_text(
        "import site, sys, time\nfrom pathlib import Path\n"
        f"site.addsitedir({str(Path(sys.prefix) / 'Lib/site-packages')!r})\n"
        f"sys.path.insert(0, {str(root / 'src')!r})\n" + launch + "time.sleep(60)\n",
        encoding="utf-8",
    )
    job = win32job.CreateJobObject(None, "")
    info = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
    info["BasicLimitInformation"]["LimitFlags"] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, info)
    process, thread, _, _ = win32process.CreateProcess(
        executable,
        subprocess.list2cmdline([executable, str(launcher)]),
        None,
        None,
        False,
        win32process.CREATE_SUSPENDED | win32process.CREATE_NO_WINDOW,
        None,
        str(tmp_path),
        win32process.STARTUPINFO(),
    )
    child_handle = None
    try:
        win32job.AssignProcessToJobObject(job, process)
        win32process.ResumeThread(thread)
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.exists(), "The isolated launcher failed to start its child."
        child_handle = win32api.OpenProcess(
            0x1000 | 0x100000 | 1, False, json.loads(marker.read_text())["pid"]
        )
        assert bool(win32job.IsProcessInJob(child_handle, job)) is not through_explorer
        win32job.TerminateJobObject(job, 99)
        assert win32event.WaitForSingleObject(process, 5000) == 0
        assert (win32event.WaitForSingleObject(child_handle, 1000) == 258) is through_explorer
    finally:
        if child_handle:
            if win32event.WaitForSingleObject(child_handle, 0) == 258:
                win32api.TerminateProcess(child_handle, 0)
                win32event.WaitForSingleObject(child_handle, 5000)
            child_handle.Close()
        win32job.TerminateJobObject(job, 99)
        process.Close()
        thread.Close()
        job.Close()
