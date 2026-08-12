"""世界规格：加载 / 校验 / 落盘。

一个世界 = 一个 JSON 规格（见 docs/superpowers/specs/2026-08-10-multi-world-platform-design.md）：
  {id, name, desc, kind: builtin|custom, owner, rulebook|rulebook_file,
   state_template, creation_schema, created_at}

- builtin 世界规格入仓库（backend/worlds/douluo.json），规则书可为独立文件（rulebook_file）。
- custom 世界落 data/worlds/<id>.json（被 .gitignore 忽略，仅作者可见）。
"""
from __future__ import annotations

import json
import os
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent
BUILTIN_DIR = BASE_DIR / "worlds"
CUSTOM_DIR = BASE_DIR / "data" / "worlds"

_REQUIRED_KEYS = ("id", "name", "desc", "kind", "state_template")


def _resolve_rulebook(spec: dict) -> str:
    """解析规则书：优先内联 rulebook，其次 rulebook_file（相对仓库根）。"""
    if spec.get("rulebook"):
        return str(spec["rulebook"])
    rf = spec.get("rulebook_file")
    if rf:
        p = Path(rf)
        if not p.is_absolute():
            p = REPO_ROOT / rf
        if p.exists():
            return p.read_text(encoding="utf-8")
    raise ValueError(f"世界 {spec.get('id', '?')} 缺少规则书（rulebook 或 rulebook_file）")


def _validate_spec(spec: dict) -> None:
    """结构校验：缺键 / 类型错误直接抛 ValueError。"""
    if not isinstance(spec, dict):
        raise ValueError("世界规格必须是 JSON 对象")
    for k in _REQUIRED_KEYS:
        if k not in spec:
            raise ValueError(f"世界规格缺少字段: {k}")
    if spec["kind"] not in ("builtin", "custom"):
        raise ValueError("kind 只能是 builtin 或 custom")
    st = spec["state_template"]
    if not isinstance(st, dict) or "character" not in st:
        raise ValueError("state_template 必须包含 character 字段")
    for key in ("resources", "stats", "affection_chars", "factions", "inventory"):
        if key in st and not isinstance(st[key], dict if key in ("resources", "stats") else list):
            raise ValueError(f"state_template.{key} 类型不合法")
    if "level_field" not in st and spec.get("summary") != "generic":
        raise ValueError("state_template 缺少 level_field")


def _load_file(path: Path) -> dict:
    spec = json.loads(path.read_text(encoding="utf-8"))
    _validate_spec(spec)
    spec["rulebook"] = _resolve_rulebook(spec)
    spec.pop("rulebook_file", None)
    return spec


def builtin_worlds() -> list[dict]:
    out = []
    if BUILTIN_DIR.exists():
        for p in sorted(BUILTIN_DIR.glob("*.json")):
            try:
                out.append(_load_file(p))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
    return out


def custom_worlds() -> list[dict]:
    out = []
    if CUSTOM_DIR.exists():
        for p in sorted(CUSTOM_DIR.glob("*.json")):
            try:
                out.append(_load_file(p))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
    return out


# 内存缓存：id -> 完整规格（含规则书）。builtin 变化少，custom 由写接口主动失效。
_cache: dict[str, dict] = {}
_CACHE_VALID = False


def _refresh_cache() -> None:
    global _CACHE_VALID
    if _CACHE_VALID:
        return
    _cache.clear()
    for w in builtin_worlds() + custom_worlds():
        _cache[w["id"]] = w
    _CACHE_VALID = True


def _invalidate() -> None:
    global _CACHE_VALID
    _CACHE_VALID = False


def get_world(world_id: str) -> dict | None:
    _refresh_cache()
    return deepcopy(_cache.get(world_id))


def get_world_template(world_id: str) -> dict | None:
    """只取 state_template（轻量，不深拷贝规则书大文本），供引擎高频调用。"""
    _refresh_cache()
    w = _cache.get(world_id)
    return deepcopy(w["state_template"]) if w else None


def save_custom_world(spec: dict) -> dict:
    """原子落盘自定义世界。spec 须已带 id/owner/created_at 与 rulebook 内联。"""
    _validate_spec(spec)
    if spec["kind"] != "custom":
        raise ValueError("只能保存 custom 世界")
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    data = deepcopy(spec)
    tmp = CUSTOM_DIR / f"{spec['id']}.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CUSTOM_DIR / f"{spec['id']}.json")
    _invalidate()
    return data


def delete_custom_world(world_id: str) -> bool:
    p = CUSTOM_DIR / f"{world_id}.json"
    if p.exists():
        p.unlink()
        _invalidate()
        return True
    return False


def new_world_id() -> str:
    return uuid.uuid4().hex[:12]


def world_summary(world: dict) -> dict:
    """给前端的精简摘要（去掉规则书全文，体积可控）。"""
    st = world.get("state_template", {}) or {}
    return {
        "id": world["id"],
        "name": world["name"],
        "desc": world.get("desc", ""),
        "kind": world["kind"],
        "owner": world.get("owner"),
        "created_at": world.get("created_at"),
        "creation_schema": world.get("creation_schema", {}),
        "summary": world.get("summary", "generic"),
        "level_field": st.get("level_field", ""),
    }


def world_name(world: dict) -> str:
    return world.get("name", "未知世界")
