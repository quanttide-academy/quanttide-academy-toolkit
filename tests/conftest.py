import gc
import sqlite3
import traceback
import weakref
from pathlib import Path

import pytest

from tests.helpers import ROOT, env  # noqa: F401  夹具在此注册


@pytest.fixture(autouse=True)
def _guard_unclosed_sqlite(monkeypatch):
    real_connect = sqlite3.connect
    base = getattr(real_connect, "_conn_cls", sqlite3.Connection)
    open_conns = {}

    class _Conn(base):
        def close(self):
            open_conns.pop(id(self), None)
            super().close()

    def tracked_connect(*a, **kw):
        kw["factory"] = _Conn
        c = real_connect(*a, **kw)
        frames = [
            f"{Path(f.filename).relative_to(ROOT)}:{f.lineno}"
            for f in traceback.extract_stack()[:-1]
            if f.filename.startswith(str(ROOT)) and ".venv" not in f.filename and not f.filename.endswith("conftest.py")
        ]
        open_conns[id(c)] = (" -> ".join(frames[-2:]) if frames else "unknown", weakref.ref(c))
        return c

    tracked_connect._conn_cls = _Conn
    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    yield
    gc.collect()
    if open_conns:
        leaks = [loc for loc, _ in open_conns.values()]
        for _, ref in list(open_conns.values()):
            conn = ref()
            if conn is not None:
                conn.close()
        open_conns.clear()
        pytest.fail("发现未关闭的 sqlite3 连接：" + ", ".join(leaks))
