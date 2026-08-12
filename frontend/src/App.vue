<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  ui, game, draft, worlds,
  setGameState, setStreaming, setTurnDone, setTurnCommitted,
  clearNarrative, setOptions, setNotes, setEvent,
  setLastChoice, setCanUndo, setError, setSessionId,
  setUiView, setBusy, setActivationOpen, togglePanel,
  appendNarrative, setTurns,
  clientId, getSubscriptionCode,
  refreshEntitlement, isGateError, selectWorld, loadWorlds,
} from './store'
import { postSse, api } from './api'
import HomeView from './views/HomeView.vue'
import GameView from './views/GameView.vue'
import CreationWizard from './components/CreationWizard.vue'
import GenericWizard from './components/GenericWizard.vue'
import CharacterCard from './components/CharacterCard.vue'
import FreedomControl from './components/FreedomControl.vue'
import ActivationPanel from './components/ActivationPanel.vue'

const archive = ref(null)

// 开局时选中的世界决定向导与加载文案；读档/续玩时以会话自带世界为准
const loadingText = computed(() => {
  if (!ui.busy) return ''
  const name = game.state?.meta?.world_name || worlds.selected?.name
  return `正在进入${name || '世界'}…`
})

function newGame(w) { selectWorld(w); setUiView('create') }
function onWizardComplete(a) { archive.value = a; setUiView('review') }
function onCardBack() { setUiView('create') }

async function onCardConfirm() {
  setBusy(true)
  setStreaming(true)
  setTurnDone(false)
  setTurnCommitted(false)
  clearNarrative()
  setOptions([])
  setNotes([])
  setEvent('')
  setLastChoice(null)
  setError('')
  setCanUndo(false)
  try {
    await postSse('/api/new-game', {
      world_id: worlds.selected?.id || 'douluo',
      archive: archive.value,
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
        setTurnCommitted(true)
      },
      onDone: () => { setUiView('game'); setBusy(false); setStreaming(false); setTurnDone(true) },
    })
  } catch (e) {
    setBusy(false)
    if (isGateError(e)) { setActivationOpen(true, e.message) }
    else alert(e.message)
  }
}

function onContinue(save) {
  if (save) {
    resumeGame(save.session_id)
    return
  }
  setUiView('game')
  togglePanel('showSave', true)
}

async function resumeGame(sessionId) {
  setBusy(true)
  setStreaming(true)
  setTurnDone(false)
  setTurnCommitted(false)
  clearNarrative()
  setOptions([])
  setNotes([])
  setEvent('')
  setLastChoice(null)
  setError('')
  setCanUndo(false)
  setSessionId(sessionId)
  try {
    const body = { client_id: clientId(), code: getSubscriptionCode() || null }
    const resp = await fetch('/api/resume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...body, session_id: sessionId }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.detail || `请求失败 ${resp.status}`)
    }
    const d = await resp.json()
    setGameState(d.state)
    setTurns((d.turns || []).map(t => ({
      narrative: t.narrative || '',
      options: t.options || [],
      notes: t.notes || [],
      event: t.event || '',
      choice: t.choice || null,
      html: (t.narrative || '').replace(/<[^>]+>/g, ''),
    })))
    setTurnDone(true)
    setTurnCommitted(true)
    setStreaming(false)
    setUiView('game')
    setBusy(false)
  } catch (e) {
    setBusy(false)
    if (isGateError(e)) { setActivationOpen(true, e.message) }
    else alert(e.message)
  }
}

onMounted(async () => {
  try { await api.health() } catch { /* 后端未启动时提示 */ }
  refreshEntitlement()
  loadWorlds()
})
</script>

<template>
  <div class="h-full">
    <HomeView v-if="ui.view === 'home'" @new-game="newGame" @continue="onContinue" />
    <GenericWizard v-else-if="ui.view === 'create' && worlds.selected && worlds.selected.id !== 'douluo'"
      :world="worlds.selected" @complete="onWizardComplete" />
    <CreationWizard v-else-if="ui.view === 'create'" @complete="onWizardComplete" />
    <CharacterCard v-else-if="ui.view === 'review'" :archive="archive" :world="worlds.selected"
      @confirm="onCardConfirm" @back="onCardBack" />
    <GameView v-else-if="ui.view === 'game'" />

    <FreedomControl v-if="ui.view !== 'home'" />
    <ActivationPanel />

    <div v-if="ui.busy" class="fixed inset-0 z-50 bg-black/70 flex items-center justify-center text-stone-200">
      {{ loadingText }}
    </div>
  </div>
</template>
