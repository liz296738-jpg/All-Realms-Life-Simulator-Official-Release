# 多世界平台化改造设计（世界 = 规格）

> **日期**：2026-08-10
> **状态**：待评审
> **范围**：把单游戏《斗罗大陆人生模拟器》改造成可容纳任意模拟世界的平台，并支持「玩家上传小说 → 构建自定义世界」

## 1. 背景与目标

现在站点是一个单一游戏：斗罗大陆人生模拟器。引擎（状态模型、结算契约、创建向导）全部斗罗专属硬编码。目标：

1. **平台化**：首页变成「世界广场」，容纳斗罗大陆 + 以后陆续发布的更多官方世界。
2. **玩家自定义世界**：玩家上传一本小说的 TXT/DOCX，站点用玩家的 DeepSeek API Key 生成一套世界框架（规则书 + 状态模板 + 创建字段），玩家即可在这套框架里游玩。自建世界**仅作者本人可见**，不做分享/广场/公开。

## 2. 关键决策记录（已与用户确认）

| # | 决策 | 结论 |
|---|---|---|
| 1 | 建世界的成本归属 | 必须填玩家自己的 DeepSeek Key 才能用「上传小说建世界」，站点零成本、防刷 |
| 2 | 小说处理方式 | 抽样精读：取 开头≈1.5万字 + 结尾≈1万字 + 中间随机几段，拼成 ≈3.5万字，一次调用生成 |
| 3 | 自建世界可见性 | 仅作者本人可见；不做分享码、不做公开广场 |
| 4 | 引擎改造方案 | 方案 A：世界化重构（引擎按「世界规格」驱动，斗罗变为一个规格） |

## 3. 架构总览：世界 = 一个 JSON 规格

```
一个世界 world = {
  id: string,                  // 唯一标识（斗罗为 "douluo"，自建为 uuid hex[:12]）
  name: string,                // 世界名（如 斗罗大陆 / 诡秘之主…）
  desc: string,                // 一句话简介（世界广场卡片展示）
  kind: "builtin" | "custom",  // 官方世界 / 玩家自建
  owner: client_id | null,     // 自建世界的作者（builtin 为 null）
  rulebook: string,            // 规则书全文（斗罗 = 现有 prompts/system_prompt.txt 内容）
  state_template: { ... },     // 状态模板：资源/属性/好感预置/势力/初始值/可选进阶表
  creation_schema: { ... },    // 创建向导字段模板（自建世界由 DeepSeek 生成）
  created_at: iso | null       // 自建世界记录创建时间
}
```

- 引擎所有入口带 `world` 参数：`default_state(world, archive)`、`validate_delta(delta, state, world)`、`apply_delta(state, delta, world)`、`prompt_builder` 系列。
- 服务器启动时从 `data/worlds/*.json` 加载全部世界（builtin 斗罗也作为文件存在）。
- 会话存储 `world_id`；`new-game/act/resume` 请求带 `world_id`，**缺省回落 "douluo"**，保证旧存档、旧接口、旧玩家体验不变。

### 3.1 状态模型通用化

内部权威状态统一为通用结构：

```python
{
  "character": {...},        # 通用字段：name/gender/age/origin/background/secret/traits/...（无斗罗专属武魂）
  "resources": {"金魂币": 10, "银魂币": 0, "铜魂币": 0},   # 任意资源/货币，来自 state_template
  "stats": {"魂力": 5},       # 任意属性，来自 state_template
  "affection": {},            # 好感：任意角色名，可动态添加（不再预置死名单）
  "affection_last_seen": {},
  "faction": {},              # 势力声望：来自 state_template（可为空）
  "inventory": [],
  "notes": [],
  "location": {"place","season","date"},
  "meta": {"turn","month","undo_left","achievements","direction","timeline_binding","session_id","created_at"}
}
```

`state_template` 规格：

```json
{
  "resources": {"金魂币": {"init": 10, "min": 0}},
  "stats": {"魂力": {"init": 5, "min": 1, "max": 100}},
  "affection_chars": [],             // 预置好感角色（可空，运行时动态加）
  "affection_min": -100, "affection_max": 100,
  "factions": [],                    // 预置势力（可空）
  "inventory": [],
  "start_location": "诺丁城",
  "rings": null | {"cap_slots": [423, 764, 1760, 5000, 12000, 20000, 50000, 80000, 100000]}
  // rings 非空 = 启用"进阶/魂环"列表特性（斗罗专属）；自建世界通常为 null
}
```

### 3.2 结算契约通用化 + 斗罗兼容层

`settle` JSON 顶层保持 `{options, state_delta, notes, event}`。`state_delta` 改为通用键：

```json
{
  "resources": {"金魂币": -5, "银魂币": 3},
  "stats": {"魂力": 2},
  "affection": {"唐三": 3},
  "location": "索托城", "date": "第3年6月", "month_delta": 0,
  "inventory_add": [], "inventory_remove": [],
  "notes_add": [],
  "soul_ring_add": {"years": 423, "beast": "...", "skill": "...", "attribute": "..."}   // 仅当世界启用 rings
}
```

**兼容层**：`validate_delta` 同时接受斗罗旧键，映射到通用路径后再校验钳制——
- `gold/silver/copper` → `resources` 的 金魂币/银魂币/铜魂币
- `soul_level` → `stats` 的 魂力
- `soul_ring_add` 校验/落账规则取自 `world.state_template.rings`（无 rings 则忽略）

**决策**：斗罗规则书 [system_prompt.txt](../../../backend/prompts/system_prompt.txt) 的输出契约**暂不重写**，继续吐旧键（最小爆炸半径，现有 66 测试大部分不动）；自建世界的规则书（由建世界提示词生成）吐通用键。后续可单开任务把斗罗迁移到通用键。

### 3.3 创建向导

- 斗罗（`world.id == "douluo"`）：继续用现有 5 步 `CreationWizard.vue`（出身→执念秘密→特质→武魂天赋→财富），不重写。
- 自建世界：新增**通用动态向导**组件，按 `creation_schema` 渲染字段：

```json
{
  "steps": [
    {"step": "身份", "fields": [
      {"key": "identity", "label": "你的身份", "type": "select",
       "options": ["穿越者", "原著角色", "原创角色", "自定义"], "required": true},
      {"key": "identityNote", "label": "具体身份", "type": "text", "required": false}
    ]},
    {"step": "背景", "fields": [...]}
  ]
}
```

  字段类型：`text` / `number` / `select` / `multiselect` / `textarea`。玩家填完产出 `archive`，走与斗罗相同的 `new-game` → 开场叙述 → 游戏循环。开场消息里把 `archive` 以 JSON 形式交给 AI（与现状一致），由该世界规则书决定如何解读。

## 4. 上传小说 → 建世界流水线

```
玩家点击「上传小说创建世界」
   │  ① 填写/校验自己的 DeepSeek Key（缺失/无效 → 拦截，不进入构建）
   ▼
POST /api/worlds/build  (multipart: file + api_key + client_id)
   │  ② 解析：TXT 编码探测（utf-8 / gb18030 / gbk 兜底）；DOCX 用 python-docx 抽文本；.doc 拒绝并提示另存为
   │  ③ 文本清洗：去 BOM、控制字符、压缩连续空行；≤10MB
   │  ④ 抽样精读：总长 ≤4万字 直接用（截断到上限）；
   │        更大 → 开头≈1.5万字 + 结尾≈1万字 + 中间随机数段，拼 ≈3.5万字
   │        抽样种子 = sha256(文件内容)  → 同一文件每次抽样一致（可测/可复现）
   ▼
DeepSeek（玩家 Key）按「世界观建构师」提示词
   │  产出 JSON：{name, desc, rulebook, state_template, creation_schema}
   │  规则：产出"结构化的世界框架"，禁止逐字复制原文；规则书复刻斗罗规则书结构
   │        （世界地图→核心机制→创建选项→输出契约），文本总量控制 ≤ 约 8K token
   ▼
校验产物：规则书非空、模板键合法、类型正确；失败自动重试 1 次，再失败给友好中文提示
   ▼
落盘 data/worlds/<id>.json（kind=custom, owner=client_id, created_at）
   ▼
返回世界摘要给作者；作者的世界列表刷新
```

- 全程用玩家 Key，站点零成本；玩家 Key 无效/额度不足时给 `_friendly_err` 同款友好中文提示。
- 构建期间前端显示进度（解析中→生成中），单次构建典型耗时几十秒。

## 5. 可见性与权限

- **自建世界仅作者可见**：`/api/worlds` 只返回 builtin 世界 + `owner == 请求 client_id` 的自建世界。不做分享码、不做公开广场、不做世界市场。
- 权限校验：`/api/worlds/<id>` 详情、以及用自定义世界开局的请求，均校验 `world.owner == client_id` 或 `kind == builtin`，否则 404。
- 玩家各自的世界是独立会话，互不共享状态。

## 6. 前端改造

- **首页 → 世界广场**：官方世界区（卡片：斗罗大陆 + 未来更多）+ 我的世界区（仅自己创建）+「上传小说创建世界」按钮（含 Key 输入与文件选择）。
- 选世界 → 斗罗走现有向导 / 自建走通用动态向导 → 档案卡 → 同一 GameView。
- 站点标题/文案改为平台名（**工作名：「万界人生模拟器」，待用户定**，全局替换即可改）。
- 订阅门禁、自由度档位、BYOK、后悔/存档等现有功能对自定义世界同样生效（`/api/act` 等请求透传 `world_id`）。
- 新增 `POST /api/worlds/build` 的进度提示与错误处理（复用现有 postSse/postJson 风格）。

## 7. 成本与安全

- 建世界必须玩家自己的 Key（硬门槛，未填/无效拦截），站点零成本。
- 上传限制：仅 `.txt` / `.docx`，≤10MB；`.doc` 拒绝。
- 构建提示词要求"结构化框架、不逐字复刻原文"，降低版权文本直接再现风险（站点面向个人轻量收费，版权边界以用户自担为准）。
- 构建用玩家 Key 调用 DeepSeek，**不留存原文**：只存生成的世界规格（规则书+模板+创建字段），不存小说全文。
- 限流：单 client 建世界频率限制（如 5 次/小时），防脚本轰炸（构建由玩家 Key 计费，但存储/IO 仍是站点资源）。

## 8. 兼容与迁移

- `world_id` 缺省 = `douluo`：旧存档（`meta.session_id` 无 world 标记）冷启动回落斗罗，旧 `/api/new-game` 请求体不带 `world_id` 照常走斗罗。
- 会话磁盘结构：session 目录新增 `world.json`（记录 world_id），`sm.load_state` 兼容无此文件（默认 douluo）。
- 现有测试：`default_state(archive)` / `apply_delta(state, delta)` 保留无 world 参数的向后兼容签名（内部默认加载斗罗规格）；访问 `state["resources"]["gold"]` 等旧字段路径的断言改为通用路径（`resources["金魂币"]`），或保留薄兼容访问器——以实际 diff 为准，测试套件是行为的权威文档。
- 66 现有测试目标：改后全绿；行为（魂环年限上限、好感衰减、后悔、门禁、凭证）由斗罗规格复现，不回归。

## 9. 部署与存储

- 世界规格存 `data/worlds/*.json`（builtin 斗罗规格随仓库入库；自建世界文件 gitignore）。
- **Render 免费实例磁盘临时**：自建世界在重部署后丢失（与存档/激活登记表同一已知限制）。README 明确说明；预留 `WORLDS_DIR` 环境变量可指向持久化磁盘/挂载（Render 付费实例或将来数据库）。
- 备份手段：作者可导出/导入世界 JSON 的接口留作将来选项，本期不做。

## 10. 测试策略

新增/调整：
- 世界规格：加载/解析/校验（缺字段、类型错误、非法模板键）。
- 抽样算法：确定性（同文件同样本）、边界（≤4万字、超长、空文本）。
- 上传解析：txt 各编码、docx、.doc 拒绝、超大小拒绝。
- 建世界流水线：mock DeepSeek 成功/畸形 JSON/重试/玩家 Key 无效。
- 通用状态：resources/stats 钳制、动态好感添加与衰减、无 rings 世界忽略 soul_ring_add、斗罗旧键兼容映射。
- 通用提示词：规则书取自身、状态摘要按模板渲染。
- 权限：非作者访问自建世界 404；builtin 对所有人可见。
- 回归：现有 66 测试全绿。

## 11. 明确不做（YAGNI）

- 不做分享/公开广场/世界市场。
- 不做世界审核/举报系统。
- 不做多人/联机。
- 不迁移斗罗规则书到通用键（另开任务）。
- 不做世界导出/导入（本期）。

## 12. 未决事项

- 平台名（工作名「万界人生模拟器」，待定）。
- 构建提示词的中文输出契约细节（随实现打磨，写入实现计划）。
