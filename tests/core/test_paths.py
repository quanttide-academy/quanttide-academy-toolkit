from feishu_workflows.core import paths
from tests.helpers import *


def test_paths_default_and_override(tmp_path):
    cfg = {"paths": {"data_dir": str(tmp_path / "数据 dir")}}
    assert paths.state_db(cfg).parent == tmp_path / "数据 dir"
    assert paths.candidates_dir(cfg).is_dir()
    assert paths.followups_path({}) is None
    assert paths.data_dir({}).is_absolute()
