from feishu_workflows.cli import common
from tests.helpers import *


def test_redact_and_batch_re():
    assert common.redact("Bearer secret_token_1234567890") == "***"
    assert common.redact("u-abcdefghijklmnopqrstuvwx") == "***"
    assert common.BATCH_RE.match("20261020-0800") and not common.BATCH_RE.match("../bad")


def test_invalid_topics_abort(env):
    cfg, tmp = env
    t = copy.deepcopy(EX)
    t["items"][0]["relation"] = "不知道"
    prepare(cfg, tmp, topics=t)
    rc, r = run("validate", "b1")
    assert rc == 20 and r["status"] == "incomplete"
    assert run("fetch", "b3", "--from", str(ROOT / "tests" / "fixtures" / "messages.json"))[0] == 10
