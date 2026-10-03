"""Tie owned Codex children to a Windows job, including after a parent crash."""

from __future__ import annotations

import asyncio
import sys


class ChildProcessLifetime:
    def __init__(self):
        self._job = None

    def attach(self, pid: int) -> None:
        if sys.platform != "win32":
            return
        import win32api
        import win32con
        import win32job

        job = win32job.CreateJobObject(None, "")
        try:
            limits = win32job.QueryInformationJobObject(
                job, win32job.JobObjectExtendedLimitInformation
            )
            limits["BasicLimitInformation"]["LimitFlags"] |= (
                win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            )
            win32job.SetInformationJobObject(
                job, win32job.JobObjectExtendedLimitInformation, limits
            )
            process = win32api.OpenProcess(
                win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE, False, pid
            )
            try:
                win32job.AssignProcessToJobObject(job, process)
            finally:
                process.Close()
            self._job = job
        except BaseException:
            job.Close()
            raise

    def close(self) -> None:
        if self._job is not None:
            self._job.Close()
            self._job = None


async def finish_cleanup(awaitable) -> None:
    """Do not release credential leases while cancellation interrupts teardown."""
    task = asyncio.create_task(awaitable)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    task.result()
    if cancelled:
        raise asyncio.CancelledError()


async def stop_owned_process(process, lifetime: ChildProcessLifetime) -> None:
    lifetime.close()
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    await asyncio.wait_for(process.wait(), timeout=3)
