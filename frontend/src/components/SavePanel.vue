<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import { ui, game, setGameState, setSessionId, setUiView, togglePanel, clientId } from '../store'

const emit = defineEmits(['resume'])
const saves = ref([])
const msg = ref('')
const loading = ref(false)
const exporting = ref(null)  // 正在导出的 session_id，防双击重复下载

async function refresh() {
  try {
    const d = await api.saves(clientId())
    saves.value = d.saves || []
  } catch (e) { msg.value = e.message }
}

async function doSave() {
  if (!game.sessionId) return
  loading.value = true
  try {
    const d = await api.save(game.sessionId)
    msg.value = `已存档（回合 ${d.savepoint.turn}）`
    await refresh()
  } catch (e) { msg.value = e.message } finally { loading.value = false }
}

async function doResume(sid) {
  loading.value = true
  try {
    const d = await api.resume(sid)
    setGameState(d.state)
    togglePanel('showSave', false)
    emit('resume', { state: d.state, narrative: d.last_narrative, options: d.last_options, turns: d.turns, canUndo: d.can_undo })
  } catch (e) { msg.value = e.message } finally { loading.value = false }
}

async function doDelete(sid) {
  try {
    await api.del(sid)
    if (game.sessionId === sid) setSessionId(null)
    msg.value = '已删除'
    await refresh()
  } catch (e) { msg.value = e.message }
}

function goHome() {
  togglePanel('showSave', false)
  setUiView('home')
}

async function doExport(sid) {
  if (exporting.value) return  // 已有导出进行中，忽略重复点击
  exporting.value = sid
  try {
    const d = await api.export(sid)
    if (!d.content || !d.turns) {
      msg.value = '这段旅程还没有可导出的剧情'
      return
    }
    const blob = new Blob([d.content], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = d.filename || 'story.md'
    document.body.appendChild(a)
    a.click()
    a.remove()
    // 延迟释放对象 URL：click 同步释放会让 Firefox 中断下载
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    msg.value = `已导出 ${d.title}（共 ${d.turns} 段剧情）`
  } catch (e) { msg.value = e.message } finally { exporting.value = null }
}

onMounted(refresh)
</script>

<template>
  <transition name="slide">
    <div v-if="ui.showSave" class="fixed inset-0 z-40 bg-black/60 flex items-center justify-center p-4" @click.self="togglePanel('showSave', false)">
      <div class="w-full max-w-md rounded-lg border border-stone-700 bg-stone-900 p-5 shadow-2xl">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-amber-200 font-semibold">存档 / 读档</h3>
          <button @click="togglePanel('showSave', false)" class="text-stone-400 hover:text-stone-200">✕</button>
        </div>

        <div class="flex gap-2 mb-4">
          <button @click="doSave" :disabled="loading || !game.sessionId"
            class="flex-1 px-3 py-2 rounded bg-amber-600 text-stone-950 text-sm font-medium disabled:opacity-30">
            💾 存档当前进度
          </button>
          <button @click="goHome"
            class="px-3 py-2 rounded bg-stone-700 text-amber-300 hover:bg-stone-600 text-sm font-medium">
            🏠 返回主界面
          </button>
        </div>
        <p v-if="msg" class="text-xs text-amber-300 mb-2">{{ msg }}</p>

        <div class="space-y-2 max-h-64 overflow-y-auto">
          <div v-for="s in saves" :key="s.session_id"
            class="rounded border border-stone-700 p-3 bg-stone-800/50">
            <div class="flex justify-between items-start">
              <div class="text-sm">
                <span class="text-stone-100 font-medium">{{ s.name }}</span>
                <span class="text-stone-500 text-xs ml-2">{{ s.level_field }} {{ s.level }}</span>
                <div class="text-xs text-stone-400 mt-0.5">{{ s.place }} · {{ s.date }} · 回合{{ s.turn }}</div>
              </div>
              <div class="flex gap-1 shrink-0">
                <button @click="doResume(s.session_id)" class="text-xs px-2 py-1 rounded bg-stone-700 text-stone-200 hover:bg-stone-600">继续</button>
                <button @click="doExport(s.session_id)" :disabled="exporting !== null" title="把这段旅程的剧情导出成 Markdown 小说" class="text-xs px-2 py-1 rounded bg-stone-700 text-amber-300 hover:bg-stone-600 disabled:opacity-40">{{ exporting === s.session_id ? '导出中…' : '📖 导出' }}</button>
                <button @click="doDelete(s.session_id)" class="text-xs px-2 py-1 rounded bg-red-900/60 text-red-200 hover:bg-red-800">删</button>
              </div>
            </div>
          </div>
          <p v-if="!saves.length" class="text-sm text-stone-500 py-4 text-center">还没有存档</p>
        </div>
      </div>
    </div>
  </transition>
</template>

<style>
.slide-enter-active, .slide-leave-active { transition: opacity 0.2s ease; }
.slide-enter-from, .slide-leave-to { opacity: 0; }
</style>
