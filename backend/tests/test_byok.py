"""BYOK：玩家自带 DeepSeek API Key 相关单元测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from llm.deepseek_client import _client, _client_for, _friendly_err


class _E401:
    status_code = 401
    code = "invalid_api_key"


class _E429:
    status_code = 429
    code = "rate_limit_exceeded"


def test_client_for_none_falls_back_to_server_client():
    if _client is not None:
        assert _client_for(None) is _client
    else:
        with pytest.raises(RuntimeError):
            _client_for(None)


def test_client_for_player_key_creates_separate_client():
    c = _client_for("sk-player-test")
    assert c.api_key == "sk-player-test"
    if _client is not None:
        assert c is not _client


def test_client_for_blank_key_falls_back():
    if _client is not None:
        assert _client_for("   ") is _client
    else:
        with pytest.raises(RuntimeError):
            _client_for("   ")


def test_friendly_err_invalid_key():
    msg = _friendly_err(_E401())
    assert "API Key" in msg and "无效" in msg


def test_friendly_err_rate_limit():
    msg = _friendly_err(_E429())
    assert "额度" in msg or "限流" in msg


def test_friendly_err_no_server_key():
    msg = _friendly_err(RuntimeError("NO_SERVER_KEY"))
    assert "API Key" in msg


def test_friendly_err_generic():
    msg = _friendly_err(RuntimeError("boom"))
    assert "DeepSeek 调用失败" in msg
