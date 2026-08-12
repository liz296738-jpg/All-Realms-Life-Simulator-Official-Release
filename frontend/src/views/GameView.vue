<script setup>
import { computed } from 'vue'
import {
  game, ui, draft,
  commitTurn, clientId, getSubscriptionCode, isGateError, worldName,
  setGameState, setStreaming, setTurnDone, setTurnCommitted,
  clearNarrative, appendNarrative, setOptions, setNotes, setEvent,
  setLastChoice, setCanUndo, setError, setTurns,
  setActivationOpen, togglePanel,
} from '../store'
import { postSse, api } from '../api'
import { renderMd, stripOptionsBlock } from '../md'
import NarrativeStream from '../components/NarrativeStream.vue'
import OptionsBar from '../components/OptionsBar.vue'
import StatusPanel from '../components/StatusPanel.vue'
import SavePanel from '../components/SavePanel.vue'
import CharacterPanel from '../components/CharacterPanel.vue'

// ── 动态等级字段（零硬编码） ──
const levelField = computed(() => game.state?.meta?.level_field || '')
const levelValue = computed(() => {
  const lf = levelField.value
  const ch = game.state?.character
  if (!lf || !ch) return null
  return ch[lf]
})
const headerLevel = computed(() => {
  const lv = levelValue.value
  if (lv != null && lv !== '') return `${lv}`
  return null
})

// 后端返回的 turns 不含渲染后的 html，此处补齐（剥掉 AI 自带的选项块，与当前回合显示一致）
function hydrateTurns(turns) {
  return (turns || []).map(t => ({ ...t, html: renderMd(stripOptionsBlock(t.narrative)) }))
}

// 后端 turns 末尾是"当前回合"，前段才是已归档的过往回合（resume/undo 恢复显示用）
function splitTurns(bt) {
  const archived = hydrateTurns(bt.slice(0, -1))
  const cur = bt[bt.length - 1] || null
  return { archived, cur }
}

/** 覆盖当前回合叙述（先清空再追加，等效于直接赋值：仅组件只读后禁止直接 game.narrative = 必须走 action）。 */
function setNarrative(text) {
  clearNarrative()
  if (text) appendNarrative(text)
}

function submit(action) {
  if (game.streaming || !game.sessionId) return
  // 在【新回合开始前】归档上一回合：叙述不丢，且当前回合 DOM 全程不重建（防页面跳动）。
  // 只有后端确认过落账（turnCommitted）的回合才归档——失败/中断的残篇不归档，避免前后端回合列表分叉。
  if (game.turnCommitted && game.narrative.trim()) {
    commitTurn({ narrative: game.narrative, options: game.options, notes: game.notes, event: game.event, choice: game.lastChoice })
  }
  setLastChoice(action)
  setStreaming(true)
  setTurnDone(false)
  setTurnCommitted(false) // 等后端 delta 确认后才可归档
  clearNarrative()
  setOptions([])
  setNotes([])   // 清除上一回合残留，防止失败后带着旧 event/notes 归档
  setEvent('')
  setError('')

  postSse('/api/act', {
    session_id: game.sessionId, action,
    api_key: draft.apiKey?.trim() || null,
    freedom: draft.freedom,
    client_id: clientId(),
    code: getSubscriptionCode() || null,
  }, {
    onText: (t) => { appendNarrative(t) },
    onDelta: (d) => {
      setGameState(d.state)
      setOptions(d.options || [])
      setNotes(d.notes || [])
      setEvent(d.event || '')
      setCanUndo(!!d.can_undo)
      setTurnCommitted(true) // 后端已把本回合写入 turns/历史
    },
    onDone: () => { setStreaming(false); setTurnDone(true) },
  }).catch((e) => {
    setStreaming(false)
    setTurnDone(true)
    setError(e.message)
    if (isGateError(e)) setActivationOpen(true, e.message)
    else alert(e.message)
  })
}

// "后悔"：退回上一回合，状态/选项/叙述全部还原（后端不调 AI，即时返回）。
// 复用 streaming 锁防止双击并发（否则两个在途 undo 各弹一层，一次点击退回两回合）。
async function undo() {
  if (game.streaming || !game.sessionId || !game.canUndo) return
  setStreaming(true)
  setTurnDone(false)
  try {
    const d = await api.undo(game.sessionId)
    const { archived, cur } = splitTurns(d.turns)
    setGameState(d.state)
    setTurns(archived)
    setNarrative(cur ? cur.narrative : '')
    setLastChoice(cur ? (cur.choice || null) : null)
    setOptions(d.options || [])
    setNotes(cur ? (cur.notes || []) : [])
    setEvent(cur ? (cur.event || '') : '')
    setCanUndo(!!d.can_undo)
    setError('')
    setTurnCommitted(true) // 恢复出的当前回合是完整已落账回合，可再次提交
  } catch (e) {
    setError(e.message)
    alert(e.message)
  } finally {
    setStreaming(false)
    setTurnDone(true)
  }
}

function onResume(payload) {
  const { archived, cur } = splitTurns(payload.turns)
  setGameState(payload.state)
  setTurns(archived)
  setNarrative(cur ? cur.narrative : '')
  setLastChoice(cur ? (cur.choice || null) : null)
  setOptions(payload.options || [])
  setNotes(cur ? (cur.notes || []) : [])
  setEvent(cur ? (cur.event || '') : '')
  setCanUndo(!!payload.canUndo)
  setError('')
  setTurnCommitted(true) // 恢复出的当前回合是完整回合
  setTurnDone(true)
  setStreaming(false)
}
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- 顶栏（右侧留出右上角常驻的自由度按钮位置） -->
    <!-- pr-40：为右上角常驻的自由度按钮（约130px）预留空间 -->
    <header class="flex items-center justify-between px-4 py-2 border-b border-stone-800 bg-stone-950/80 pr-40">
      <button @click="togglePanel('showSave', true)" class="text-sm text-stone-400 hover:text-amber-300">💾 存档/读档</button>
      <h1 class="text-sm text-stone-300 tracking-widest">{{ worldName(game.state) }}</h1>
      <span class="text-sm text-stone-500 w-20 text-right">
        <template v-if="headerLevel">{{ headerLevel }}</template>
        <template v-else>第{{ game.state?.meta?.turn ?? '—' }}回合</template>
      </span>
    </header>

    <!-- 叙事流 -->
    <NarrativeStream />

    <!-- 选项与输入 -->
    <OptionsBar @choose="submit" @undo="undo" />

    <!-- 折叠状态栏 + 角色设定 + 存档面板 -->
    <StatusPanel />
    <CharacterPanel />
    <SavePanel @resume="onResume" />
  </div>
</template>
