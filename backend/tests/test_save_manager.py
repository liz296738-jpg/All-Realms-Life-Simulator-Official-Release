import sys, tempfile, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.state_schema import default_state
from game import save_manager as sm


def test_roundtrip_state_and_history():
    with tempfile.TemporaryDirectory() as td:
        sm.SAVES_DIR = Path(td)
        sid = "test-1"
        st = default_state({"character": {"name": "A", "innate_soul_power": 5}})
        hist = [json.dumps({"role": "user", "content": "hi"}, ensure_ascii=False)]
        sm.save_state(sid, st, hist)
        st2, h2 = sm.load_state(sid)
        assert st2["character"]["name"] == "A"
        assert h2[0] == hist[0]


def test_savepoint_and_list():
    with tempfile.TemporaryDirectory() as td:
        sm.SAVES_DIR = Path(td)
        sid = "test-2"
        st = default_state({"character": {"name": "B", "innate_soul_power": 7}})
        sm.save_state(sid, st, [])  # 真实流程：新游戏先落盘 state.json
        sp = sm.create_savepoint(sid, st, [])
        assert sp["id"].startswith("test-2-")
        listed = sm.list_sessions()
        assert any(x["session_id"] == sid for x in listed)
        loaded = sm.load_savepoint(sp["id"])
        assert loaded["state"]["character"]["name"] == "B"


def test_turns_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        sm.SAVES_DIR = Path(td)
        sid = "test-turns"
        turns = [{"narrative": "n", "options": [], "notes": [], "event": "", "choice": None}]
        undo = [{"state": {"meta": {"turn": 1}}, "history": [], "options": []}]
        sm.save_turns(sid, turns, undo)
        t, u = sm.load_turns(sid)
        assert t == turns
        assert u == undo


def test_savepoint_with_turns_and_old_compat():
    with tempfile.TemporaryDirectory() as td:
        sm.SAVES_DIR = Path(td)
        st = default_state({"character": {"name": "C"}})
        turns = [{"narrative": "n1", "options": [], "notes": [], "event": "", "choice": None}]
        sp = sm.create_savepoint("sp-new", st, [], turns)
        loaded = sm.load_savepoint(sp["id"])
        assert loaded["turns"] == turns

        # 旧存档（无 turns 字段）向后兼容
        sp2 = sm.create_savepoint("sp-old", st, [])
        loaded2 = sm.load_savepoint(sp2["id"])
        assert "turns" not in loaded2
