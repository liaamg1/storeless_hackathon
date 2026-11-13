"""The API must start a consumer even when only Uvicorn is launched."""
import asyncio
import runpy
import signal
import sys
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.core import transcription_worker as lifecycle
from app.main import app


class FakeProcess:
    def __init__(self, returncode=None):
        self.pid = 987654321
        self.returncode = returncode
        self.terminated = False
        self.killed = False
        self.exited = asyncio.Event()
        if returncode is not None:
            self.exited.set()

    async def wait(self):
        await self.exited.wait()
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0
        self.exited.set()

    def kill(self):
        self.killed = True
        self.returncode = -9
        self.exited.set()


def test_api_starts_worker_by_default_and_stops_it_on_shutdown(monkeypatch):
    monkeypatch.delenv('AUTO_START_TRANSCRIPTION_WORKER', raising=False)
    events = []
    async def supervise(stopping):
        events.append('started')
        await stopping.wait()
        events.append('stopped')
    monkeypatch.setattr(lifecycle, 'supervise_worker', supervise)
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        assert events == ['started']
    assert events == ['started', 'stopped']


def test_api_can_opt_out_for_a_standalone_worker(monkeypatch):
    async def must_not_start(stopping):
        raise AssertionError('Automatic worker was explicitly disabled')
    monkeypatch.setattr(lifecycle, 'supervise_worker', must_not_start)
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200


def test_worker_uses_same_python_environment_and_is_owned_by_api(monkeypatch):
    async def scenario():
        process = FakeProcess()
        started = asyncio.Event()
        stopping = asyncio.Event()
        commands = []
        async def create(*args, **kwargs):
            commands.append((args, kwargs))
            started.set()
            return process
        monkeypatch.setattr(lifecycle.asyncio, 'create_subprocess_exec', create)
        supervisor = asyncio.create_task(lifecycle.supervise_worker(stopping))
        await asyncio.wait_for(started.wait(), 1)
        stopping.set()
        await asyncio.wait_for(supervisor, 1)
        assert commands == [((sys.executable, '-m', 'app.worker', '--wait-for-lock'), {
            'cwd': str(lifecycle.BACKEND_DIR), 'start_new_session': True,
        })]
        assert process.terminated
    asyncio.run(scenario())


@pytest.mark.parametrize('initial_failure', ['exit', 'start_error'])
def test_supervisor_restarts_a_failed_worker(monkeypatch, initial_failure):
    async def scenario():
        stopping = asyncio.Event()
        started_again = asyncio.Event()
        second_process = FakeProcess()
        calls = []
        async def create(*args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                if initial_failure == 'start_error':
                    raise OSError('private system details')
                return FakeProcess(returncode=1)
            started_again.set()
            return second_process
        async def short_wait(event, seconds):
            try:
                await asyncio.wait_for(event.wait(), 0.01)
            except asyncio.TimeoutError:
                pass
        monkeypatch.setattr(lifecycle.asyncio, 'create_subprocess_exec', create)
        monkeypatch.setattr(lifecycle, 'wait_for_stop', short_wait)
        supervisor = asyncio.create_task(lifecycle.supervise_worker(stopping))
        await asyncio.wait_for(started_again.wait(), 1)
        stopping.set()
        await asyncio.wait_for(supervisor, 1)
        assert len(calls) == 2
        assert second_process.terminated
    asyncio.run(scenario())


def test_shutdown_is_bounded_and_stops_worker_descendants(monkeypatch):
    async def scenario():
        process = FakeProcess()
        def ignore_termination():
            process.terminated = True
        process.terminate = ignore_termination
        monkeypatch.setattr(lifecycle, 'SHUTDOWN_TIMEOUT_SECONDS', 0.01)
        group_signals = []
        if lifecycle.os.name == 'posix':
            def kill_group(pid, signal_number):
                group_signals.append((pid, signal_number))
                process.kill()
            monkeypatch.setattr(lifecycle.os, 'killpg', kill_group)
        await asyncio.wait_for(lifecycle.stop_worker(process), 1)
        assert process.terminated and process.killed
        if lifecycle.os.name == 'posix':
            assert group_signals == [(process.pid, signal.SIGKILL)]
    asyncio.run(scenario())


def test_reload_launcher_watches_source_not_virtualenv(monkeypatch):
    import uvicorn
    from conftest import ROOT
    calls = []
    monkeypatch.chdir(ROOT / 'backend')
    monkeypatch.setattr(uvicorn, 'run', lambda *args, **kwargs: calls.append((args, kwargs)))
    runpy.run_path(str(ROOT / 'backend/dev.py'), run_name='__main__')
    _, options = calls[0]
    assert options['reload'] is True
    watched = [Path(path) for path in options['reload_dirs']]
    assert watched == [ROOT / 'backend/app']
    for excluded in ['.venv', '.cache', 'uploads', 'tests']:
        directory = ROOT / 'backend' / excluded
        assert not any(path == directory or path in directory.parents for path in watched)
