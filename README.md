# 万界人生模拟器

AI 驱动的沉浸式文字 RPG 网页平台，容纳众多模拟世界。内置两位创作者出品的官方原创世界：
- **「魂兽大陆」**：魂师与魂兽共存、各有际遇——你可以扮演穿越者、重生者或土著，从出身、秘密、特质到武魂天赋，逐步塑造属于自己的人生。
- **「万物生」**：灵气复苏·现代都市文字 RPG——复苏日后灵气突破临界、万物生灵，你从一名普通人觉醒超凡之力，踏上吞噬万物、逆行增熵的守门人之路。
- **「隔壁的租客」**：现代都市慢热甜文 RPG——老城区顶楼的小次卧，对门住着作息诡秘的沈砚，心动藏在生锈的门把手、一锅多盛的粥与窗台上排成两排的石头里。

故事的每一步由 DeepSeek 大模型实时生成，并通过流式叙述呈现。平台同时支持玩家上传小说自建专属世界（仅本人可见），详见下方"多世界平台"。

## 功能

- **角色创建向导**：出身 · 执念秘密 · 特质 · 天赋档与武魂 · 财富，五步定制后生成角色档案卡
- **AI 世界引擎**：两阶段调用——先流式生成叙述（文风符合规则书），再结算状态变动
- **状态权威在后端**：金币 / 魂力 / 好感度 / 魂环 / 位置 / 日期等状态由 FastAPI 全权持有，AI 只提交增量，后端校验钳制后落账
- **好感度系统**：与主要角色互动积累好感，久不联系会缓慢衰减
- **魂环机制**：按年限上限依次解锁（423 / 764 / 1760 / 5000 / 12000 / 20000 / 50000 / 80000 / 100000 年）
- **存档 / 读档**：JSON 存档 + 每回合存档点，随时继续游戏
- **回合记录不丢**：每回合叙述生成完自动存档为完整记录，滚动回放全程，新回合不再覆盖旧文字
- **后悔（回合回退）**：每次选项生成后多一个"后悔"，点选即可退回上一回合——状态、选项、叙述全部还原，可连续后悔，最多 20 层
- **导出剧情**：在存档/读档面板点「📖 导出」，把这段旅程一路生成的所有叙述正文整理成 Markdown 小说下载——通关或想留纪念时，就是自己在这个世界亲身经历的故事集（只含 AI 叙述正文，不含选项与数值）
- **真流式叙述**：DeepSeek 边生成、边推给前端，约 2 秒出现第一个字，叙述在打字机渲染中实时生长
- **生成不跳页**：当前回合叙述在原位生成→完成，不做 DOM 重建；只有停在页面底部附近时才自动跟随滚动，向上翻阅历史绝不被打断
- **自由度（叙述篇幅档位）**：右上角常驻小按钮，随时切换五个档位——精炼 200 字 / 简洁 500 字 / 标准 1000 字 / 详尽 1500 字 / 极尽 2000 字，点击按钮可查看功能说明；档位越高文字越长、生成越慢，选择随浏览器记住
- **限长保速**：叙述/结算都有 token 上限，档位越高上限越高，单回合稳定在数秒内完成，不随剧情膨胀失控
- **订阅门禁（1元/月）**：微信扫码支付 1 元后找站长领**当天的激活码**，随机英文码、存服务器码池（一个码对应一年中的一天、每年循环，只有当天能激活），激活后 30 天无限游玩；未激活可免费试玩 5 回合；右上/首页随时可输入激活码，激活结果本机长期有效

## 多世界平台

- **世界广场**：首页即世界广场，展示创作者已开发的世界（魂兽大陆 · 隔壁的租客 · 万物生）与你自建的世界
- **新增内置世界需重启**：内置世界以 JSON 文件形式放在 `backend/worlds/`（广场排序按文件名），但服务端对世界规格有缓存——**新增/修改内置世界文件后需重启后端**，广场才会显示新世界
- **上传小说自建世界**：上传 TXT / Word 小说，DeepSeek 抽样精读后自动生成该世界的框架（规则、出身、初始状态、创建向导字段），成为专属世界
- **仅本人可见**：自建世界只对创建者本人显示，他人看不到也玩不到
- **BYOK 零成本**：自建世界使用玩家自己的 DeepSeek API Key 生成与游玩，站点不为此承担任何模型费用
- **内部标识不变**：魂兽大陆的内置世界 id 仍为 `douluo`，旧存档无缝兼容

## 架构

```
┌─────────────┐   SSE (text/delta/done)   ┌──────────────┐   HTTPS    ┌────────────┐
│ Vue 3 前端   │ ───────────────────────► │ FastAPI 后端  │ ────────► │ DeepSeek   │
│ Vite + Tail │ ◄─────────────────────── │ 状态账本+引擎  │ ◄──────── │ deepseek-  │
│ 打字机渲染    │                          │ (权威状态)     │           │ chat       │
└─────────────┘                          └──────────────┘           └────────────┘
        ▲                                       │
        │                                       ▼
   vite proxy /api → :8000              data/saves/<session>/  (state.json,
        │                                        history.jsonl, savepoints/)
        └────── 浏览器（localhost:5173）
```

- 后端是**唯一权威状态**。每次回合：① 流式叙述（temperature 0.85）→ ② 结算 JSON（temperature 0.3，强制 JSON 输出）→ ③ `apply_delta` 校验并落账。
- 状态增量使用固定英文 key：`gold / silver / copper / soul_level / affection / location / date / month_delta / inventory_add / inventory_remove / notes_add / soul_ring_add`，越权或非法的增量会被后端钳制。

## 目录结构

```
backend/
  main.py                 FastAPI 路由（health/saves/new-game/act/resume/save/load/delete/activate/entitlement）+ SSE + 订阅门禁
  generate_code.py        查看/补全激活码池（首次补齐全年 366 个码，之后只查不改；随仓库提交）
  game/
    state_schema.py       状态默认值、增量校验、魂环年限上限、好感角色
    game_engine.py        落账引擎（月份推进、好感衰减、增量钳制）
    save_manager.py       JSON 存档 / 读档 / 存档点 / 订阅登记表(activations.json)
    prompt_builder.py     规则书系统提示 + 两阶段消息组装
  prompts/
    system_prompt.txt     完整规则书 + 输出契约
  data/                   运行时数据（存档 / 订阅登记表不入库；激活码池 activation_codes.json 随部署提交）
  tests/                  143 个单元测试（pytest，含"后悔"、自由度、订阅门禁、多世界/建世界、剧情导出用例）
  requirements.txt
  .env.example
frontend/
  src/
    api.js                fetch SSE 解析 + API 封装（含 activate/entitlement）
    store.js              响应式全局状态（game / ui / entitlement / clientId）
    App.vue               视图路由（home/create/review/game）+ 订阅激活弹窗
    views/                HomeView · GameView
    components/           创建向导 / 档案卡 / 叙述流 / 选项栏 / 状态栏 / 存档面板 / 激活弹窗
  vite.config.js          开发代理 /api → 127.0.0.1:8000
  package.json
```

## 快速开始

### 0. 前置

- Python 3.10+
- [bun](https://bun.sh)（或 npm）

### 1. 后端

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash
pip install -r requirements.txt

# 配置 DeepSeek API Key
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY=sk-...

uvicorn main:app --port 8000
```

### 2. 前端

```bash
cd frontend
bun install        # 或 npm install
bun run dev        # 或 npm run dev → http://localhost:5173
```

打开 http://localhost:5173 开始游戏。开发模式下 `/api` 由 vite 自动代理到 `:8000`。

## API

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/health` | GET | 健康检查 |
| `/api/saves` | GET | 存档列表 |
| `/api/new-game` | POST | 开始新游戏，SSE 流式返回开场叙述（body 可带 `freedom` 1-5，默认 3） |
| `/api/act` | POST | 提交行动，SSE 流式返回新叙述（body 可带 `freedom` 1-5，默认 3） |
| `/api/resume` | POST | 继续游戏（返回状态 + 回合记录 + 选项，不调 AI） |
| `/api/undo` | POST | "后悔"：退回上一回合（还原状态/选项/回合记录，不调 AI） |
| `/api/save` | POST | 保存当前进度（存档点） |
| `/api/load` | POST | 加载指定存档点 |
| `/api/delete` | POST | 删除会话 |
| `/api/export` | POST | 导出剧情（body: `session_id`）：把该会话的叙述历史整理成 Markdown 小说文本（`{title, content, filename, turns, chars}`），前端下载 .md 文件 |
| `/api/activate` | POST | 输入当天激活码激活订阅（body: `code` + `client_id`）；按服务器码池校验，非当天/无效码返回 400 |
| `/api/entitlement` | POST | 查询订阅/免费试玩状态（body: `client_id`，可带 `code` 做无状态校验） |

SSE 事件：`event: text`（叙述片段）→ `event: delta`（`{state, options, notes, event, can_undo}`）→ `event: done`。`can_undo` 为 true 时前端显示"后悔"选项。

`/api/new-game` 与 `/api/act` 的请求体均可携带 `freedom`（1-5），缺省 3（标准 1000 字）。档位决定叙述目标字数与 `max_tokens`，并在提示词中显式覆盖规则书的固定字数限制。

这两个端点在未订阅且免费试玩用尽时返回 `403`（`detail` 含"免费试玩/订阅/激活"，前端据此自动弹出激活面板）。请求体可携带 `client_id`（浏览器 localStorage 的持久身份）与 `code`（本机保存的激活码，后端按服务器码池校验）；未携带视为未激活。

## 测试

```bash
cd backend
pytest -q
# 143 passed
```

## BYOK：玩家自带 API Key

担心朋友玩你的部署版消耗你的 API 额度？创建角色第一步新增了可选的 **DeepSeek API Key** 输入框：

- 填了自己的 Key → 该玩家的每轮 AI 调用都用 **他自己的 Key** 计费，不碰站点额度
- 不填 → 回落使用站点配置的 `DEEPSEEK_API_KEY`
- Key 只存在**玩家自己浏览器**的 localStorage，随请求单独发送，**不会写进存档、不会进提示词、服务端不落盘**
- 填错 Key 会得到明确中文提示（无效/额度不足），而不是不明不白的报错

> 想强制每位玩家都用自己的 Key？部署时不配置 `DEEPSEEK_API_KEY` 环境变量即可 —— 没填 Key 的玩家会被引导填写。

## 订阅收款（微信收款码 · 服务器端码池 · 每年循环）

想用这个项目收 1元/月 的订阅费？内置一套**免登录、免数据库**的激活机制：激活码由站长一次性生成一年（366 个码，含闰日），随机英文码、存在服务器码池里，**不需要任何人去算，输入即用**。

1. **收款**：微信收款码已放在 `frontend/src/assets/wechat-pay-qr.jpg`，前端激活面板会自动展示。以后换了新收款码，用新图片替换同名文件即可。玩家扫码支付 1 元后，会通过微信的「联系收款方」向你要激活码——你确认收款后，把**当天**的激活码回复给该玩家即可。
2. **生成码池**（管理员本机运行，只需做一次）：**Windows 双击 `backend/发激活码.bat`** 最省心；或开终端 `python generate_code.py`。首次运行自动补齐全年 366 天（含闰日 02-29）的码并写入 `backend/data/activation_codes.json`，随机 12 位英文码（`XXXX-XXXX-XXXX`）；之后再运行只查看，**不会改掉已发出的码**。
3. **按天发码 · 每年循环**：一个码对应一年中的一个日子（`月-日`），当天所有顾客用同一个码即可。8 月 10 号的码只有 8 月 10 号当天能激活；而且**每年循环**——2026 年 8 月 10 号的码，2027、2028 年 8 月 10 号永远能用，**不需要每年重新生成**。码存在服务器底层逻辑里，随机不可伪造，无需人算。
4. **玩家流程**：未激活可免费试玩 5 回合 → 玩完被门禁提示 → 微信扫码支付 1 元 → 在支付记录里点「联系收款方」向收款方要激活码 → 在首页或游戏内点"💳 订阅 / 激活码"输入**当天的码** → 立即解锁 30 天（从今天起 30 天）；到期后再领新码**顺延**。

**激活规则**：每个激活码只对应一年中的一天、只有当天能激活（"今天"以服务器系统时间为准）。激活成功后到期日写进本机订阅登记（`backend/data/activations.json`），之后 30 天一直有效，即使那天已过。同一天内换设备/换浏览器，重新输入同一个码即可恢复；过了当天，新设备请领当天的新码。

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `FREE_TRIAL_TURNS` | `5` | 未激活可免费试玩的回合数（`0` = 纯付费） |

> **⚠️ 局限（务必了解）**
> - **码必须当天激活**：激活码只在它对应的那天能激活，过了那天只能等明年同一天（码每年循环，不会消失）。所以请当天发码、顾客当天输入。
> - **激活码可以转发**：拿到码的人当天就能激活 30 天。码按天发，一人一天一个即可；请提醒玩家勿转发。
> - 本机制按"浏览器 localStorage 身份"记账**免费试玩次数**，**不绑定账号**：会折腾的玩家清一下浏览器数据就能再领 5 回合试玩。对 1元/月 的轻量收费这是可接受的取舍；要硬墙请接入账号系统 + 数据库。
> - **部署在 Render 免费套餐时磁盘是临时的**：服务重启/重新部署后 `backend/data/` 的**订阅登记与试玩次数**会丢失（激活码池在仓库里、不会丢）。玩家重新输入激活码即可恢复订阅。免费存档的丢失风险见"部署到 Render"一节。
> - **码池随仓库提交、随镜像上线**：`data/activation_codes.json` 进 Git 仓库，且 `.dockerignore` 已放行（`data/` 其余内容仍不进镜像）——Docker/Render 部署会自动带上全部码。**仓库务必设为私有**——若是公开仓库，任何人都能读到全部码。

## 部署到 Render（在线网站）

仓库根目录已包含 `render.yaml`（Blueprint）与 `Dockerfile`，可一键部署为单服务：

1. 把项目推到 GitHub（`render.yaml` 在仓库根目录）
2. 登录 [Render](https://render.com) → **New → Blueprint Instance** → 选择本仓库
3. Render 读取 `render.yaml`，构建 `Dockerfile`（阶段1 用 Node 构建前端 → 阶段2 Python 运行时同源托管）
4. 首次部署会提示设置 `DEEPSEEK_API_KEY`（你的 DeepSeek API Key）
5. 部署完成后访问 `https://<服务名>.onrender.com` 即可游玩

架构：单个 Web 服务同源提供「前端静态文件 + `/api` 接口」，无需 CORS/代理。

> **注意（免费套餐）**：Render 免费实例磁盘是临时的，服务重启后存档（`backend/data/`）会丢失。想长期保存请升级实例或后续接入数据库存储。

## 环境变量

| 变量 | 说明 |
|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek API Key（必填） |
| `FREE_TRIAL_TURNS` | 未激活免费试玩回合数（默认 5，`0` = 纯付费） |

> `.env` 已被 `.gitignore` 忽略，不会入库。真实 key 请勿提交。

## 技术栈

FastAPI · uvicorn · openai (DeepSeek 兼容) · SSE · Vue 3 · Vite · Tailwind CSS · markdown-it · bun
