<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import {
  ui, worlds, loadWorlds, SITE_NAME,
  entitlement, refreshEntitlement, fmtDate, clientId, setActivationOpen,
} from '../store'

const emit = defineEmits(['newGame', 'continue'])
const sessions = ref([])

// ── 上传小说 → 建世界 ─────────────────────────────
const file = ref(null)
const apiKey = ref(localStorage.getItem('douluo_api_key') || '')
const buildPhase = ref('')      // '' | 'uploading' | 'error' | 'done'
const buildMsg = ref('')
const deleting = ref('')        // 正在删除的世界 id
const exporting = ref(false)
const dataMsg = ref('')
const dataMsgType = ref('ok')  // 'ok' | 'err'
const refreshing = ref(false)

const statusText = computed(() => {
  if (entitlement.loading) return '加载中…'
  if (entitlement.paid) return `已订阅 · 无限游玩（至 ${fmtDate(entitlement.paidUntil)}）`
  const left = Math.max(0, entitlement.trialLimit - entitlement.trialUsed)
  return `免费试玩中 · 剩余 ${left} 回合 · 1元/月无限玩`
})

async function buildWorld() {
  if (buildPhase.value === 'uploading') return
  if (!file.value) { buildMsg.value = '请先选择一本小说的 TXT 或 Word(.docx) 文件。'; return }
  const key = apiKey.value.trim()
  if (!key) { buildMsg.value = '建世界需要你自己的 DeepSeek API Key（站点不代付额度）。'; return }
  const fd = new FormData()
  fd.append('file', file.value)
  fd.append('api_key', key)
  fd.append('client_id', clientId())
  buildPhase.value = 'uploading'
  buildMsg.value = '正在解析小说并让 AI 搭建世界框架（约 30-90 秒）…'
  try {
    const w = await api.buildWorld(fd)
    await loadWorlds()
    buildPhase.value = 'done'
    buildMsg.value = `世界「${w.name}」创建成功！可在下方「我的世界」里进入。`
    file.value = null
  } catch (e) {
    buildPhase.value = 'error'
    buildMsg.value = e.message
  }
}

function onKeyInput(e) { localStorage.setItem('douluo_api_key', e.target.value.trim()) }

async function delWorld(w) {
  if (!confirm(`确定删除自建世界「${w.name}」吗？该世界的存档不会受影响，但世界本身不可恢复。`)) return
  deleting.value = w.id
  try {
    await api.deleteWorld({ world_id: w.id, client_id: clientId() })
    await loadWorlds()
  } catch (e) { alert(e.message) } finally { deleting.value = '' }
}

async function exportData() {
  if (exporting.value) return
  exporting.value = true
  dataMsg.value = ''
  try {
    const blob = await api.exportAll({ client_id: clientId() })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const ts = new Date().toISOString().slice(0, 10).replace(/-/g, '')
    a.download = `万界人生模拟器-备份-${ts}.json`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    dataMsg.value = '导出成功，请妥善保存文件'
    dataMsgType.value = 'ok'
  } catch (e) {
    dataMsg.value = '导出失败：' + e.message
    dataMsgType.value = 'err'
  } finally { exporting.value = false }
}

async function importData(e) {
  const f = e.target.files?.[0]
  if (!f) return
  dataMsg.value = '正在导入…'
  dataMsgType.value = 'ok'
  try {
    const fd = new FormData()
    fd.append('file', f)
    fd.append('client_id', clientId())
    const r = await api.importAll(fd)
    const parts = []
    if (r.worlds_imported) parts.push(`${r.worlds_imported} 个世界`)
    if (r.saves_imported) parts.push(`${r.saves_imported} 个存档`)
    const skipped = (r.worlds_skipped || 0) + (r.saves_skipped || 0)
    let msg = parts.length ? `已恢复 ${parts.join('、')}` : '没有新数据可导入'
    if (skipped) msg += `，${skipped} 项已存在已跳过`
    dataMsg.value = msg
    dataMsgType.value = 'ok'
    await loadWorlds()
    try { const d = await api.saves(clientId()); sessions.value = d.saves || [] } catch {}
  } catch (e) {
    dataMsg.value = '导入失败：' + e.message
    dataMsgType.value = 'err'
  }
  e.target.value = ''
}

async function refreshPage() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    await loadWorlds()
    try { const d = await api.saves(clientId()); sessions.value = d.saves || [] } catch {}
    dataMsg.value = '页面已刷新'
    dataMsgType.value = 'ok'
  } catch {
    dataMsg.value = '刷新失败'
    dataMsgType.value = 'err'
  } finally { refreshing.value = false }
}

function sessionLabel(s) {
  if (s.level != null && s.level !== 0) return `${s.name}（${s.level_field}${s.level}）`
  return s.name
}

// 找出与指定世界关联的存档
function saveForWorld(worldId) {
  return sessions.value.find(s => s.world_id === worldId)
}

function continueSave(save) {
  emit('continue', save)
}

onMounted(async () => {
  refreshEntitlement()
  loadWorlds()
  try { const d = await api.saves(); sessions.value = d.saves || [] } catch {}
})
</script>

<template>
  <div class="h-full overflow-y-auto px-6 py-10">
    <div class="max-w-3xl mx-auto">
      <!-- 平台标题 -->
      <div class="text-center mb-8">
        <h1 class="text-3xl md:text-4xl font-bold text-amber-200 mb-3 tracking-wide">{{ SITE_NAME }}</h1>
        <p class="text-stone-400 text-sm md:text-base leading-relaxed">
          一个容纳众多模拟世界的文字 RPG 平台。选择你感兴趣的世界，从出生开始书写属于你的人生。
        </p>
      </div>

      <!-- 创作者已开发的世界 -->
      <section class="mb-10">
        <h2 class="text-lg font-semibold text-stone-300 mb-3 flex items-center gap-2">
          ✦ 创作者已开发的世界
        </h2>
        <div v-if="worlds.builtin.length" class="grid gap-3 sm:grid-cols-2">
          <div v-for="w in worlds.builtin" :key="w.id"
            class="rounded-lg border border-amber-800/50 bg-stone-900/70 p-5 flex flex-col hover:border-amber-500/70 transition">
            <div class="flex items-center justify-between mb-1">
              <h3 class="text-xl font-bold text-amber-200">{{ w.name }}</h3>
              <span class="text-[10px] px-2 py-0.5 rounded-full bg-amber-900/60 text-amber-300">创作者</span>
            </div>
            <p class="text-sm text-stone-400 flex-1 mb-4">{{ w.desc }}</p>
            <div class="space-y-2">
              <button v-if="saveForWorld(w.id)" @click="continueSave(saveForWorld(w.id))"
                class="w-full py-2.5 rounded-lg bg-emerald-700 text-white font-medium hover:bg-emerald-600 transition text-sm">
                ▶ 继续冒险（{{ saveForWorld(w.id).name }} · 第{{ saveForWorld(w.id).turn }}回合）
              </button>
              <button @click="emit('newGame', w)"
                class="w-full py-2.5 rounded-lg bg-amber-600 text-stone-950 font-medium hover:bg-amber-500 transition">
                进入「{{ w.name }}」
              </button>
            </div>
          </div>
        </div>
        <p v-else class="text-sm text-stone-500">世界加载中…</p>
      </section>

      <!-- 我的世界 -->
      <section class="mb-10">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-lg font-semibold text-stone-300">✦ 我的世界</h2>
          <span class="text-xs text-stone-500">仅你自己可见</span>
        </div>
        <div v-if="worlds.mine.length" class="grid gap-3 sm:grid-cols-2">
          <div v-for="w in worlds.mine" :key="w.id"
            class="rounded-lg border border-stone-700 bg-stone-900/70 p-5 flex flex-col hover:border-stone-500 transition">
            <div class="flex items-center justify-between mb-1">
              <h3 class="text-lg font-bold text-stone-200">{{ w.name }}</h3>
              <button @click="delWorld(w)" :disabled="deleting === w.id"
                class="text-xs text-stone-500 hover:text-red-400 transition disabled:opacity-30">删除</button>
            </div>
            <p class="text-sm text-stone-400 flex-1 mb-4">{{ w.desc || '由你上传小说生成的专属世界' }}</p>
            <div class="space-y-2">
              <button v-if="saveForWorld(w.id)" @click="continueSave(saveForWorld(w.id))"
                class="w-full py-2.5 rounded-lg bg-emerald-700 text-white font-medium hover:bg-emerald-600 transition text-sm">
                ▶ 继续冒险（{{ saveForWorld(w.id).name }} · 第{{ saveForWorld(w.id).turn }}回合）
              </button>
              <button @click="emit('newGame', w)"
                class="w-full py-2.5 rounded-lg border border-amber-600/60 text-amber-200 hover:bg-amber-900/30 transition">
                进入「{{ w.name }}」
              </button>
            </div>
          </div>
        </div>
        <p v-else class="text-sm text-stone-500 mb-4">还没有自建世界——上传一本你喜欢的小说，AI 会帮你搭出它的世界框架。</p>

        <!-- 上传小说建世界 -->
        <div class="rounded-lg border border-dashed border-stone-600 bg-stone-900/40 p-5">
          <h3 class="font-medium text-stone-300 mb-2">📖 上传小说 → 创建专属世界</h3>
          <p class="text-xs text-stone-500 leading-relaxed mb-4">
            上传小说的 <b>TXT</b> 或 <b>Word(.docx)</b> 文件（≤30MB），AI 会抽样精读并生成一套
            可游玩的世界框架（规则书 + 资源属性 + 创建选项）。<br/>
            建世界会调用 <b>你自己的 DeepSeek API Key</b> 计费（约几分钱），站点不代付；原文章节不会留存。
          </p>
          <div class="space-y-3">
            <input type="file" accept=".txt,.md,.docx"
              @change="e => { file = e.target.files[0]; buildMsg = '' }"
              class="block w-full text-sm text-stone-300 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-stone-700 file:text-stone-200 file:hover:bg-stone-600 file:cursor-pointer" />
            <input v-model="apiKey" type="password" @input="onKeyInput" autocomplete="off" placeholder="你的 DeepSeek API Key（sk-...）"
              class="w-full bg-stone-900 border border-stone-700 rounded-lg p-2.5 font-mono text-sm" />
            <button @click="buildWorld" :disabled="buildPhase === 'uploading'"
              class="w-full py-2.5 rounded-lg bg-amber-600 text-stone-950 font-medium hover:bg-amber-500 transition disabled:opacity-50">
              {{ buildPhase === 'uploading' ? '⏳ 正在生成世界框架…' : '✨ 生成世界框架' }}
            </button>
            <p v-if="buildMsg" :class="buildPhase === 'error' ? 'text-red-400' : 'text-emerald-400'"
              class="text-xs leading-relaxed">{{ buildMsg }}</p>
          </div>
        </div>
      </section>

      <!-- 继续游戏 -->
      <div class="space-y-3">
        <button v-if="sessions.length" @click="emit('continue')"
          class="w-full py-3 rounded-lg border border-stone-600 text-stone-300 hover:bg-stone-800 transition">
          继续游戏 / 读档
        </button>
        <p v-if="sessions.length" class="text-xs text-stone-500 text-center">
          已有存档：{{ sessions.map(sessionLabel).join('、') }}
        </p>
      </div>

      <!-- 数据备份 -->
      <div class="text-center mt-6 pt-6 border-t border-stone-800">
        <div class="flex justify-center gap-4">
          <button @click="exportData" :disabled="exporting"
            class="text-xs text-stone-400 hover:text-amber-300 transition disabled:opacity-40">
            {{ exporting ? '⏳ 导出中…' : '📥 导出数据' }}
          </button>
          <label class="text-xs text-stone-400 hover:text-amber-300 transition cursor-pointer">
            📤 导入恢复
            <input type="file" accept=".json" @change="importData" class="hidden" />
          </label>
          <button @click="refreshPage" :disabled="refreshing"
            class="text-xs text-stone-400 hover:text-amber-300 transition disabled:opacity-40">
            {{ refreshing ? '⏳' : '🔄' }} 刷新页面
          </button>
        </div>
        <p class="text-[11px] text-stone-600 mt-1">定期导出备份，浏览器清缓存后可导入恢复</p>
        <p v-if="dataMsg" :class="[
          'text-sm mt-3 px-3 py-2 rounded-lg border text-center',
          dataMsgType === 'err'
            ? 'bg-red-900/40 border-red-800 text-red-200'
            : 'bg-emerald-900/40 border-emerald-800 text-emerald-100'
        ]">{{ dataMsg }}</p>
      </div>

      <!-- 订阅 / 免费试玩状态 -->
      <div class="text-center mt-8">
        <button @click="setActivationOpen(true)"
          class="text-xs text-stone-400 hover:text-amber-300 transition">
          💳 订阅 / 激活码
        </button>
        <p class="text-[11px] text-stone-600 mt-1">{{ statusText }}</p>
      </div>
    </div>
  </div>
</template>
