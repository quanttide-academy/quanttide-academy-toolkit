from quanttide_academy import cli
from quanttide_academy.cli.doctor import doctor, selftest
from tests.helpers import *


def test_doctor_and_selftest(env):
    cfg, _tmp = env
    r = doctor(cfg)
    assert r["config"] is True and r["todo_provider"] == "todoist" and r["todoist_token"] == "unset"
    rc, out = run("selftest")
    assert rc == 0 and out["status"] == "ok" and cli.doctor is doctor and cli.selftest is selftest
