# 《万界人生模拟器》开发者指南

> 新世界创建 · 推送到 GitHub · 技术知识总结
> 适用于站长 / 开发者本人。文档随代码演进，若与实际不符，以代码为准并顺手修正本文。

本文分三大部分：

- **第一部分 · 创建新世界**：内置世界的完整流程——写两个文件 → 可选加专属摘要 → 写测试 → 本地验证 → 上线。
- **第二部分 · 推送到 GitHub**：提交前安全扫描 → 提交 → 推送 → Render 自动部署，以及仓库可见性的安全提醒。
- **第三部分 · 技术知识总结**：前后端架构、权威状态与结算模型、SSE 协议、订阅门禁、会话存档、自由度、部署配置、常见坑速查。

---

## 第一部分：创建新世界

### 1.1 世界系统本质

**一个世界 = 一个 JSON 规格 + 一段规则书文本。新增内置世界不需要改任何 Python/前端代码。**

- 世界规格：`backend/worlds/<id>.json`（内置，进 git）
- 规则书：`backend/prompts/<id>_system_prompt.txt`（规则书文本，进 git）
- 自建世界：`backend/data/worlds/<id>.json`（玩家上传小说生成，**不入 git**，仅作者可见）

发现机制（[backend/game/worlds.py](backend/game/worlds.py)）：`builtin_worlds()` 用 `sorted(BUILTIN_DIR.glob("*.json"))` 扫目录，每份 JSON 里的 `rulebook_file` 指向规则书文本（相对仓库根解析）。**广场排序按文件名（字典序）**，不是声明顺序。

⚠️ **缓存**：服务端对世界规格有内存缓存（`worlds._cache` + `_CACHE_VALID`，首次访问构建）。新增/修改内置世界 JSON 或规则书后**必须重启后端**，广场才会显示——这是故意为之（内置世界变化少，省去每次扫描）。

### 1.2 第一个文件：`backend/worlds/<id>.json`

完整字段表（以《太上浮黎》`taishangfuli.json` 为范本）：

```json
{
  "id": "taishangfuli",
  "name": "太上浮黎",
  "kind": "builtin",
  "owner": null,
  "desc": "一句话简介（广场卡片用）",
  "rulebook_file": "backend/prompts/taishangfuli_system_prompt.txt",
  "summary": "taishangfuli",
  "state_template": {
    "character": {
      "name": "无名", "gender": "?", "age": 18,
      "identity": "太虚剑宗外门弟子", "origin": "陈塘村",
      "root": "中品金灵根", "direction": "剑修",
      "traits": [], "personality": [],
      "realm": {"init": 1, "min": 1, "max_step": 1}
    },
    "level_field": "realm",
    "resources": {"灵石": {"init": 50, "min": 0}},
    "stats": {
      "灵力": {"init": 20, "min": 0, "max": 1000, "max_step": 30},
      "神识": {"init": 5,  "min": 0, "max": 500, "max_step": 20},
      "体魄": {"init": 20, "min": 0, "max": 500, "max_step": 20}
    },
    "affection_chars": ["谢尘", "苏清月", "周寒", "柳依依", "云鹤真人"],
    "affection_min": -100, "affection_max": 100,
    "factions": ["太虚剑宗", "玄天盟", "万妖山脉", "归墟渊"],
    "inventory": [],
    "start_location": "太虚剑宗·山门",
    "meta": {"rewind_left": 3}
  },
  "creation_schema": { "steps": [ ...见下... ] }
}
```

字段逐项说明：

| 字段 | 含义 / 规则 |
|---|---|
| `id` | 内部标识，小写英文。旧存档靠它恢复世界，**上线后不要改**。 |
| `kind` | 只能是 `builtin` 或 `custom`。内置写 `builtin`，`owner: null` = 人人可见。 |
| `desc` | 广场卡片一句话简介。 |
| `rulebook_file` | 规则书文件路径（相对仓库根）。也可以直接用 `rulebook` 内联大文本（自建世界走这种）。 |
| `summary` | 状态摘要路由：填世界 id 会走 `prompt_builder.py` 里的专属摘要函数；填 `generic` 走通用模板（见 1.4）。 |
| `character` | 角色字段。标量给默认值；`realm` 这类等级字段给 `{init, min, max_step}` 规格（见下）。 |
| `level_field` | 等级字段名（如 `realm`），必须对应 `character` 里的键。后端按"绝对目标 + 每轮限步"钳制。`summary` 非 `generic` 时**必填**——缺它或类型错，`_validate_spec` 会抛 `ValueError`。 |
| `resources` | 资源字典：`{资源名: {init, min}}`。min 决定最多扣到多少（不能为负）。初始值除 `init` 外还支持 `from_archive`（取档案指定字段）与 `origin_field`+`origin_defaults`（按身份映射初始值），参考 douluo 的 gold：`{"init": 10, "min": 0, "from_archive": "initial_gold"}`。 |
| `stats` | 属性字典：`{属性名: {init, min, max, max_step}}`。max_step 限每轮增减幅度，min/max 限上下界。 |
| `affection_chars` | 好感人物名单（开局全 0），可动态新增。`affection_min/max` 钳制好感区间（默认 ±100）。 |
| `factions` | 势力名单（开局全 0），只认名单里的，未知势力会被忽略。 |
| `inventory` | 初始道具。 |
| `start_location` | 开局地点。 |
| `meta.rewind_left` | "后悔"回退次数（默认 3，四个内置世界均为 3）。注：20 是后端撤销快照栈的全局上限 `UNDO_LIMIT`（见 3.7），与 rewind_left 无关。 |

**等级字段（level_field）的三种规格形态**：

```json
// 1) 绝对目标 + 限步（realm 境界）——AI 输出绝对值，每轮最多 ±1
"realm": {"init": 1, "min": 1, "max_step": 1}
// 2) 绝对目标 + 上下界（gebi 心动值）——heart 0-100，每轮最多 ±8
"heart": {"init": 0, "min": 0, "max": 100, "max_step": 8}
// 3) 绝对目标 + floor_from 兜底（魂兽大陆魂力等级随"先天魂力"角色字段保下限）
"soul_level": {"init": 5, "max_step": 2, "floor_from": "innate_soul_power"}
```

⚠️ `realm` 这类"只升不跌"的境界务必写 `"min": 1`——否则 AI 误输出 `realm: 0` 时会被当作绝对目标 0 直接清空境界（这是修过的真实 bug）。

⚠️ `floor_from` 只能引用 `state_template.character` **里的键**（如先天魂力 `innate_soul_power`），**不能指向 stats 属性**——后端从 `state["character"]` 取兜底值，写 stats 键会读到 0、境界被钳回 0。万物生 realm 未用 floor_from。

**`creation_schema`（创建向导，驱动前端表单）**：

```json
"creation_schema": {
  "steps": [
    {
      "step": "你是谁",
      "fields": [
        {"key": "name", "label": "姓名", "type": "text", "placeholder": "你的名字", "required": true},
        {"key": "gender", "label": "性别", "type": "select", "options": ["男", "女"], "required": true},
        {"key": "age", "label": "年龄", "type": "number", "min": 14, "max": 45, "default": 18}
      ]
    },
    {
      "step": "出身与根骨",
      "fields": [
        {"key": "identity", "label": "身份背景", "type": "select", "options": ["太虚剑宗外门弟子", "散修少年"], "required": true},
        {"key": "traits", "label": "天生特质", "type": "multiselect", "placeholder": "风隙天资, 灵识敏锐"},
        {"key": "secret", "label": "执念秘密", "type": "textarea", "rows": 2}
      ]
    }
  ]
}
```

- 字段类型支持：`text` / `textarea` / `number` / `select` / `multiselect` / `boolean`（未知类型兜底 text）。
- **关键约束：`fields[].key` 必须与 `state_template.character` 里的键一一对应**——前端 `GenericWizard.buildArchive()` 把表单值打包成 `{character: {key: value}}`，`default_state()` 只取 character 模板里存在的键，对不上的会被丢弃。
- `multiselect` 是文本输入、逗号分隔，前端切成数组。
- `number` 支持 `min` / `max` / `default`；`select` 的 options 支持字符串或 `{value, label}` 对象。

### 1.3 第二个文件：`backend/prompts/<id>_system_prompt.txt`

规则书是喂给 DeepSeek 的 system prompt，决定世界质感与行为约束。四份内置规则书的通用骨架（节标题示例，可按世界裁剪）：

```
# 角色设定
# 一、核心原则（置于一切之上）     → 玩家意愿最高、选项驱动、自由度
# 二、世界观                       → 地图/区域、核心法则
# 三、境界体系 / 势力 / 核心人物    → 数值表 + 名字 + 性格
# 四、剧情走向（正典大纲）          → 供 AI 把握节奏，不强制玩家走完
# 五、核心机制                     → 时间推进、战斗、经济、好感、势力声望
# 六、开局引导                     → 开场怎么起
# 七、文风与叙述约束（硬性规定）    → 禁止句式、选项写法、关键数字加粗
# 八、对 AI 引擎的输出契约（必读，最高优先级）  → JSON 结算契约
```

**输出契约（结算 JSON）是最关键的一节**，必须与后端 `validate_delta` 的键精确对应：

```json
{
  "options": [
    {"label": "A", "text": "选项文字", "recommended": true},
    {"label": "B", "text": "..."},
    {"label": "C", "text": "..."},
    {"label": "D", "text": "..."}
  ],
  "state_delta": {
    "resources": {"灵石": 0},
    "stats": {"灵力": 0, "神识": 0, "体魄": 0},
    "realm": null,
    "affection": {"谢尘": 3},
    "faction": {"太虚剑宗": 2},
    "location": "太虚剑宗·山门",
    "date": "第1年1月",
    "month_delta": 0,
    "inventory_add": [], "inventory_remove": [], "notes_add": []
  },
  "notes": [],
  "event": ""
}
```

契约措辞要点（照抄进你的规则书）：

- **增量 vs 绝对目标**：`resources` / `stats` / `affection` / `faction` 一律是**增量**（正负均可）；`level_field`（realm/heart/soul_level）是**绝对目标数值**，本轮没变写 `null`，绝不能写 0。
- realm 未突破必须写 JSON 原生 `null`——若写 0 会被后端当作目标 0，直接跌穿境界（修过的 bug）。
- `month_delta` 0-24（游戏内经过的月数）；`date` 文本与叙述里的时间一致。
- 未知势力/未知属性会被后端静默忽略；好感可动态新增人物。
- `options` 3-4 个，**恰好一个** `"recommended": true`（系统推荐最符合剧情走向的选项）。
- 无势力声望的世界（如隔壁的租客）明确写"不要输出 faction 键"。
- 只输出 JSON，不要解释文字。

各内置世界的等级字段对照：

| 世界 | level_field | 资源 | 属性 | 境界名 |
|---|---|---|---|---|
| 魂兽大陆 douluo | `soul_level` | gold/silver/copper | （魂环制） | 魂力等级 |
| 万物生 wanwusheng | `realm` | 元 | 灵力/神识/体魄 | 吐纳→交感→天人→化羽→地君→天君→无上 |
| 隔壁的租客 gebi | `heart`（0-100 ±8） | 元 | 灵感/精力/心情 | 心动值 |
| 太上浮黎 taishangfuli | `realm` | 灵石 | 灵力/神识/体魄 | 炼气→筑基→金丹→元婴→化神→炼虚→合道 |

### 1.4 可选：专属状态摘要

默认 `summary: "generic"` 走通用模板（[prompt_builder.py](backend/game/prompt_builder.py) 的 `_generic_summary`），会把 character 字段 + 资源 + 属性 + 好感 + 势力 + 道具 + 笔记列成几行。若要定制（比如把 realm 数字渲染成中文境界名），在 `prompt_builder.py` 加专属函数并挂到 `state_summary`：

```python
_TAISHANG_REALMS = {1: "炼气", 2: "筑基", 3: "金丹", 4: "元婴", 5: "化神", 6: "炼虚", 7: "合道"}

def _taishangfuli_summary(state: dict) -> str:
    c = state["character"]
    realm = int(c.get("realm", 1))
    realm_name = _TAISHANG_REALMS.get(realm) or f"未知（{realm}）"
    # ...拼出多行摘要...

def state_summary(state, world=None):
    s = world.get("summary")
    if s == "taishangfuli":
        return _taishangfuli_summary(state)
    # ...其余世界分支...
    return _generic_summary(state, world)
```

摘要会以「【当前状态】/【新角色状态】」system 消息喂给每轮 AI，所以**把玩家需要被记住的关键信息都放进去**。

### 1.5 写测试（镜像模式）

新世界的测试照抄 `test_wanwusheng.py` / `test_taishangfuli.py` 的骨架（19 个测试文件、184 用例全通过，约 6 秒）。固定套路：

1. 顶部两行注入 backend 到 sys.path（仓库无 conftest/pytest.ini，每文件自插）：
   ```python
   import sys
   from pathlib import Path
   sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
   ```
2. 固定 import 四件套：`from game import worlds` / `from game.game_engine import apply_delta` / `from game.prompt_builder import state_summary` / `from game.state_schema import default_state, validate_delta`。
3. 按顺序写断言：
   - **规格加载**：`worlds.get_world("<id>")` 非 None、name、`kind=="builtin"`、`owner is None`、`summary=="<id>"`、`len(rulebook) > 200`、模板关键字段。
   - **广场排序**：`[w["id"] for w in worlds.builtin_worlds()]` 断言新世界排在对应位置（文件名 dict 序）。
   - **默认状态**：`default_state(archive, w)` 断言 realm==1、资源 init、stats、好感全 0、势力全 0、location。
   - **等级钳制**：`validate_delta({"realm": 9}, s, w)["realm"] == 2`（绝对目标 + max_step=1，越级冲被钳回）+1；realm 压零 `{"realm": 0}` → 1（min=1 兜底）。
   - **stats 钳制**：灵力 999 → 30（max_step）。
   - **好感/势力**：合法键落账，未知势力/属性被忽略。
   - **资源/道具**：扣到 min、inventory_add 追加。
   - **摘要渲染**：`state_summary(s, w)` 含中文境界名、资源名、地点。
   - **正典覆盖**（可选）：断言规则书里含关键剧情锚点词。
4. 跑：`cd backend && python -m pytest tests/test_<id>.py -q`。

端到端（走 HTTP 的）测试要打 LLM 桩：fixture 里 `monkeypatch.setattr(main, "_stream_narrative", 生成器桩)` + `monkeypatch.setattr(main, "_call_settle", 固定 dict 桩)`，并重定向 `sm.SAVES_DIR` / `sm.ACTIVATIONS_PATH` 到 tmp_path、清 `main._SESSIONS`，返回 `TestClient(main.app)`。`_stream_narrative` 桩必须是含 `yield` 的生成器函数（它被当迭代器消费）。

### 1.6 本地验证清单

```bash
# 1. 全量测试
cd backend && python -m pytest -q            # 期望 184 passed

# 2. 重启后端（内置世界有缓存，不重启不显示）
cd backend && uvicorn main:app --port 8124   # 本地后端端口是 8124，不是 README 写的 8000

# 3. 确认广场出现新世界
curl -s "http://localhost:8124/api/worlds" | python -m json.tool   # builtin 里应有 <id>

# 4. 真实 smoke test（一次真实 DeepSeek 调用，验证规则书→开场叙述→结算全链路）
#    把 JSON 写到 Windows 绝对路径（curl 是原生程序，读不懂 MSYS 的 /tmp）
#    请求体只要 archive 必填；world_id 填新世界 id，archive 的键与 creation_schema 一致，例如：
#    {"world_id": "<新世界id>", "archive": {"character": {"name": "测试", "gender": "男", "age": 18}}, "freedom": 3}
curl -s -N -X POST http://localhost:8124/api/new-game \
  -H "Content-Type: application/json" \
  --data-binary @"C:/Users/ASUA/douluo-simulator/backend/smoke_body.json"
# 期望 SSE：多次 event: text（流式叙述）→ event: delta（状态+选项）→ event: done；无 error
```

### 1.7 前端零改动

前端 `GenericWizard.vue` 完全由 `creation_schema` 驱动，`CharacterCard.vue` 对非魂兽大陆世界走通用档案卡（label 取自 creation_schema）。**新增内置世界前端一行不用改**，广场自动出现、创角向导自动生成。

---

## 第二部分：推送到 GitHub

### 2.1 提交前：激活码泄露扫描（必须）

⚠️ 仓库里提交了激活码池 `backend/data/activation_codes.json`（366 个码）。**提交任何改动前**，扫描暂存区是否把真码混进了别的地方：

```bash
git add <你的文件>
git diff --cached | grep -nE '[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}' \
  && echo "!!! 发现疑似激活码，停手 !!!" || echo "OK: 无泄露"
```

测试文件里的假码（`TEST-0000-000` 之类）不匹配 4-4-4 模式，可放心。

### 2.2 提交 + 推送

```bash
cd C:/Users/ASUA/douluo-simulator

# 提交（提交信息用文件传入，避免 shell 引号/中文问题）
cat > /tmp/msg.txt <<'EOF'
<提交信息，如：feat: 新增内置世界《xxx》>
EOF
git add backend/worlds/<id>.json backend/prompts/<id>_system_prompt.txt backend/game/prompt_builder.py backend/tests/test_<id>.py
git commit -F /tmp/msg.txt

# 推送：当前开发仓库是测试版 test-server，老仓库 origin 已冻结（按既定工作流只推 test-server）
git push test-server main      # 测试/开发仓库（主推送目标）
# git push origin main          # 老仓库（liz296738-jpg/-Multiverse-Life-Simulator）一般不推
# 提交前用 git remote -v 核对两个 remote 名，别推错
```

### 2.3 Render 自动部署

`render.yaml`（Blueprint）读取 `Dockerfile` 多阶段构建，push 到**测试仓库 test-server 的 main** 即自动触发重部署。⚠️ 若 Render 的部署源仍绑定老仓库 origin，请先在 Render 控制台把构建源切到 test-server，否则推 test-server 不会触发部署。

1. 阶段 1：`oven/bun:1` 装前端依赖（`bun install --frozen-lockfile`）→ `bun run build` → 产出 `frontend/dist`。
2. 阶段 2：`python:3.11-slim` 把 dist 拷进 `frontend/dist`，`COPY backend/`，`pip install -r requirements.txt`。
3. 后端 `main.py` 末尾在 `frontend/dist` 存在时 `app.mount("/", StaticFiles(...))`——**同源托管前端 + /api**，无需跨域。
4. `CMD uvicorn main:app --port ${PORT:-10000}`，健康检查 `GET /api/health`。
5. `DEEPSEEK_API_KEY` 在 render.yaml 里是 `sync: false`——首次部署时在 Render 控制台手动填。

本地端口 8124 vs 线上 10000 由 PORT 环境变量隔离，无需改代码。

### 2.4 仓库可见性：激活码安全（务必读完）

**码池是随仓库走的**：`.gitignore` / `.dockerignore` 都白名单放行了 `backend/data/activation_codes.json`（提交 1e0459c 的教训：曾把整个 data/ 排除，导致线上容器里一个码都没有、所有激活全失败）。因此：

- 只要仓库是 **Private**，码池就是安全的。
- 若仓库是 **Public**，任何人都能读走全部 366 个码 → 订阅门禁形同虚设。
- 提交/推送前扫描真码模式（见 2.1）；文档/示例里一律用假码 `1234567890`。
- 每次换新仓库/新部署，先确认可见性再推。

---

## 第三部分：技术知识总结

### 3.1 整体架构

```
┌─────────────┐   SSE (text/delta/done)   ┌──────────────┐   HTTPS   ┌────────────┐
│ Vue 3 前端   │ ────────────────────────► │ FastAPI 后端  │ ────────► │ DeepSeek   │
│ (Vite+      │ ◄──────────────────────── │ (权威状态账本) │ ◄──────── │ deepseek-  │
│  Tailwind)  │   流式叙述 + 结算 JSON      │  main.py     │           │ chat       │
└─────────────┘                           └──────┬───────┘           └────────────┘
                                                 │ 落盘
                                          backend/data/
                                          (saves/ activations.json activation_codes.json)
```

- **前端**：Vue 3 + Vite + Tailwind，无 vue-router，用 `store.ui.view` 状态机切视图（home / create / review / game）。
- **后端**：FastAPI，单进程；权威状态全在后端，AI 只提交增量。
- **模型**：DeepSeek `deepseek-chat`，兼容 OpenAI SDK（`base_url=https://api.deepseek.com`）。
- **生产**：后端同源托管前端 dist（Docker + Render）。

### 3.2 权威状态与结算模型（核心设计）

数据流：**AI 只输出增量 → 后端校验钳制 → 落账**。

- `default_state(archive, world)`：创建档案 + 世界模板 → 初始权威状态。
- `validate_delta(delta, state, world)`：清洗 AI 的增量（不改 state），钳制规则：

| 键 | 规则 |
|---|---|
| `resources` | 增量，最多扣到 `min`（不能为负） |
| `stats` | 增量，`max_step` 限步，`min`/`max` 限界，**未知属性忽略** |
| `level_field`（realm/heart/soul_level） | **绝对目标**，`max_step` 限步（±），`min`/`max` 限界，`floor_from` 兜底 |
| `affection` | 增量，钳到 `[affection_min, affection_max]`，**允许动态新增角色** |
| `faction` | 增量，钳到 `[affection_min, affection_max]`，**未知势力忽略** |
| `soul_ring_add` | 魂兽大陆专属，按 `cap_slots` 钳年限、不可跳环 |
| `inventory_add/remove`、`notes_add` | 字符串列表；inventory 去重 |
| `location` / `date` | 字符串，`null` 保留旧值 |
| `month_delta` | 0-24 |

- `apply_delta(state, delta, world)`：落账 → 月份推进 → 好感衰减（本月未见面角色按月衰减，最多 -3）→ 季节推断（`_guess_season` 按中文季节词或月份）→ `turn` +1。
- **健壮性**：AI 吐 null/脏类型不崩（`test_delta_robustness` 覆盖）。

### 3.3 两阶段生成（流式）

每回合两次 LLM 调用（`_run_turn`）：

1. **阶段一「叙述」**：`_stream_narrative` 真流式——DeepSeek `stream=True`，攒满 48 字符推一块，玩家 ~2 秒见第一个字。`temperature=0.85`，`max_tokens` 按自由度档位（见 3.8）。
2. **阶段二「结算」**：需要完整叙述才能算增量，`_call_settle` 单独调用，`temperature=0.3`，`response_format={"type":"json_object"}`，失败自动重试一次，再失败自愈 `{}`（本回合仍正常结束）。

选项规范化 `_normalize_options`：保证 `label/text/recommended`，且**恰好一个系统推荐**（AI 没标或标多 → 取第一个）。

### 3.4 SSE 事件协议

`/api/new-game` 与 `/api/act` 返回 `text/event-stream`：

| 事件 | 时机 | data |
|---|---|---|
| `text` | 叙述流式生成中（多次） | `{"content": "..."}` |
| `delta` | 叙述完成 + 结算落账后 | `{"state", "options", "notes", "event", "can_undo"}` |
| `done` | 回合完整结束 | `{}` |
| `error` | 生成/结算失败 | `{"message": "友好中文提示"}` |

前端 `postSse`（api.js）：fetch + AbortController，默认 90s 超时，按 `\n\n` 分帧解析。**只有收到 `done` 才算回合完整**；中断/超时丢弃残篇不归档。失败回合不写 history、不计免费试玩（`_bump_trial` 只在成功后调用）。

### 3.5 订阅门禁与激活码

**码池方案**（`game/activation_codes.py`）：

- 一个码对应一年中的一个"日子"（键 `MM-DD`，含闰日 02-29 共 **366 个码**），每年同一天循环用同一个码——一次生成、长期复用。
- 码格式 `XXXX-XXXX-XXXX`，字符集去掉 0/O、1/I（`ABCDEFGHJKLMNPQRSTUVWXYZ23456789`），随机不可伪造。
- **只有当天能激活**；激活后从对应日算起 **30 天**有效（到期日 23:59:59）。
- 站长工具：双击 `backend/发激活码.bat` 或 `python generate_code.py`（首次自动补齐全年，之后只查看不改已发码）。

**时间线正确性**（修过的真实 bug）：服务器常跑在 UTC，"今天"必须以**中国时区（UTC+8）墙钟**计算——`_cn_now()` 返回 naive 北京时刻。否则北京 0:00-8:00 之间会把 8/11 的码拒成"今天 8/10"。

**隐私**：非当天激活的提示只写「激活码错误或已过期」，**不透露码对应的日期**（修过的隐私问题）。

**门禁判定**（`_gate_for`）：

1. 请求带 `code` 且码池校验通过 → 放行；
2. 登记表 `paid_until` 镜像在有效期 → 放行（当天激活后写盘，之后不带码也认）；
3. 否则免费试玩 `FREE_TRIAL_TURNS`（默认 5）用尽 → 403「免费试玩已结束」。

**BYOK（零成本）**：玩家在创角页填自己的 DeepSeek Key（存 localStorage），随请求 `api_key` 下发；`_client_for(api_key)` 优先玩家 Key，回落服务端 Key；服务端无 Key 且玩家不填 → 提示「站点未配置默认额度，请填写自己的 Key」。自建世界的建世界调用全程用玩家 Key 计费。

### 3.6 自建世界（上传小说生成）

玩家在「我的世界」上传小说 → 后端用**玩家自己的 DeepSeek Key** 生成世界规格（站点零成本）：

1. **上传**：`/api/worlds/upload` 收原始文件，`validate_upload_size` 限 **30MB**（novel_parser.py `_MAX_SIZE`）；`extract_text` 解析 txt/docx（txt 按 utf-8-sig → gb18030 → gbk → big5 → latin-1 顺序探测解码），**不落盘存原文**。
2. **抽样精读**：`sample_text` 取开头 15000 + 结尾 10000 字符喂给 AI，`clean_text` 清洗噪声。
3. **生成规格**：`world_builder.build_world` 用玩家 Key 调 DeepSeek，按 `BUILD_PROMPT` 契约生成完整 world 规格（含 creation_schema / state_template / 内联 rulebook），失败自动重试一次。
4. **落盘**：生成结果存 `data/worlds/<id>.json`（**不入 git**，data/ 入库状态见 3.10 表），`kind: "custom"`、`owner` 记作者 client_id。
5. **鉴权**：`/api/worlds/build` 限流**每个 client 每小时 5 次**（`_BUILD_LIMIT`）；`_resolve_world` 对 custom 世界校验作者，**非作者一律 404**（不泄露世界存在）。

### 3.7 会话 · 存档 · 撤销 · 导出

- **内存会话**：`_SESSIONS[session_id] = {state, history, archive, last_options, turns, undo_stack}`。
- **冷启动恢复**：从磁盘读 `data/saves/<id>/state.json` + `history.jsonl` + `turns.json` + `undo.json`。
- **每回合落盘**：state.json / history.jsonl / turns.json / undo.json 每回合写一次；**每 10 回合自动建存档点**（`savepoints/<id>-<时间戳>.json`）。
- **后悔（回退）**：`/api/undo` 弹快照栈，还原状态/历史/选项/回合；最多 20 层；开场回合不可撤销；读档后撤销栈置空重新积累。
- **导出**：`/api/export` 把全部叙述历史整理成 Markdown 小说（纯本地、无 AI 调用、不设门禁）。
- **路径安全**：session/savepoint id 走白名单正则（`^[A-Za-z0-9][...]{0,63}$`），防 `../` 目录穿越（`test_path_safety` 覆盖）。

### 3.8 自由度档位与限长

右上角常驻"自由度"按钮，五档：精炼 200 字 / 简洁 500 / 标准 1000 / 详尽 1500 / 极尽 2000。每档对应 `max_tokens` 预算（320→3200），随每次 new-game/act 请求下发。规则书的固定 150-250 字叙述限制会被 `_append_length_hint` 覆盖（以字数要求为准），高档位用"至少 5 段展开"的结构指令控制篇幅。

限长既控成本又控延迟：叙述 `NARRATIVE_MAX_TOKENS=1200`、结算 `SETTLE_MAX_TOKENS=600`（自由度高时随档位上调）。历史裁剪：`_history_messages` 按 60 条 + 20000 token 双重上限，从新往旧裁（1 中文字 ≈ 1.3 token）。

### 3.9 前端要点

- **世界广场**：`HomeView` 两个 section（创作者已开发的世界 / 我的世界），点卡片 → `worlds.selected` → 视图 `create`。
- **创角**：非魂兽大陆世界走 `GenericWizard`（schema 驱动），魂兽大陆走专用 `CreationWizard`；完成后 `CharacterCard` 预览 → 确认 → `postSse('/api/new-game')`，body 里 `world_id = worlds.selected?.id || 'douluo'`。
- **客户端身份**：`localStorage 'douluo_client_id'`（crypto.randomUUID 去横线，非安全上下文回落 Math.random）——门禁按它记账。激活码存 `douluo_sub_code`，随请求携带。
- **门禁 403 触发弹窗**：`isGateError(e)` 用正则 `/(激活|订阅|试玩)/` 匹配错误消息 → 弹 `ActivationPanel` 而不是普通 alert。
- **BYOK**：`douluo_api_key` 存 localStorage，随 `api_key` 下发；仅存本浏览器、不进存档。
- **回合归档时机**：`commitTurn` 在【新回合开始前】调用（而非 delta 时）——当前回合 DOM 全程不重建、防页面跳动；只有收到 delta（`turnCommitted=true`）的回合才归档。

### 3.10 部署与配置速查

| 项 | 值 |
|---|---|
| 本地后端 | `uvicorn main:app --port 8124`（README 的 8000 已过时） |
| 前端 dev | `cd frontend && bun run dev` → `http://localhost:5173`，`/api` 代理到 `127.0.0.1:8124` |
| 前端构建 | `cd frontend && bun run build` → `frontend/dist`（改代码后需重新 build，dev server 不动 dist） |
| 线上 | Render + Docker，PORT=10000，健康检查 `/api/health` |
| 环境变量 | `DEEPSEEK_API_KEY`（服务端 Key，可选）、`FREE_TRIAL_TURNS`（默认 5） |
| 依赖 | fastapi / uvicorn[standard] / openai>=1.0 / python-dotenv / pydantic / pytest / httpx / python-docx / python-multipart |

**data/ 目录入库/入镜像状态**（改动 .gitignore/.dockerignore 时务必保持）：

| 文件 | 进 git | 进镜像 | 说明 |
|---|---|---|---|
| `activation_codes.json` | ✅（白名单） | ✅（白名单） | 码池，必须随部署上线 |
| `activations.json` | ❌ | ❌ | 订阅登记表，Render 免费实例重启即丢（玩家重输激活码可恢复） |
| `saves/` | ❌ | ❌ | 存档 |
| `worlds/`（自建） | ❌ | ❌ | 玩家自建世界，仅作者可见 |

### 3.11 常见坑速查

- **改了内置世界不显示** → 没重启后端（worlds 缓存）。
- **内置世界 JSON 校验不过也不显示、且毫无报错** → `builtin_worlds()` 加载失败会**静默跳过**（catch 掉 ValueError 后 continue，无日志）。先本地验证 JSON：`python -c "import json;json.load(open('backend/worlds/<id>.json',encoding='utf-8'))"`，再查缺 level_field（summary 非 generic 时必填）等硬约束。
- **广场排序不对** → 按文件名 dict 序，不是 JSON 里的顺序。
- **realm 变 0** → 等级字段没写 `"min": 1`。
- **创角字段丢** → creation_schema 的 key 与 state_template.character 键不一致。
- **「激活码无效」线上全挂** → 镜像里没有码池（.dockerignore 误排除了 activation_codes.json，见 1e0459c）。
- **北京凌晨激活码日期不对** → 后端没跑 UTC+8（`_cn_now`）。
- **前端连不上后端** → 端口是 8124 不是 8000。
- **测试加了新文件跑不起来** → 少了顶部 `sys.path.insert` 两行（无 conftest）。
- **SSE 残篇当完整回合** → 前端只有收到 `done` 才归档，别提前 commitTurn。
- **激活码示例被玩家照抄** → 示例一律用假码 `1234567890`（b4f4c5b 修正过）。
- **新仓库/新部署** → 先确认仓库可见性是 Private，再推（码池随仓库走）。
