import asyncio
import json
import os
import subprocess
import sys

import psutil
import pytest

from codex_account_manager.codex.runtime import codex_command


@pytest.mark.skipif(sys.platform != "win32", reason="Windows command processor")
@pytest.mark.parametrize("suffix", [".cmd", ".bat"])
async def test_batch_wrapper_preserves_arguments_with_unicode_and_spaces(tmp_path, suffix):
    folder = tmp_path / "Çalışmalar with spaces"
    folder.mkdir()
    wrapper = folder / ("fake codex" + suffix)
    wrapper.write_text(
        '@echo off\n"%CODEX_TEST_PYTHON%" -c "import json,sys;print(json.dumps(sys.argv[1:]))" %*\n',
        encoding="utf-8",
    )
    arguments = ["login", "--example", "iki sözcük", "", "stdio://"]
    command = codex_command(*arguments, executable=str(wrapper))
    env = {**os.environ, "CODEX_TEST_PYTHON": sys.executable}
    # Verify argument handling, allowing for cold Windows process startup.
    # Product deadlines are tested separately; this is not a latency benchmark.
    result = subprocess.run(command, capture_output=True, text=True, timeout=60, env=env)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == arguments
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
        env=env,
    )
    communication = asyncio.create_task(process.communicate())
    try:
        stdout, stderr = await asyncio.wait_for(asyncio.shield(communication), timeout=60)
    finally:
        if process.returncode is None:
            try:
                children = psutil.Process(process.pid).children(recursive=True)
            except psutil.NoSuchProcess:
                children = []
            for child in children:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            if process.returncode is None:
                process.kill()
        await communication
        await process.wait()
    assert process.returncode == 0, stderr
    assert json.loads(stdout) == arguments


@pytest.mark.parametrize("unsafe", ['"', "%", "!", "&", "|", "<", ">", "^", "(", ")", "\r", "\n"])
def test_batch_wrapper_rejects_shell_syntax(unsafe):
    with pytest.raises(ValueError, match="Unsafe shell characters"):
        codex_command("login", unsafe, executable="codex.cmd")
    with pytest.raises(ValueError, match="Unsafe shell characters"):
        codex_command("login", executable=f"unsafe{unsafe}codex.cmd")


def test_native_executable_keeps_arguments_literal():
    assert codex_command("a&b", executable="codex.exe") == ["codex.exe", "a&b"]
