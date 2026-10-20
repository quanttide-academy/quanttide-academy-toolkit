"""A/B 渲染回归：intent 并入 watch 之后，A、B 两组的卡片版本与 cards.txt 必须与基线逐字节一致。
基线在 local/e2e-golden-versions-<组>.json（含真实消息 ID，只放本地、不入库）；缺本地数据则跳过。"""

import pytest

from integrated_tests import e2e_render as E


@pytest.mark.parametrize("scope", ["A", "B"])
def test_render_versions_unchanged(scope):
    g = E.ROOT / "data" / f"e2e-golden-versions-{scope}.json"
    if not (E.available(scope) and g.exists()):
        pytest.skip("缺本地 e2e 数据或基线")
    E.render(scope)
    assert (E.OUT[scope] / "versions.json").read_bytes() == g.read_bytes()
