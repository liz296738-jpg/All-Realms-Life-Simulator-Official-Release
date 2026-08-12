# 《斗罗大陆人生模拟器》网页版 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将《斗罗大陆人生模拟器》文字 RPG 实现为可运行的网页游戏：角色创建向导 + 开放世界探索 + AI 叙述/选项 + 实时状态追踪 + 存档读档。

**Architecture:** 后端（FastAPI）是状态权威账本；DeepSeek 担任世界引擎——每轮先流式输出叙述，再由一次结构化结算调用产出「状态变动单 + 选项」；后端校验钳制变动单、应用被动机制（好感衰减/自动存档）并推回权威状态；前端（Vue3 + Tailwind）极简沉浸式渲染剧情流，状态栏折叠。

**Tech Stack:** Python 3 + FastAPI + openai SDK（DeepSeek `deepseek-chat`）；Vue 3 + Vite + Tailwind CSS + markdown-it；JSON 文件存储。

## Global Constraints

- 所有游戏状态数值必须由后端权威追踪与校验，AI 不得直接改账本
- 状态变动单使用固定英文 delta schema（见 Task 1）
- 好感度钳制 -100~100；金币/银币/铜币不得为负；魂力单轮增量 -2~+2；魂环只能按序追加、年限不超上限（423/764/1760/5000/12000/20000/50000/80000/100000）
- 完整的游戏规则书（用户提供）逐字写入 `backend/prompts/system_prompt.txt`，作为系统提示底座
- AI 叙述必须遵守规则书文风硬性规定（禁套路句式、选项有人味、每轮 3-4 个选项含自定义路线）
- DeepSeek Key 从 `C:/Users/ASUA/backend/.env` 复制到本项目 `backend/.env`
- 所有文件用 UTF-8 编码；前后端分离，CORS 全开（本地开发）
- 独立 git 仓库（已初始化于 douluo-simulator/），每任务一提交

---

## 文件结构

```
douluo-simulator/
├── docs/superpowers/specs/2026-08-10-...design.md   （已完成）
├── docs/superpowers/plans/2026-08-10-....md          （本计划）
├── backend/
│   ├── requirements.txt
│   ├── .env.example
│   ├── .env                （复制 DEEPSEEK_API_KEY）
│   ├── prompts/system_prompt.txt   （规则书 + 输出契约）
│   ├── game/
│   │   ├── __init__.py
│   │   ├── state_schema.py     # 状态模型 / 初始化 / 变动单校验钳制
│   │   ├── game_engine.py      # apply_delta / 好感衰减 / 季节推断
│   │   ├── prompt_builder.py   # 系统提示 + 状态摘要 + 历史组装
│   │   └── save_manager.py     # 状态持久化 / 存档点 / 列表
│   ├── main.py                 # FastAPI 路由 + SSE + DeepSeek 客户端
│   └── tests/
│       ├── test_state_schema.py
│       ├── test_game_engine.py
│       └── test_save_manager.py
└── frontend/
    ├── package.json / vite.config.js / index.html / tailwind.config.js / postcss.config.js
    └── src/
        ├── main.js / style.css
        ├── api.js              # HTTP + SSE 客户端
        ├── store.js            # 响应式全局 store（Vue reactive）
        ├── App.vue
        ├── views/HomeView.vue  # 入口：新游戏/继续/读档
        ├── views/GameView.vue  # 主游戏界面
        └── components/
            ├── CreationWizard.vue  # 5 步创建向导
            ├── CharacterCard.vue   # 档案卡确认
            ├── NarrativeStream.vue # 剧情流 + 打字机
            ├── OptionsBar.vue      # 选项胶囊 + 自由输入
            ├── StatusPanel.vue     # 折叠状态栏
            └── SavePanel.vue       # 存档面板
```

---

### Task 1: 后端脚手架 + 状态模型 + 校验钳制

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/.env.example`
- Create: `backend/game/__init__.py`
- Create: `backend/game/state_schema.py`
- Test: `backend/tests/test_state_schema.py`

**Interfaces:**
- Produces: `default_state(archive: dict) -> dict`；`validate_delta(delta: dict, state: dict) -> dict`；常量 `RING_YEAR_CAPS`、`DEFAULT_AFFECTION_CHARS`、`TALENT_TIERS`

- [ ] **Step 1: 建目录与 requirements**

```bash
mkdir -p backend/game backend/prompts backend/tests frontend/src/views frontend/src/components
```

`backend/requirements.txt`:
```
fastapi
uvicorn[standard]
openai>=1.0
python-dotenv
pydantic
pytest
httpx
```

- [ ] **Step 2: 写失败测试** `backend/tests/test_state_schema.py`

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.state_schema import default_state, validate_delta

def make_archive(**kw):
    base = {"character": {"name": "测试", "gender": "男", "age": 12,
            "wuhun": "蓝银草", "innate_soul_power": 5, "talent_tier": "普通魂师档",
            "origin": "平民", "initial_gold": 8}}
    base.update(kw)
    return base

def test_default_state_starts_at_innate():
    s = default_state(make_archive())
    assert s["character"]["soul_level"] == 5
    assert s["soul_rings"] == []
    assert s["resources"]["gold"] == 8
    assert s["affection"]["唐三"] == 0

def test_validate_clamps_gold_non_negative():
    s = default_state(make_archive())
    d = validate_delta({"gold": -999}, s)
    # 只能花到 0
    assert d["gold"] == -8

def test_validate_clamps_affection():
    s = default_state(make_archive())
    s["affection"]["唐三"] = 99
    d = validate_delta({"affection": {"唐三": 5}}, s)
    assert d["affection"]["唐三"] == 100

def test_validate_caps_soul_level_delta():
    s = default_state(make_archive())
    d = validate_delta({"soul_level": 30}, s)  # 目标30，现5
    assert d["soul_level"] <= 7  # 单轮最多+2

def test_validate_ring_year_cap():
    s = default_state(make_archive())
    d = validate_delta({"soul_ring_add": {"years": 9000, "beast": "X", "skill": "S"}}, s)
    assert d["soul_ring_add"]["slot"] == 1
    assert d["soul_ring_add"]["years"] == 423  # 第一环上限

def test_validate_rejects_skipping_ring():
    s = default_state(make_archive())
    s["soul_rings"] = [{"slot": 1, "years": 400, "beast": "a", "skill": "b", "attribute": "c"}]
    d = validate_delta({"soul_ring_add": {"years": 400, "beast": "X", "skill": "S"}}, s)
    assert d["soul_ring_add"]["slot"] == 2
```

- [ ] **Step 3: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_state_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: game.state_schema`

- [ ] **Step 4: 实现 state_schema.py**

```python
"""权威状态模型 + 变动单(delta)校验钳制。后端是唯一账本。"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

# 关键 NPC 好感度预置键
DEFAULT_AFFECTION_CHARS = [
    "唐三", "小舞", "戴沐白", "朱竹清", "奥斯卡", "宁荣荣",
    "弗兰德", "玉小刚", "比比东", "千仞雪", "胡列娜",
]

# 魂环年限上限（第一环→第九环）
RING_YEAR_CAPS = [423, 764, 1760, 5000, 12000, 20000, 50000, 80000, 100000]

TALENT_TIERS = {"凡人档": (1, 3), "普通魂师档": (4, 6), "天才档": (7, 9), "怪物档": (9, 10)}
ORIGIN_GOLD = {"平民": (5, 10), "小家族": (100, 300), "宗门子弟": (500, 800), "孤儿": (2, 5)}


def default_state(archive: dict[str, Any]) -> dict[str, Any]:
    """根据创建档案卡生成初始权威状态。"""
    ch = archive.get("character", {})
    innate = int(ch.get("innate_soul_power", 5))
    origin = ch.get("origin", "平民")
    lo, hi = ORIGIN_GOLD.get(origin, (5, 10))
    gold = int(ch.get("initial_gold", hi))
    return {
        "character": {
            "name": ch.get("name", "无名"), "gender": ch.get("gender", "?"),
            "age": int(ch.get("age", 12)), "wuhun": ch.get("wuhun", "蓝银草"),
            "wuhun_type": ch.get("wuhun_type", "器武魂"),
            "innate_soul_power": innate, "soul_level": innate,
            "talent_tier": ch.get("talent_tier", "普通魂师档"),
            "origin": origin, "background": ch.get("background", ""),
            "family": ch.get("family", ""), "secret": ch.get("secret", ""),
            "traits": ch.get("traits", ""), "personality": ch.get("personality", []),
            "desire_to_grow": int(ch.get("desire_to_grow", 5)),
            "development_direction": ch.get("development_direction", "强攻系"),
        },
        "soul_rings": [],
        "location": {"place": archive.get("start_location", "诺丁城"), "season": "春", "date": "第1年1月"},
        "resources": {"gold": gold, "silver": 0, "copper": 0},
        "affection": {c: 0 for c in DEFAULT_AFFECTION_CHARS},
        "affection_last_seen": {c: 0 for c in DEFAULT_AFFECTION_CHARS},
        "faction": {"武魂殿": 0, "七宝琉璃宗": 0, "史莱克学院": 0, "天斗皇室": 0, "星罗皇室": 0, "中立自由人": 0},
        "inventory": list(ch.get("special_items", [])),
        "notes": [],
        "meta": {
            "turn": 0, "month": 0, "rewind_left": 3, "achievements": [],
            "direction": archive.get("direction", "自由/综合向"),
            "timeline_binding": archive.get("timeline_binding", "半绑定"),
            "session_id": archive.get("session_id", ""),
            "created_at": archive.get("created_at", ""),
        },
    }


def _clamp_int(value, floor=None, ceil=None) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = 0
    if floor is not None and v < floor:
        v = floor
    if ceil is not None and v > ceil:
        v = ceil
    return v


def validate_delta(delta: dict, state: dict) -> dict:
    """校验并钳制变动单，返回清洗后的 delta（不直接改 state）。"""
    out = deepcopy(delta)
    res = state["resources"]
    out["gold"] = _clamp_int(delta.get("gold"), floor=-res["gold"])
    out["silver"] = _clamp_int(delta.get("silver"), floor=-res["silver"])
    out["copper"] = _clamp_int(delta.get("copper"), floor=-res["copper"])

    cur = state["character"]["soul_level"]
    if "soul_level" in delta and delta["soul_level"] is not None:
        target = _clamp_int(delta["soul_level"])
        d = max(-2, min(2, target - cur))
        out["soul_level"] = max(state["character"]["innate_soul_power"], cur + d)
    else:
        out.pop("soul_level", None)

    aff = state["affection"]
    out["affection"] = {}
    for name, inc in (delta.get("affection") or {}).items():
        if name in aff:
            out["affection"][name] = max(-100, min(100, aff[name] + _clamp_int(inc)))

    rings = state["soul_rings"]
    if delta.get("soul_ring_add"):
        slot = len(rings) + 1
        if slot <= 9:
            add = dict(delta["soul_ring_add"])
            add["slot"] = slot
            add["years"] = _clamp_int(add.get("years"), floor=0, ceil=RING_YEAR_CAPS[slot - 1])
            add["beast"] = str(add.get("beast", "魂兽"))
            add["skill"] = str(add.get("skill", "未知魂技"))
            add["attribute"] = str(add.get("attribute", "无"))
            out["soul_ring_add"] = add
        else:
            out.pop("soul_ring_add", None)
    else:
        out.pop("soul_ring_add", None)

    out["inventory_add"] = [str(x) for x in delta.get("inventory_add", []) if x]
    out["inventory_remove"] = [str(x) for x in delta.get("inventory_remove", []) if x]
    out["notes_add"] = [str(x) for x in delta.get("notes_add", []) if x]
    out["location"] = str(delta.get("location", state["location"]["place"]))
    out["date"] = str(delta.get("date", state["location"]["date"]))
    out["month_delta"] = _clamp_int(delta.get("month_delta"), floor=0, ceil=24)
    return out
```

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_state_schema.py -v`
Expected: PASS (7 passed)

- [ ] **Step 6: 提交**

```bash
git add backend && git commit -m "feat(backend): 状态模型与变动单校验钳制"
```

---

### Task 2: 状态应用引擎（apply_delta + 好感衰减 + 季节推断）

**Files:**
- Create: `backend/game/game_engine.py`
- Test: `backend/tests/test_game_engine.py`

**Interfaces:**
- Consumes: `default_state`, `validate_delta` from `game.state_schema`
- Produces: `apply_delta(state: dict, delta: dict) -> dict`（就地修改并返回 state）

- [ ] **Step 1: 写失败测试**

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.state_schema import default_state
from game.game_engine import apply_delta

def make():
    return default_state({"character": {"name": "A", "innate_soul_power": 5,
        "talent_tier": "普通魂师档", "origin": "平民", "initial_gold": 10}})

def test_applies_money_and_affection():
    s = make()
    apply_delta(s, {"gold": -3, "silver": 2, "affection": {"唐三": 5}})
    assert s["resources"]["gold"] == 7
    assert s["resources"]["silver"] == 2
    assert s["affection"]["唐三"] == 5

def test_applies_soul_level_and_ring():
    s = make()
    apply_delta(s, {"soul_level": 7, "soul_ring_add": {"years": 400, "beast": "曼陀罗蛇", "skill": "缠绕"}})
    assert s["character"]["soul_level"] == 7
    assert s["soul_rings"][0]["slot"] == 1

def test_affection_decay_when_month_passes():
    s = make()
    s["affection"]["唐三"] = 30
    s["affection_last_seen"]["唐三"] = 0
    apply_delta(s, {"month_delta": 2, "affection": {"小舞": 3}})
    # 唐三未见面衰减，小舞刚见面不衰减
    assert s["affection"]["唐三"] == 29
    assert s["affection"]["小舞"] == 3

def test_season_inferred_from_date():
    s = make()
    apply_delta(s, {"date": "第2年7月"})
    assert s["location"]["season"] == "夏"
```

- [ ] **Step 2: 运行确认失败** → `ModuleNotFoundError: game.game_engine`

- [ ] **Step 3: 实现 game_engine.py**

```python
"""状态应用引擎：把清洗后的 delta 落账，并驱动被动机制。"""
from __future__ import annotations

import re
from typing import Any

from .state_schema import validate_delta


def _guess_season(date: str) -> str:
    m = re.search(r"(\d{1,2})月", date or "")
    if m:
        mo = int(m.group(1))
        if mo in (12, 1, 2):
            return "冬"
        if 3 <= mo <= 5:
            return "春"
        if 6 <= mo <= 8:
            return "夏"
        return "秋"
    return "春"


def apply_delta(state: dict, raw_delta: dict) -> dict:
    """校验 → 落账 → 好感衰减 → 季节 → 回合自增。就地修改 state。"""
    delta = validate_delta(raw_delta, state)

    res = state["resources"]
    res["gold"] += delta.get("gold", 0)
    res["silver"] += delta.get("silver", 0)
    res["copper"] += delta.get("copper", 0)

    if "soul_level" in delta:
        state["character"]["soul_level"] = delta["soul_level"]

    for name, val in delta.get("affection", {}).items():
        state["affection"][name] = val
        state["affection_last_seen"][name] = state["meta"]["month"]

    if delta.get("soul_ring_add"):
        state["soul_rings"].append(delta["soul_ring_add"])

    for item in delta.get("inventory_add", []):
        if item not in state["inventory"]:
            state["inventory"].append(item)
    for item in delta.get("inventory_remove", []):
        if item in state["inventory"]:
            state["inventory"].remove(item)
    for note in delta.get("notes_add", []):
        if note not in state["notes"]:
            state["notes"].append(note)

    state["location"]["place"] = delta.get("location", state["location"]["place"])
    state["location"]["date"] = delta.get("date", state["location"]["date"])
    state["location"]["season"] = _guess_season(state["location"]["date"])

    md = delta.get("month_delta", 0)
    if md > 0:
        state["meta"]["month"] += md
        for name in state["affection"]:
            last = state["affection_last_seen"].get(name, 0)
            gap = state["meta"]["month"] - last
            if gap >= 1:
                state["affection"][name] = max(-100, state["affection"][name] - min(gap, 3))
                state["affection_last_seen"][name] = state["meta"]["month"]

    state["meta"]["turn"] += 1
    return state
```

- [ ] **Step 4: 运行确认通过** → PASS (4 passed)

- [ ] **Step 5: 提交** → `git add backend && git commit -m "feat(backend): 状态应用引擎与好感衰减"`

---

### Task 3: 存档管理

**Files:**
- Create: `backend/game/save_manager.py`
- Test: `backend/tests/test_save_manager.py`

**Interfaces:**
- Produces: `session_dir(session_id) -> Path`；`save_state(session_id, state, history)`；`load_state(session_id) -> (state, history)`；`create_savepoint(session_id, state, history) -> dict`；`list_sessions() -> list[dict]`；`load_savepoint(savepoint_id) -> dict`

- [ ] **Step 1: 写失败测试**

```python
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
        sp = sm.create_savepoint(sid, st, [])
        assert sp["id"].startswith("test-2-")
        listed = sm.list_sessions()
        assert any(x["session_id"] == sid for x in listed)
        loaded = sm.load_savepoint(sp["id"])
        assert loaded["state"]["character"]["name"] == "B"
```

- [ ] **Step 2: 运行确认失败** → `ModuleNotFoundError`

- [ ] **Step 3: 实现 save_manager.py**

```python
"""会话持久化与存档点。状态 + 对白历史 落盘为 JSON。"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
SAVES_DIR = BASE_DIR / "data" / "saves"


def session_dir(session_id: str) -> Path:
    d = SAVES_DIR / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_state(session_id: str, state: dict, history: list[str]) -> Path:
    d = session_dir(session_id)
    (d / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "history.jsonl").write_text(
        "\n".join(history) + ("\n" if history else ""), encoding="utf-8")
    return d


def load_state(session_id: str) -> tuple[dict, list[str]]:
    d = session_dir(session_id)
    state = json.loads((d / "state.json").read_text(encoding="utf-8"))
    raw = (d / "history.jsonl").read_text(encoding="utf-8") if (d / "history.jsonl").exists() else ""
    history = [l.strip() for l in raw.splitlines() if l.strip()]
    return state, history


def create_savepoint(session_id: str, state: dict, history: list[str]) -> dict:
    d = session_dir(session_id) / "savepoints"
    d.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    sp_id = f"{session_id}-{ts}"
    (d / f"{sp_id}.json").write_text(
        json.dumps({"state": state, "history": history}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return {
        "id": sp_id, "time": ts, "turn": state["meta"]["turn"],
        "place": state["location"]["place"], "name": state["character"]["name"],
        "soul_level": state["character"]["soul_level"],
    }


def list_sessions() -> list[dict]:
    out = []
    if SAVES_DIR.exists():
        for d in SAVES_DIR.iterdir():
            p = d / "state.json"
            if d.is_dir() and p.exists():
                st = json.loads(p.read_text(encoding="utf-8"))
                out.append({
                    "session_id": d.name,
                    "name": st["character"]["name"],
                    "soul_level": st["character"]["soul_level"],
                    "turn": st["meta"]["turn"],
                    "place": st["location"]["place"],
                    "date": st["location"]["date"],
                })
    return sorted(out, key=lambda x: x["session_id"], reverse=True)


def load_savepoint(savepoint_id: str) -> dict:
    if SAVES_DIR.exists():
        for d in SAVES_DIR.iterdir():
            p = d / "savepoints" / f"{savepoint_id}.json"
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"存档不存在: {savepoint_id}")
```

- [ ] **Step 4: 运行确认通过** → PASS (2 passed)

- [ ] **Step 5: 提交** → `git add backend && git commit -m "feat(backend): 存档管理"`

---

### Task 4: 游戏规则书系统提示（system_prompt.txt）

**Files:**
- Create: `backend/prompts/system_prompt.txt`
- Create: `backend/.env.example`

- [ ] **Step 1: 写入规则书**

将用户提供的《斗罗大陆人生模拟器》规则全文（核心原则 → 世界地图 → 开局身份 → 游玩方向 → 角色创建 → 核心机制 → 世界演化 → 辅助功能 → 文风约束 → 世界观扩展 → 天赋锚定 → 补充设定 → 输出格式 → 约束条件）**逐字**转录进 `backend/prompts/system_prompt.txt`。

在末尾追加「输出契约」节：

```text
═══════════════════════════════════════
【对 AI 引擎的输出契约（必读）】
你将在两阶段工作：
阶段一「叙述」：按上面规则书写一段 150-250 字叙述（含环境与感官细节、有人味），并在结尾以「【选项】」列出 3-4 个选项：
  - 至少 1 条顺当前剧情
  - 至少 1 条偏离/反转
  - 至少 1 条自定义路线（写成"你有别的想法，你自己说"）
  选项文字要带情绪/代价暗示（如"上前搭话——可能耽误正事"），不要机械的"A.xx B.xx"。
  关键数字变动（好感度/魂力/金币）在叙述中用 **加粗** 标出，如 **唐三好感度+3**。
  时间地点用【诺丁城·初级学院·三月·午后】格式写在叙述开头。
阶段二「结算」：结算引擎会单独调用你，你只输出一个 JSON 对象，字段：
{
  "options": [{"label":"A","text":"选项文字"}, ...3-4项],
  "state_delta": {
    "gold": 0, "silver": 0, "copper": 0,
    "soul_level": null,
    "affection": {"唐三": 3},
    "location": "索托城·猫鹰酒店",
    "date": "第3年6月",
    "month_delta": 0,
    "inventory_add": [], "inventory_remove": [],
    "notes_add": []
  },
  "notes": [], 
  "event": ""
}
规则：
- state_delta 键名严格使用上述英文名，不得变体。
- 未变化的字段写 null 或 0 或空数组，不得省略整个对象。
- affection 键是角色中文名（唐三/小舞/比比东/千仞雪等），值为好感增量（正负均可）。
- soul_level 为目标绝对等级（如 22）。若本轮无提升写 null。
- gold/silver/copper 是增量（可负）。month_delta 是游戏内经过的月数（0 表示同日）。
- 魂环获取（猎杀魂兽成功）时，state_delta 追加 "soul_ring_add": {"years":年限,"beast":"魂兽名","skill":"魂技名","attribute":"属性"}。
- 严禁跳过规则书中的设定：魂环年限上限、天赋锚定、文风禁令一律遵守。
- 只输出 JSON，不要任何解释文字。
═══════════════════════════════════════
```

- [ ] **Step 2: `.env.example`**

```
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

- [ ] **Step 3: 复制 Key 并提交**

```bash
cp C:/Users/ASUA/backend/.env backend/.env
git add backend && git commit -m "feat(backend): 游戏规则书系统提示"
```

---

### Task 5: 提示词组装器

**Files:**
- Create: `backend/game/prompt_builder.py`

**Interfaces:**
- Consumes: `state`（权威状态）、`history`（list[str]，JSONL 行）
- Produces: `build_narrative_messages(state, history, player_action) -> list[dict]`；`build_settle_messages(state, history, narrative) -> list[dict]`；`build_opening_messages(state, archive) -> list[dict]`

- [ ] **Step 1: 实现 prompt_builder.py**

```python
"""提示词组装：规则书 + 当前状态 + 历史 + 玩家行动。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.txt"
_SYSTEM = RULES_PATH.read_text(encoding="utf-8")

SETTLE_INSTRUCTION = (
    "你是《斗罗大陆人生模拟器》的结算引擎。只输出一个 JSON 对象，不得输出任何其他文字。"
    "输出契约见系统规则。请严格使用 state_delta 的英文键名。"
)


def system_prompt() -> str:
    return _SYSTEM


def state_summary(state: dict) -> str:
    c = state["character"]
    rings = "；".join(
        f"第{r['slot']}环·{r['years']}年·{r['beast']}" for r in state["soul_rings"]
    ) or "无魂环"
    aff = "，".join(f"{k}{v}" for k, v in sorted(
        state["affection"].items(), key=lambda x: -x[1]) if v)
    res = state["resources"]
    return (
        f"姓名：{c['name']} | 性别：{c['gender']} | 年龄：{c['age']} | 魂力：{c['soul_level']}级\n"
        f"武魂：{c['wuhun']}（{c['wuhun_type']}）| 先天魂力：{c['innate_soul_power']}\n"
        f"天赋档：{c['talent_tier']} | 出身：{c['origin']} | 秘密：{c['secret'] or '无'}\n"
        f"所在地：{state['location']['place']} | 时间：{state['location']['date']}（{state['location']['season']}）\n"
        f"魂环配置：{rings}\n"
        f"财富：{res['gold']}金 {res['silver']}银 {res['copper']}铜\n"
        f"势力声望：{state['faction']}\n"
        f"好感度：{aff or '无'}\n"
        f"道具：{state['inventory']}\n"
        f"笔记：{state['notes']}\n"
        f"游玩方向：{state['meta']['direction']} | 时间线绑定：{state['meta']['timeline_binding']}"
    )


def _history_messages(history: list[str], limit: int = 60) -> list[dict]:
    msgs = []
    for line in history[-limit:]:
        try:
            entry = json.loads(line)
            if entry.get("role") in ("user", "assistant"):
                msgs.append({"role": entry["role"], "content": entry["content"]})
        except json.JSONDecodeError:
            continue
    return msgs


def build_narrative_messages(state: dict, history: list[str], player_action: str) -> list[dict]:
    msgs = [{"role": "system", "content": _SYSTEM}]
    msgs.append({"role": "system", "content": "【当前状态】\n" + state_summary(state)})
    msgs.extend(_history_messages(history))
    msgs.append({"role": "user", "content": f"【你的行动】\n{player_action}\n\n（请按叙述规则续写世界，结尾给出选项）"})
    return msgs


def build_opening_messages(state: dict, archive: dict) -> list[dict]:
    msgs = [{"role": "system", "content": _SYSTEM}]
    msgs.append({"role": "system", "content": "【新角色状态】\n" + state_summary(state)})
    msgs.append({"role": "user", "content":
        f"新玩家已创建角色，档案卡：{json.dumps(archive, ensure_ascii=False)}。\n"
        "请写出这场斗罗大陆之行的开场白：交代当前地点、季节、出场人物或氛围，"
        "让玩家感受到自己是谁、身在何处，结尾给出 3-4 个行动选项。"
        "若玩家选择的是原创/穿越/重生身份，请在叙述中自然体现。\n"
        "请以【地点·场景·季节·时段】开头。"})
    return msgs


def build_settle_messages(state: dict, history: list[str], narrative: str) -> list[dict]:
    msgs = [{"role": "system", "content": _SYSTEM}]
    msgs.append({"role": "system", "content": "【当前状态】\n" + state_summary(state)})
    msgs.extend(_history_messages(history))
    msgs.append({"role": "user", "content":
        f"刚才的叙述如下：\n{narrative}\n\n"
        "请作为结算引擎输出本轮 JSON 结算（选项 + state_delta + notes + event）。"
        "state_delta 必须与叙述一致，例如叙述中花了钱、提升了等级、改了地点、加了好感，都要如实反映。"})
    return msgs
```

- [ ] **Step 2: 自测**（无网络调用，仅确认可导入、可组装）

Run: `cd backend && python -c "from game.prompt_builder import build_narrative_messages; print(len(build_narrative_messages({}, [], 'test')))"`
Expected: 无报错（len≥2）

- [ ] **Step 3: 提交** → `git add backend && git commit -m "feat(backend): 提示词组装器"`

---

### Task 6: FastAPI 路由 + DeepSeek 客户端（SSE）

**Files:**
- Create: `backend/main.py`

**Interfaces:**
- Consumes: `default_state`, `game_engine.apply_delta`, `save_manager`, `prompt_builder`
- Produces: REST 路由 `POST /api/new-game`、`POST /api/act`（均 SSE）、`GET /api/saves`、`POST /api/save`、`POST /api/load`、`POST /api/delete`、`GET /api/health`

- [ ] **Step 1: 实现 main.py**

```python
"""《斗罗大陆人生模拟器》后端 — FastAPI 入口。"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel

from game import save_manager as sm
from game.game_engine import apply_delta
from game.prompt_builder import (
    build_narrative_messages, build_opening_messages, build_settle_messages,
)
from game.state_schema import default_state

load_dotenv()

app = FastAPI(title="斗罗大陆人生模拟器 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

_key = os.getenv("DEEPSEEK_API_KEY")
if not _key:
    raise RuntimeError("未设置 DEEPSEEK_API_KEY，请在 backend/.env 配置")
_client = OpenAI(api_key=_key, base_url="https://api.deepseek.com")
MODEL = "deepseek-chat"

# 会话内存缓存：session_id -> (state, history, 当前回合options)
_SESSIONS: dict[str, dict] = {}


class NewGameRequest(BaseModel):
    archive: dict
    session_id: str | None = None


class ActRequest(BaseModel):
    session_id: str
    action: str


class SessionRequest(BaseModel):
    session_id: str


class LoadRequest(BaseModel):
    savepoint_id: str


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _text_chunks(text: str, size: int = 120) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


def _call_narrative(messages: list[dict]) -> str:
    """流式叙述：从 DeepSeek 取完整叙述文本（内部收集）。"""
    resp = _client.chat.completions.create(
        model=MODEL, messages=messages, temperature=0.85, stream=True,
    )
    parts = []
    for chunk in resp:
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            parts.append(chunk.choices[0].delta.content)
    return "".join(parts)


def _call_settle(messages: list[dict]) -> dict:
    """结算调用：要求 JSON 输出，失败重试一次。"""
    for attempt in range(2):
        try:
            resp = _client.chat.completions.create(
                model=MODEL, messages=messages, temperature=0.3,
                response_format={"type": "json_object"},
            )
            text = resp.choices[0].message.content or "{}"
            return json.loads(text)
        except Exception:
            if attempt == 0:
                continue
            return {}
    return {}


def _run_turn(session_id: str, player_action: str, opening: bool = False):
    """生成叙述 + 结算，应用状态，返回 SSE 生成器。"""
    state, history = _SESSIONS[session_id]["state"], _SESSIONS[session_id]["history"]

    if opening:
        msgs = build_opening_messages(state, _SESSIONS[session_id]["archive"])
    else:
        history.append(json.dumps({"role": "user", "content": player_action}, ensure_ascii=False))
        msgs = build_narrative_messages(state, history, player_action)

    narrative = _call_narrative(msgs)
    settle_msgs = build_settle_messages(state, history, narrative)
    settle = _call_settle(settle_msgs)

    options = settle.get("options") or [{"label": "A", "text": "继续前行"}]
    apply_delta(state, settle.get("state_delta") or {})

    history.append(json.dumps({"role": "assistant", "content": narrative}, ensure_ascii=False))
    _SESSIONS[session_id]["last_options"] = options
    _SESSIONS[session_id]["history"] = history
    _SESSIONS[session_id]["state"] = state

    # 每 10 回合自动存档
    if state["meta"]["turn"] % 10 == 0:
        sm.create_savepoint(session_id, state, history)

    def gen():
        for chunk in _text_chunks(narrative):
            yield _sse("text", {"content": chunk})
        yield _sse("delta", {
            "state": state,
            "options": options,
            "notes": settle.get("notes", []),
            "event": settle.get("event", ""),
        })
        yield "event: done\ndata: {}\n\n"

    return gen(), state


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/saves")
def list_saves():
    return {"saves": sm.list_sessions()}


@app.post("/api/new-game")
def new_game(req: NewGameRequest):
    session_id = req.session_id or uuid.uuid4().hex[:12]
    archive = req.archive
    archive["session_id"] = session_id
    archive["created_at"] = datetime.now().isoformat()
    state = default_state(archive)
    sm.save_state(session_id, state, [])
    _SESSIONS[session_id] = {"state": state, "history": [], "archive": archive, "last_options": []}
    gen, _ = _run_turn(session_id, "", opening=True)
    return StreamingResponse(gen, media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/act")
def act(req: ActRequest):
    if req.session_id not in _SESSIONS:
        # 冷启动：从磁盘恢复
        try:
            state, history = sm.load_state(req.session_id)
            _SESSIONS[req.session_id] = {"state": state, "history": history, "archive": {}, "last_options": []}
        except Exception:
            raise HTTPException(404, "会话不存在，请检查存档列表")
    gen, _ = _run_turn(req.session_id, req.action)
    return StreamingResponse(gen, media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/save")
def save(req: SessionRequest):
    if req.session_id not in _SESSIONS:
        raise HTTPException(404, "会话不存在")
    state, history = _SESSIONS[req.session_id]["state"], _SESSIONS[req.session_id]["history"]
    sp = sm.create_savepoint(req.session_id, state, history)
    sm.save_state(req.session_id, state, history)
    return {"savepoint": sp}


@app.post("/api/load")
def load(req: LoadRequest):
    data = sm.load_savepoint(req.savepoint_id)
    sid = req.savepoint_id.split("-")[0]
    _SESSIONS[sid] = {"state": data["state"], "history": data["history"], "archive": {}, "last_options": []}
    return {"session_id": sid, "state": data["state"]}


@app.post("/api/delete")
def delete(req: SessionRequest):
    import shutil
    d = sm.session_dir(req.session_id)
    if d.exists():
        shutil.rmtree(d)
    _SESSIONS.pop(req.session_id, None)
    return {"ok": True}
```

- [ ] **Step 2: 启动冒烟测试**（不调用 DeepSeek，仅验证 import 与路由加载）

Run: `cd backend && python -c "from main import app; print(len(app.routes))"`
Expected: 打印路由数量，无报错

- [ ] **Step 3: 提交** → `git add backend && git commit -m "feat(backend): FastAPI 路由与 DeepSeek SSE 集成"`

---

### Task 7: 后端联调冒烟（真调 DeepSeek）

- [ ] **Step 1: 启动后端**

Run: `cd backend && python -m uvicorn main:app --port 8000 &`（后台）

- [ ] **Step 2: 用 curl 走一遍新游戏 + 行动 + 存档**

```bash
curl -s http://127.0.0.1:8000/api/health
curl -s -X POST http://127.0.0.1:8000/api/new-game \
  -H "Content-Type: application/json" \
  -d '{"archive":{"character":{"name":"林默","gender":"男","age":12,"wuhun":"蓝银草","wuhun_type":"器武魂","innate_soul_power":7,"talent_tier":"天才档","origin":"平民","initial_gold":8,"traits":"瘦削 手上有茧 眼神早熟","personality":["沉稳","多疑"],"secret":"背负家族复仇的执念"},"start_location":"诺丁城","direction":"自由/综合向","timeline_binding":"半绑定"}}'
```

Expected: SSE 流返回 `event: text` 若干 + `event: delta`（含 state 与 options）
- [ ] **Step 3: 记录返回的 session_id，行动一回合**

```bash
curl -s -N -X POST http://127.0.0.1:8000/api/act -H "Content-Type: application/json" -d '{"session_id":"<上面返回的id>","action":"A"}'
```

Expected: 新的 text/delta 流；state 中 turn 递增、好感/金币可能变化
- [ ] **Step 4: 确认 data/saves/<id>/state.json 落盘、存档列表有记录**

```bash
curl -s http://127.0.0.1:8000/api/saves
```
- [ ] **Step 5: 提交**（无代码变更则不提交）

---

### Task 8: 前端脚手架

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.js`, `frontend/index.html`, `frontend/tailwind.config.js`, `frontend/postcss.config.js`, `frontend/src/main.js`, `frontend/src/style.css`, `frontend/src/api.js`, `frontend/src/store.js`, `frontend/src/App.vue`

- [ ] **Step 1: package.json**

```json
{
  "name": "douluo-life-simulator",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": { "dev": "vite", "build": "vite build", "preview": "vite preview" },
  "dependencies": { "vue": "^3.5.0", "markdown-it": "^14.1.0" },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.1.0", "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0", "tailwindcss": "^3.4.0", "vite": "^5.4.0"
  }
}
```

- [ ] **Step 2: vite.config.js**

```js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({
  plugins: [vue()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } }
})
```

- [ ] **Step 3: index.html / tailwind.config.js / postcss.config.js / src/main.js**

`index.html`:
```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>斗罗大陆人生模拟器</title>
</head>
<body class="bg-stone-950 text-stone-200">
  <div id="app"></div>
  <script type="module" src="/src/main.js"></script>
</body>
</html>
```

`tailwind.config.js`:
```js
export default { content: ['./index.html', './src/**/*.{vue,js}'], theme: { extend: {} }, plugins: [] }
```

`postcss.config.js`:
```js
export default { plugins: { tailwindcss: {}, autoprefixer: {} } }
```

`src/main.js`:
```js
import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
createApp(App).mount('#app')
```

`src/style.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
html, body, #app { height: 100%; }
body { font-family: 'Georgia', 'Songti SC', 'SimSun', serif; }
```

- [ ] **Step 4: 安装依赖**

Run: `cd frontend && bun install`（若无 bun 则 `npm install`）

- [ ] **Step 5: 提交** → `git add frontend && git commit -m "feat(frontend): 脚手架"`

---

### Task 9: 前端 API 客户端与 store

**Files:**
- Create: `frontend/src/api.js`
- Create: `frontend/src/store.js`

- [ ] **Step 1: api.js**（含 SSE 消费）

```js
// 消费 POST 的 SSE 流。回调 onText/onDelta/onDone。
export async function postSse(url, body, handlers) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    throw new Error(err.detail || `请求失败 ${resp.status}`)
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    // 按 \n\n 切分 SSE 事件
    let idx
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const raw = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      const lines = raw.split('\n')
      const evt = (lines.find(l => l.startsWith('event:')) || 'event: message').slice(7).trim()
      const dataLine = lines.find(l => l.startsWith('data:'))
      if (!dataLine) continue
      const data = JSON.parse(dataLine.slice(5).trim())
      if (evt === 'text' && handlers.onText) handlers.onText(data.content)
      else if (evt === 'delta' && handlers.onDelta) handlers.onDelta(data)
      else if (evt === 'done' && handlers.onDone) handlers.onDone()
    }
  }
  handlers.onDone && handlers.onDone()
}

export const api = {
  health: () => fetch('/api/health').then(r => r.json()),
  saves: () => fetch('/api/saves').then(r => r.json()),
  save: (session_id) => fetch('/api/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id }) }).then(r => r.json()),
  load: (savepoint_id) => fetch('/api/load', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ savepoint_id }) }).then(r => r.json()),
  del: (session_id) => fetch('/api/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id }) }).then(r => r.json()),
}
```

- [ ] **Step 2: store.js**

```js
import { reactive, ref } from 'vue'

// 游戏会话状态（权威数据来自后端 delta 事件）
export const game = reactive({
  sessionId: null,
  state: null,        // 后端权威 state（含 character/rings/resources/affection...）
  narrative: '',      // 当前回合完整叙述
  streaming: false,   // 是否正在流式
  options: [],        // 当前可用选项 [{label,text}]
  notes: [],          // 本轮新笔记
  event: '',          // 本轮随机事件
  turnDone: false,    // 本轮是否可操作
})

export const ui = reactive({
  view: 'home',        // home | create | game
  showStatus: false,   // 状态栏展开
  showSave: false,     // 存档面板
  busy: false,
})

export const draft = reactive({
  // 创建向导草稿
  identity: '', name: '', gender: '', age: 12, origin: '诺丁城',
  background: '', family: '', secret: '', traits: '',
  personality: '', desire: 5, talentTier: '', wuhun: '', wuhunType: '器武魂',
  developmentDirection: '强攻系', gold: null, specialItems: [],
  direction: '自由/综合向', timelineBinding: '半绑定', customNote: '',
})

export function setGameState(state) {
  game.state = state
  game.sessionId = state?.meta?.session_id || game.sessionId
}
```

- [ ] **Step 3: 提交** → `git add frontend && git commit -m "feat(frontend): API 客户端与 store"`

---

### Task 10: 创建向导 + 档案卡

**Files:**
- Create: `frontend/src/components/CreationWizard.vue`
- Create: `frontend/src/components/CharacterCard.vue`

- [ ] **Step 1: CreationWizard.vue**（5 步表单，含天赋档选择、自定义入口）

关键逻辑（完整 SFC）：
- `step` 1→5，每步一个区块，底部上一步/下一步
- step4 先选天赋档（四档单选），`watch` 后按档位填充 `innate_soul_power` 输入框（凡人1-3/普通4-6/天才7-9/怪物9-10）
- step5 按出身 `origin` 预填金币区间（平民5-10/小家族100-300/宗门500+）
- 每步都有"自定义/其他"文本输入
- 完成 → 组装 `archive` 对象 → 触发 `emits('complete', archive)`
- 天赋约束提示：怪物档也不能开局满环/超常规（文案内置于 UI）

- [ ] **Step 2: CharacterCard.vue**（档案卡确认）

展示所有档案字段 + 天赋档说明 + 「确认，开始游戏」按钮 → `emits('confirm')`

- [ ] **Step 3: 提交** → `git add frontend && git commit -m "feat(frontend): 创建向导与档案卡"`

---

### Task 11: 游戏主界面 + 状态栏 + 存档面板 + App 装配

**Files:**
- Create: `frontend/src/views/HomeView.vue`
- Create: `frontend/src/views/GameView.vue`
- Create: `frontend/src/components/NarrativeStream.vue`
- Create: `frontend/src/components/OptionsBar.vue`
- Create: `frontend/src/components/StatusPanel.vue`
- Create: `frontend/src/components/SavePanel.vue`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: NarrativeStream.vue**

- 全屏滚动容器，`game.narrative` 渲染
- 打字机：流式期间 `onText` 追加；用 `stripArtifacts()` 去掉流式中的 `**`、行首 `##`，结束后用 markdown-it 渲染最终版
- 自动滚到底部

- [ ] **Step 2: OptionsBar.vue**

- `game.options` 渲染为胶囊按钮（`A/B/C/D` 前缀），点击 → `emits('choose', label)`
- 底部自由输入框：快捷指令识别（存档/查看笔记/快进到X/切换方向）+ 自由行动文本
- 输入框回车即提交

- [ ] **Step 3: StatusPanel.vue**（折叠状态栏）

- 右上角 ☰ 切换 `ui.showStatus`
- 展开显示：姓名/性别/年龄/魂力/武魂/先天魂力/地点/季节/日期/魂环配置（slot·年限·魂兽·魂技）/财富/势力声望/好感度/道具/笔记/成就数/回溯次数
- 关键变动加粗：对 `game.state` 做 diff 不好做，改为由 delta 事件里的本轮变动高亮（v1 简化为：每次 delta 后对显示的整体状态栏做一次"数值变动闪烁"——暂不做，直接显示）

- [ ] **Step 4: SavePanel.vue**

- 列表（来自 `/api/saves`）、存档按钮、读档、删除、新开局
- 读档后 `setGameState` + 回到游戏视图

- [ ] **Step 5: HomeView.vue**

- 标题 + 开场白（规则书的开场引导语）+ 三个按钮：开始新游戏 / 继续游戏 / 读档
- 继续游戏 → 列出会话，选一个恢复

- [ ] **Step 6: GameView.vue**（核心装配）

```js
function submit(action) {
  if (game.streaming || !game.sessionId) return
  game.streaming = true; game.turnDone = false
  game.narrative = ''; game.options = []; game.notes = []; game.event = ''
  postSse('/api/act', { session_id: game.sessionId, action }, {
    onText: (t) => { game.narrative += t },
    onDelta: (d) => {
      setGameState(d.state)
      game.options = d.options; game.notes = d.notes; game.event = d.event
    },
    onDone: () => { game.streaming = false; game.turnDone = true }
  }).catch(e => { game.streaming = false; alert(e.message) })
}
```

- [ ] **Step 7: App.vue**

- `ui.view` 分发：home → HomeView / create → CreationWizard(+CharacterCard) / game → GameView
- 创建完成流程：显示档案卡 → confirm → `postSse('/api/new-game', { archive })` → 切到 game 视图
- 顶部常驻：标题 + ☰ 状态栏开关 + 存档按钮

- [ ] **Step 8: 构建验证**

Run: `cd frontend && bun run build`
Expected: 构建成功，`dist/` 产出

- [ ] **Step 9: 提交** → `git add frontend && git commit -m "feat(frontend): 游戏主界面与完整装配"`

---

### Task 12: 端到端联调 + 打磨

- [ ] **Step 1: 双开服务**（后端 8000 + 前端 dev 5173），浏览器手测走完整流程：创建角色 → 档案卡确认 → 开场白 → 选选项 → 状态栏更新 → 存档 → 新开 → 读档
- [ ] **Step 2: 打磨**：空状态提示、错误提示、移动端布局、流式期间选项禁用
- [ ] **Step 3: 写 README.md**（启动方式、项目结构）
- [ ] **Step 4: 提交** → `git add -A && git commit -m "docs: README 与打磨"`

---

## Self-Review 记录

- **Spec 覆盖**：规格 4 节（状态模型）→ Task 1/2；第 5 节（提示词）→ Task 4/5；第 6 节（校验）→ Task 1/2；第 7 节（创建向导）→ Task 10；第 8 节（API）→ Task 6；第 9 节（前端）→ Task 8-11；第 10 节（存储存档）→ Task 3/6；第 11 节（错误处理）→ Task 6 `_call_settle` 重试 + `_call_narrative` 容错；第 12 节（范围边界）→ 全部遵守；第 13 节（规则书集成）→ Task 4。
- **占位符扫描**：无 TBD/TODO；每步含实际代码或明确指令。
- **类型一致性**：`default_state`/`validate_delta`/`apply_delta`/`save_state`/`build_*_messages` 签名在跨任务引用处一致；delta 键名在 Task 1/4/5/6 中统一（gold/silver/copper/soul_level/affection/location/date/month_delta/inventory_add/inventory_remove/notes_add/soul_ring_add）。
