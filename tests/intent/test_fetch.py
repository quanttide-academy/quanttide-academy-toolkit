from quanttide_academy_toolkit.core import config
from quanttide_academy_toolkit.intent import fetch as flow_fetch
from tests.helpers import *


def test_fingerprint_and_footer():
    assert flow_fetch.fingerprint({"links": [{"message_id": "om_a"}, {"message_id": "om_b"}]}) == "om:om_a"
    assert flow_fetch.FOOTER == "可以直接回复：写入、修改、说明或否决（可带序号）。"


def test_render_skips_rejected(env):
    cfg, tmp = env
    prepare(cfg, tmp)
    rc, _ = run("validate", "b1")
    assert rc == 0
    rc, _r = run("render", "b1")
    assert rc == 0
    cards = (Path(config.load()["paths"]["work_dir"]) / "b1" / "cards.txt").read_text(encoding="utf-8")
    assert cards.rstrip().endswith(flow_fetch.FOOTER)
