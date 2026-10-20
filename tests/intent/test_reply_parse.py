from feishu_workflows.intent.reply_parse import parse_reply
from tests.helpers import *


@pytest.mark.parametrize(
    "t", ["整理一下", "都行吧", "好的", "可以", "没问题，都写吧", "全部写入", "先别写入 #8", "不要写入#8", "看着办"]
)
def test_vague_never_confirms(t):
    acts, q = parse_reply(t)
    assert not any(a["action"] == "confirm" and a["no"] is not None for a in acts)
    assert q or all(a["no"] is None for a in acts)


def test_parse_reply_explicit():
    assert parse_reply("#6、#8 写入；#7 否决")[0] == [
        {"action": "confirm", "no": 6},
        {"action": "confirm", "no": 8},
        {"action": "reject", "no": 7},
    ]
    assert parse_reply("否决 7")[0] == [{"action": "reject", "no": 7}]
    a = parse_reply("#8 修改：截止改到周五")[0]
    assert a == [{"action": "modify", "no": 8, "instruction": "截止改到周五"}]
    assert parse_reply("#8 写入 #8 否决")[1]
