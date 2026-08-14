"""世界规格"体检"：遍历 backend/worlds/*.json，在引擎静默跳过坏文件之前主动断言三类隐患。

背景：builtin_worlds() 对加载失败的 JSON 会 catch 后 continue（零报错），坏世界会从
广场"消失"且无提示。本测试在 pytest 时兜底，确保每个世界：
  1) 是合法 JSON 对象；
  2) 创建向导字段与角色字段对齐（否则玩家填的值被 default_state 丢弃）；
  3) 资源/属性初始值不越界（min <= init <= max）。
"""
import json
from pathlib import Path

WORLDS_DIR = Path(__file__).resolve().parent.parent / "worlds"


def _load_specs():
    """返回 [(文件名, 解析后的 dict)]。任一文件解析失败或非对象即在此抛错。"""
    specs = []
    for p in sorted(WORLDS_DIR.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"{p.name}: 顶层必须是 JSON 对象，实际为 {type(data).__name__}"
        specs.append((p.name, data))
    return specs


def _num(field, key):
    """取字段规格里的数值；缺失或非数值返回 None。"""
    v = field.get(key)
    return int(v) if isinstance(v, (int, float)) else None


def test_every_world_is_valid_json_object():
    _load_specs()  # 解析失败或非对象 → 断言失败


def test_creation_schema_keys_align_with_character():
    for name, spec in _load_specs():
        char = (spec.get("state_template") or {}).get("character") or {}
        for step in (spec.get("creation_schema") or {}).get("steps") or []:
            for f in step.get("fields") or []:
                key = f.get("key")
                assert key in char, (
                    f"{name}: 创建向导字段 {key!r} 不在 state_template.character 中，"
                    "玩家填写的值会被 default_state 丢弃"
                )


def test_init_within_bounds():
    for name, spec in _load_specs():
        st = spec.get("state_template") or {}
        for group in ("resources", "stats"):
            for field_name, field in (st.get(group) or {}).items():
                assert isinstance(field, dict), f"{name}: {group}.{field_name} 必须是对象"
                init = _num(field, "init")
                lo = _num(field, "min")
                hi = _num(field, "max")
                if init is not None and lo is not None:
                    assert init >= lo, f"{name}: {group}.{field_name} init={init} 低于 min={lo}"
                if init is not None and hi is not None:
                    assert init <= hi, f"{name}: {group}.{field_name} init={init} 高于 max={hi}"
