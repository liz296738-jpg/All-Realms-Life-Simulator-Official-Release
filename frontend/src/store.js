import { reactive, readonly } from 'vue'
import { renderMd, stripOptionsBlock } from './md'
import { api } from './api'

// ═══════════════════════════════════════════════════════════════
//  私有状态（仅允许通过下方导出的 Actions 修改）
// ═══════════════════════════════════════════════════════════════

const _game = reactive({
  sessionId: null,
  state: null,        // 后端权威 state（character/rings/resources/affection...）
  narrative: '',      // 当前回合叙述（流式生长 → 完成后保留在原位）
  streaming: false,   // 是否正在流式输出
  options: [],        // 当前回合选项 [{label, text}]
  notes: [],          // 当前回合笔记（delta 设置，归档时随回合记录保存）
  event: '',          // 当前回合事件
  lastChoice: null,   // 当前回合由哪个选项发起
  turns: [],          // 已归档的过往回合 [{narrative, html, options, notes, event, choice}]
  canUndo: false,     // 是否可"后悔"（回到上一回合）
  error: '',          // 上次失败的提示（渲染在叙述流顶部）
  turnDone: false,    // 本轮是否可操作
  turnCommitted: false, // 后端已确认本回合落账（收到 delta/恢复时置 true，提交时置 false）
})

const _ui = reactive({
  view: 'home',       // home | create | review | game
  showStatus: false,  // 状态栏展开
  showSave: false,    // 存档面板
  showCharacter: false,  // 角色设定面板
  busy: false,
  activationOpen: false,   // 订阅/激活弹窗
  activationMsg: '',       // 触发弹窗的原因提示（门禁 403 时的说明）
})

const _worlds = reactive({
  builtin: [],
  mine: [],
  selected: null,    // 当前选中的世界（创建/开局用）
  loading: false,
})

const _entitlement = reactive({
  paid: false,            // 是否在激活期内
  paidUntil: '',          // 订阅到期日（iso）
  trialUsed: 0,           // 已消耗免费试玩回合
  trialLimit: 5,          // 免费试玩总回合（后端下发的实际值）
  subscriptionCode: '',   // 激活码（领到后在对应日起 30 天内激活即可）
  loading: false,
})

const _draft = reactive({
  identity: '',          // 穿越者/正典重生/原创/自定义
  identityNote: '',      // 具体身份细节（穿越成谁/重生谁/自定义描述）
  name: '', gender: '男', age: 12, origin: '云溪镇',
  background: '', family: '', secret: '',
  traits: '', personality: '', desire: 5,
  talentTier: '', innateSoulPower: null,
  wuhun: '', wuhunType: '器武魂', developmentDirection: '强攻系',
  specialItems: [],
  direction: '自由/综合向', timelineBinding: '半绑定',
  gold: '',             // 初始金魂币（玩家显式填写，优先级高于出身默认值）
  // BYOK：玩家自带 DeepSeek Key，仅存本浏览器，随请求单独发送（不进存档/提示词）
  apiKey: localStorage.getItem('douluo_api_key') || '',
  // 自由度档位 1-5：控制每回合叙述字数（200~2000），随每次生成请求下发
  freedom: Number(localStorage.getItem('douluo_freedom')) || 3,
})

// ═══════════════════════════════════════════════════════════════
//  只读视图（组件只允许读，不允许直接写）
// ═══════════════════════════════════════════════════════════════

export const game = readonly(_game)
export const ui = readonly(_ui)
export const worlds = readonly(_worlds)
export const entitlement = readonly(_entitlement)
export const draft = readonly(_draft)

// ═══════════════════════════════════════════════════════════════
//  Actions — game（叙述 / 流式 / 回合流转 / 错误处理）
// ═══════════════════════════════════════════════════════════════

export function setStreaming(isStreaming) {
  _game.streaming = !!isStreaming
}

export function clearNarrative() {
  _game.narrative = ''
}

export function appendNarrative(text) {
  if (text) _game.narrative += text
}

export function setOptions(options) {
  _game.options = Array.isArray(options) ? options : []
}

export function setTurnCommitted(isCommitted) {
  _game.turnCommitted = !!isCommitted
}

export function setTurnDone(isDone) {
  _game.turnDone = !!isDone
}

export function setError(errorMsg) {
  _game.error = errorMsg || ''
}

export function setCanUndo(can) {
  _game.canUndo = !!can
}

export function setTurns(turns) {
  _game.turns = Array.isArray(turns) ? turns : []
}

export function setNotes(notes) {
  _game.notes = Array.isArray(notes) ? notes : []
}

export function setEvent(event) {
  _game.event = event || ''
}

export function setLastChoice(choice) {
  _game.lastChoice = choice || null
}

export function setSessionId(id) {
  _game.sessionId = id || null
}

/** 后端权威状态覆盖（delta / resume / undo 场景）。 */
export function setGameState(state) {
  _game.state = state
  if (state?.meta?.session_id) _game.sessionId = state.meta.session_id
}

/** 重置游戏态（新开局 / 加载出错恢复）。不清 turns——由 commitTurn 或上游接管。 */
export function resetGameState() {
  _game.sessionId = null
  _game.state = null
  _game.narrative = ''
  _game.streaming = false
  _game.options = []
  _game.notes = []
  _game.event = ''
  _game.lastChoice = null
  _game.turns = []
  _game.canUndo = false
  _game.error = ''
  _game.turnDone = false
  _game.turnCommitted = false
}

/** 归档一个回合：把已完成回合压进 turns，并清空当前回合区。
 *  在【新回合开始前】调用（submit），而不是 delta 时——这样当前回合的 DOM 全程
 *  不重建，生成/完成切换不产生页面跳动。 */
export function commitTurn({ narrative, options, notes, event, choice }) {
  _game.turns.push({
    narrative,
    options: options || [],
    notes: notes || [],
    event: event || '',
    choice: choice || null,
    html: renderMd(stripOptionsBlock(narrative)),
  })
  _game.narrative = ''
  _game.notes = []
  _game.event = ''
  _game.lastChoice = null
  _game.turnCommitted = false
}

// ═══════════════════════════════════════════════════════════════
//  Actions — ui（视图切换 / 面板控制）
// ═══════════════════════════════════════════════════════════════

const VALID_VIEWS = new Set(['home', 'create', 'review', 'game'])

export function setUiView(viewName) {
  if (VALID_VIEWS.has(viewName)) _ui.view = viewName
}

const VALID_PANELS = new Set(['showStatus', 'showSave', 'showCharacter', 'activationOpen', 'busy'])

export function togglePanel(panelName, isOpen) {
  if (VALID_PANELS.has(panelName)) _ui[panelName] = !!isOpen
}

export function setBusy(isBusy) {
  _ui.busy = !!isBusy
}

export function setActivationOpen(isOpen, msg) {
  _ui.activationOpen = !!isOpen
  _ui.activationMsg = msg || ''
}

// ═══════════════════════════════════════════════════════════════
//  Actions — worlds
// ═══════════════════════════════════════════════════════════════

export async function loadWorlds() {
  _worlds.loading = true
  try {
    const d = await api.worlds(clientId())
    _worlds.builtin = d.builtin || []
    _worlds.mine = d.mine || []
  } catch { /* 后端未启动等场景静默 */ } finally { _worlds.loading = false }
}

export function selectWorld(w) {
  _worlds.selected = w
}

// ═══════════════════════════════════════════════════════════════
//  常量 / 纯工具函数
// ═══════════════════════════════════════════════════════════════

export const SITE_NAME = '万界人生模拟器'
export const DEFAULT_WUHUN = '白灵藤'

/** 世界名：优先取会话状态 meta.world_name，兜底显示平台名。 */
export function worldName(state) {
  if (state?.meta?.world_name) return state.meta.world_name
  if (_worlds.selected) return _worlds.selected.name
  return SITE_NAME
}

// ── 浏览器身份 ──────────────────────────────────────────

/** 浏览器身份：localStorage 持久化，服务端按此判定订阅激活状态。 */
export function clientId() {
  let id = localStorage.getItem('douluo_client_id')
  if (!id) {
    id = 'c' + (crypto?.randomUUID
      ? crypto.randomUUID().replace(/-/g, '')
      : Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2))
    localStorage.setItem('douluo_client_id', id)
  }
  return id
}

// ── 订阅 / 免费试玩 ─────────────────────────────────────

export function getSubscriptionCode() {
  return localStorage.getItem('douluo_sub_code') || ''
}

export function setSubscriptionCode(code) {
  const v = (code || '').trim()
  _entitlement.subscriptionCode = v
  if (v) localStorage.setItem('douluo_sub_code', v)
  else localStorage.removeItem('douluo_sub_code')
}

export async function refreshEntitlement() {
  _entitlement.loading = true
  try {
    const d = await api.entitlement({ client_id: clientId(), code: getSubscriptionCode() })
    _entitlement.paid = !!d.paid
    _entitlement.paidUntil = d.paid_until || ''
    _entitlement.trialUsed = d.trial_used || 0
    _entitlement.trialLimit = d.trial_limit
    _entitlement.subscriptionCode = getSubscriptionCode()
  } catch { /* 后端未启动等场景静默 */ } finally { _entitlement.loading = false }
}

export function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d)) return ''
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
}

/** 激活成功后乐观更新订阅状态（供 ActivationPanel 使用）。 */
export function markEntitlement({ paid, paidUntil, trialUsed }) {
  if (paid !== undefined) _entitlement.paid = !!paid
  if (paidUntil !== undefined) _entitlement.paidUntil = paidUntil || ''
  if (trialUsed !== undefined) _entitlement.trialUsed = trialUsed
}

/** 门禁 403 的提示是否来自订阅/试玩（是则前端应弹出激活面板而非普通 alert）。 */
export function isGateError(e) {
  return /(激活|订阅|试玩)/.test(String((e && e.message) || ''))
}

// ── 创建向导草稿 ────────────────────────────────────────

export function saveApiKey(k) {
  _draft.apiKey = k
  localStorage.setItem('douluo_api_key', k)
}

export function setFreedom(v) {
  _draft.freedom = v
  localStorage.setItem('douluo_freedom', String(v))
}

/** 通用草稿字段更新（供 CreationWizard / GenericWizard 的 v-model 平替）。 */
export function updateDraft(key, value) {
  if (key in _draft) _draft[key] = value
}

/** 增量更新 game.state.npcs[name] 的子字段（供 CharacterPanel 使用）。 */
export function patchNpcState(name, update) {
  const npcs = _game.state?.npcs
  if (npcs) {
    if (!npcs[name]) npcs[name] = {}
    Object.assign(npcs[name], update)
  }
}
