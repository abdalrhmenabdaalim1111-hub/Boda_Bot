"""
tests/cc_fixtures.py — shared fixtures for the Control Center test-suite.

Kept out of ``conftest.py`` on purpose: the project has no global conftest
and adding one could change the behaviour of the existing 363 tests.
"""

import io
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
BOTS_DIR = ROOT / "Bots_Folder"
for _p in (str(ROOT), str(BOTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture()
def cc_db(tmp_path, monkeypatch):
    """
    An isolated SQLite database with the Control Center schema applied.

    The bots' own schema is bootstrapped by ``BodaDatabase`` and the Control
    Center schema by the migration runner — exactly like production.
    """
    db_file = tmp_path / "cc_test.db"
    monkeypatch.setenv("BODA_DB_PATH", str(db_file))

    import database
    from control_center import db as cc_db_module
    from control_center import migrations as cc_migrations

    database.BodaDatabase.reset_instance()
    cc_db_module.reset_db()

    conn = cc_db_module.connect(str(db_file))
    cc_migrations.apply_migrations(conn, backup=False)
    conn.close()

    db = database.get_db()
    yield db

    database.BodaDatabase.reset_instance()
    cc_db_module.reset_db()


class FakeProcess:
    """A stand-in for ``subprocess.Popen`` used by the tests."""

    _next_pid = [41000]

    def __init__(self, lines=(), exit_code=0):
        FakeProcess._next_pid[0] += 1
        self.pid = FakeProcess._next_pid[0]
        self.returncode = None
        self._exit_code = exit_code
        self.stdout = io.StringIO("".join(f"{line}\n" for line in lines))
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = self._exit_code

    def kill(self):
        self.killed = True
        self.returncode = self._exit_code

    def crash(self, code=1):
        """Simulate an unexpected exit."""
        self.returncode = code


@pytest.fixture()
def cc_supervisor(monkeypatch):
    """
    A supervisor whose process factory is faked.

    Without this the API tests would spawn the **real** bot processes, which
    crash, restart on a backoff and lock the test database.
    """
    from control_center.api import reset_supervisor
    from control_center.supervisor import BotSupervisor

    created = []

    def _spawner(bot_id):
        proc = FakeProcess(lines=[f"started {bot_id}"])
        created.append(proc)
        return proc

    reset_supervisor()
    supervisor = BotSupervisor(base_dir=ROOT,
                               registry_path=ROOT / "bots_registry.json",
                               spawner=_spawner)
    supervisor.created = created

    import control_center.api as cc_api
    monkeypatch.setattr(cc_api, "get_supervisor", lambda: supervisor)

    yield supervisor

    supervisor.shutdown()
    reset_supervisor()


@pytest.fixture()
def cc_router():
    """The Control Center router with a fresh route table."""
    from control_center.api import ROUTER
    return ROUTER


# Pytest only auto-discovers fixtures declared in ``conftest.py``. This module
# is imported explicitly by every Control Center test file, so the fixtures
# have to be re-exported here for the import to bind them to the module.
__all__ = ["cc_db", "cc_router", "cc_supervisor", "FakeProcess",
           "ROOT", "BOTS_DIR"]
