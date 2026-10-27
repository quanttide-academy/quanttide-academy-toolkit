import tempfile

from quanttide_academy_toolkit import settings
from tests.helpers import *


def test_root_and_pkg():
    assert (settings.ROOT / "pyproject.toml").exists() and (settings.PKG / "core" / "schema.sql").exists()


def test_config_path_override(tmp_path, monkeypatch):
    monkeypatch.delenv("FEISHU_INTENT_CONFIG", raising=False)
    monkeypatch.delenv("FEISHU_WORKFLOWS_CONFIG", raising=False)
    assert settings.config_path() == settings.ROOT / "config.yaml"
    with settings.override_config(tmp_path / "c.yaml"):
        assert settings.config_path() == tmp_path / "c.yaml"
    assert settings.config_path() == settings.ROOT / "config.yaml"


def test_guard_test_path(monkeypatch):
    monkeypatch.setenv("FI_TEST", "1")
    with pytest.raises(settings.UnsafeTestPath):
        settings.guard_test_path(settings.ROOT / "data")
    p = Path(tempfile.gettempdir()) / "x" / "y.db"
    assert settings.guard_test_path(p) == p


def test_has_secret(monkeypatch):
    monkeypatch.setenv("FI_X_TOKEN", "v")
    assert settings.has_secret("FI_X_TOKEN")
    monkeypatch.delenv("FI_X_TOKEN")
    assert not settings.has_secret("FI_X_TOKEN") and not settings.has_secret(None)


def test_sensitive_hmac_settings(tmp_path, monkeypatch):
    monkeypatch.delenv(settings.SENSITIVE_HMAC_ENV, raising=False)
    monkeypatch.delenv(settings.SENSITIVE_HASHES_ENV, raising=False)
    assert (
        settings.sensitive_hmac_key() is None
        and settings.sensitive_hashes_path() == settings.ROOT / "data" / "sensitive_hashes.txt"
    )
    monkeypatch.setenv(settings.SENSITIVE_HMAC_ENV, "  my-key  ")
    monkeypatch.setenv(settings.SENSITIVE_HASHES_ENV, str(tmp_path / "h.txt"))
    assert settings.sensitive_hmac_key() == b"my-key" and settings.sensitive_hashes_path() == tmp_path / "h.txt"
