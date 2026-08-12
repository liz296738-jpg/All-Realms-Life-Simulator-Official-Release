"""路径安全回归：会话/存档点 id 拼进文件系统路径前必须过白名单，防 ../ 穿越。

超算审查（wf_e8bea13b）确认：/api/export、/api/delete、/api/load 等路由把用户
提供的 id 直接喂给 save_manager，未做校验即可读写 saves 目录之外的路径。
session_dir / load_savepoint 现在先校验 id 格式，非法即抛 ValueError。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game import save_manager as sm

TRAVERSALS = ["../evil", "..\\evil", "../../etc", "a/../b", "a\\..\\b", "/abs", "", "..", "./a"]


@pytest.mark.parametrize("bad", TRAVERSALS)
def test_session_dir_rejects_traversal(bad, tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "SAVES_DIR", tmp_path)
    with pytest.raises(ValueError):
        sm.session_dir(bad)


def test_session_dir_accepts_normal_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "SAVES_DIR", tmp_path)
    for ok in ["abc123", "cwsm", "livesub", "03096c824e03", "a-b_c"]:
        assert sm.session_dir(ok).name == ok


@pytest.mark.parametrize("bad", TRAVERSALS)
def test_load_savepoint_rejects_traversal(bad, tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "SAVES_DIR", tmp_path)
    with pytest.raises(ValueError):
        sm.load_savepoint(bad)
