"""建世界流水线：产物校验 / mock DeepSeek 成功与重试 / 友好错误映射。"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from game import world_builder


def good_payload():
    return {
        "name": "青云志",
        "desc": "灵气复苏的仙侠世界",
        "rulebook": (
            "世界观：灵气复苏的修真世界，修士以修为论高低。\n"
            "地图：青云宗、天墉城、荒古禁地、云梦泽、镇妖塔。\n"
            "机制：修炼提升修为、门派贡献、与同门培养好感、秘境争夺机缘。\n"
            "创建选项：身份决定出身资源，天赋影响修炼速度。\n"
            "输出契约：state_delta 必须用 resources/stats/affection 增量，禁止旧键。\n"
        ) * 6,
        "state_template": {
            "character": {"name": "无名", "gender": "?"},
            "level_field": "修为",
            "resources": {"灵石": {"init": 10, "min": 0}},
            "stats": {"修为": {"init": 1, "min": 1, "max": 100, "max_step": 3}},
            "affection_chars": ["林晚"], "factions": ["青云宗"],
            "inventory": [], "start_location": "青云宗",
        },
        "creation_schema": {"steps": [
            {"step": "身份", "fields": [
                {"key": "identity", "label": "你的身份", "type": "select",
                 "options": ["穿越者", "正典角色", "原创角色"], "required": True},
                {"key": "name", "label": "姓名", "type": "text", "required": False},
            ]},
            {"step": "背景", "fields": [
                {"key": "background", "label": "背景故事", "type": "textarea", "required": False},
            ]},
        ]},
    }


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class _Completions:
    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = 0

    def create(self, **kw):
        self.calls += 1
        content = self.contents.pop(0) if len(self.contents) > 1 else self.contents[0]
        if isinstance(content, Exception):
            raise content
        return _Resp(content)


class _FakeOpenAI:
    def __init__(self, completions):
        self.chat = type("Chat", (), {"completions": completions})()


def _patch(monkeypatch, completions):
    monkeypatch.setattr(
        world_builder, "OpenAI",
        lambda *a, **k: _FakeOpenAI(completions),
    )
    return completions


def test_validate_world_spec_ok():
    w = world_builder.validate_world_spec(good_payload(), "u1")
    assert w["kind"] == "custom"
    assert w["owner"] == "u1"
    assert w["summary"] == "generic"
    assert w["state_template"]["stats"]["修为"]["max_step"] == 3
    assert w["state_template"]["resources"]["灵石"]["min"] == 0
    assert w["creation_schema"]["steps"][0]["fields"][0]["type"] == "select"


def test_validate_rejects_short_rulebook():
    bad = good_payload()
    bad["rulebook"] = "太短了"
    with pytest.raises(ValueError):
        world_builder.validate_world_spec(bad, "u1")


def test_validate_rejects_missing_steps():
    bad = good_payload()
    bad["creation_schema"] = {"steps": []}
    with pytest.raises(ValueError):
        world_builder.validate_world_spec(bad, "u1")


def test_validate_coerces_bad_field_type_to_text():
    good = good_payload()
    good["creation_schema"]["steps"][0]["fields"][0]["type"] = "checkbox"
    w = world_builder.validate_world_spec(good, "u1")
    # 基础字段兜底会插入到第一页最前，按 key 定位 identity 字段更稳健
    all_fields = [f for s in w["creation_schema"]["steps"] for f in s["fields"]]
    identity = next(f for f in all_fields if f["key"] == "identity")
    assert identity["type"] == "text"


def test_validate_ensures_base_fields_when_missing():
    good = good_payload()
    # 模拟 AI 漏字段：向导只保留一个字段、character 清空
    good["creation_schema"]["steps"] = [
        {"step": "身份", "fields": [
            {"key": "identity", "label": "身份", "type": "select", "options": ["穿越者"]},
        ]},
    ]
    good["state_template"]["character"] = {}
    w = world_builder.validate_world_spec(good, "u1")

    keys = [f["key"] for s in w["creation_schema"]["steps"] for f in s["fields"]]
    for k in ("name", "gender", "age", "custom_setting"):
        assert k in keys, f"缺少基础字段 {k}"
    # 第一页以 name 开头
    assert w["creation_schema"]["steps"][0]["fields"][0]["key"] == "name"
    # gender 是下拉且选项正确
    gender = next(f for f in w["creation_schema"]["steps"][0]["fields"] if f["key"] == "gender")
    assert gender["type"] == "select" and gender["options"] == ["男", "女", "神秘"]
    # character 同步补齐四键
    ch = w["state_template"]["character"]
    assert ch["name"] == "无名" and ch["gender"] == "?" and ch["age"] == 0 and ch["custom_setting"] == ""


def test_build_world_success(monkeypatch):
    good = json.dumps(good_payload(), ensure_ascii=False)
    comp = _Completions([good])
    _patch(monkeypatch, comp)
    w = world_builder.build_world("样本", "sk-test", "u1")
    assert w["name"] == "青云志"
    assert w["owner"] == "u1"
    assert comp.calls == 1


def test_build_world_retries_once_on_error(monkeypatch):
    good = json.dumps(good_payload(), ensure_ascii=False)
    comp = _Completions([RuntimeError("boom"), good])
    _patch(monkeypatch, comp)
    w = world_builder.build_world("样本", "sk-test", "u1")
    assert w["name"] == "青云志"
    assert comp.calls == 2  # 失败一次后自动重试


def test_build_world_fails_after_two_attempts(monkeypatch):
    comp = _Completions([RuntimeError("bad"), RuntimeError("bad")])
    _patch(monkeypatch, comp)
    with pytest.raises(RuntimeError):
        world_builder.build_world("样本", "sk-test", "u1")
    assert comp.calls == 2


def test_build_world_strips_code_fence(monkeypatch):
    content = "```json\n" + json.dumps(good_payload(), ensure_ascii=False) + "\n```"
    comp = _Completions([content])
    _patch(monkeypatch, comp)
    w = world_builder.build_world("样本", "sk-test", "u1")
    assert w["name"] == "青云志"


def test_friendly_error_401():
    e = type("E", (), {"status_code": 401, "code": "invalid_api_key"})()
    msg = world_builder._friendly_build_error(e)
    assert "无效" in msg and "Key" in msg


def test_friendly_error_429():
    e = type("E", (), {"status_code": 429, "code": "insufficient_quota"})()
    msg = world_builder._friendly_build_error(e)
    assert "额度" in msg or "限流" in msg
