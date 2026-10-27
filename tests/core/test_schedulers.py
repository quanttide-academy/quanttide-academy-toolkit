from zoneinfo import ZoneInfo

from quanttide_academy_toolkit.core import schedulers
from tests.helpers import *


def test_schedulers():
    assert schedulers.local_times(["11:30"], ZoneInfo("UTC")) == [(3, 30)]
    for plat in ["win32", "darwin", "linux"]:
        _kind, text, _ = schedulers.for_platform([(11, 30)], plat)
        assert "quanttide_academy_toolkit.cli" in text
