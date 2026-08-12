<script setup>
import { computed, ref, watch, reactive } from 'vue'
import { game, ui, clientId, draft, togglePanel, patchNpcState } from '../store'
import { api } from '../api'

// ── 防抖工具 ──
const timers = {}
function debounce(key, fn, ms = 800) {
  if (timers[key]) clearTimeout(timers[key])
  timers[key] = setTimeout(fn, ms)
}

// ── 状态 ──
const loading = reactive({})     // { name: true } → 该 NPC 提取中
const toast = ref('')
const toastType = ref('ok')     // 'ok' | 'err'
const extracting = ref(false)   // 全局提取中（禁用按钮）

// ── 主角名 ──
const protagonist = computed(() => game.state?.character?.name || '')

// ── NPC 列表 ──
const npcNames = computed(() => {
  const names = new Set()
  const aff = game.state?.affection || {}
  Object.keys(aff).forEach(n => names.add(n))
  const npcs = game.state?.npcs || {}
  Object.keys(npcs).forEach(n => names.add(n))
  return Array.from(names).filter(n => n !== protagonist.value).sort()
})

// ── NPC 档案辅助 ──
function getProfile(name) {
  const npcs = game.state?.npcs || {}
  const raw = npcs[name] || {}
  return {
    age: raw.age || '',
    gender: raw.gender || '',
    background: raw.background || raw.description || '',
    affection: raw.affection || String(game.state?.affection?.[name] || ''),
    personality: raw.personality || [],
    strength: raw.strength || '',
    preferences: raw.preferences || '',
    customNotes: raw.customNotes || '',
    firstMet: raw.first_met || raw.first_met || '',
  }
}

function hasProfile(name) {
  const p = getProfile(name)
  return !!(p.age || p.gender || p.background || p.personality.length || p.strength || p.preferences)
}

// ── Toast ──
function show(msg, type = 'ok') {
  toast.value = msg
  toastType.value = type
  setTimeout(() => { toast.value = '' }, 2000)
}

// ── AI 提取 ──
async function extract(names) {
  if (!names.length || extracting.value) return
  extracting.value = true
  names.forEach(n => { loading[n] = true })
  try {
    const d = await api.extractNpcProfiles({
      session_id: game.sessionId,
      npc_names: names,
      client_id: clientId(),
      api_key: draft.apiKey?.trim() || null,
    })
    // 增量更新到 game.state.npcs（通过唯一 action 路径）
    const profiles = d.profiles || {}
    for (const [name, prof] of Object.entries(profiles)) {
      patchNpcState(name, prof)
    }
    show(`已刷新 ${names.length} 个角色的情报`)
  } catch (e) {
    show('提取失败：' + e.message, 'err')
  } finally {
    extracting.value = false
    names.forEach(n => { loading[n] = false })
  }
}

function refreshNpc(name) { extract([name]) }
function refreshAll() { extract([...npcNames.value]) }

// ── 自动保存 customNotes（防抖 800ms）──
function onCustomChange(name, value) {
  // 立即乐观更新本地 state（通过唯一 action 路径）
  patchNpcState(name, { customNotes: value })
  // 防抖落盘
  debounce(`save_${name}`, async () => {
    try {
      await api.updateNpcs({
        session_id: game.sessionId,
        client_id: clientId(),
        npcs: { [name]: { customNotes: value } },
      })
    } catch { /* 静默失败；下次保存时自动重试 */ }
  }, 800)
}

// 打开面板时清空 toast
watch(() => ui.showCharacter, (open) => {
  if (open) toast.value = ''
})

function close() {
  togglePanel('showCharacter', false)
}
</script>

<template>
  <!-- 悬浮按钮 -->
  <button @click="togglePanel('showCharacter', !ui.showCharacter)"
    class="fixed top-[6.5rem] right-4 z-30 px-3 py-1.5 rounded-full bg-stone-800/90 border border-stone-700 text-sm text-stone-300 hover:bg-stone-700">
    {{ ui.showCharacter ? '收起 ✕' : '👥 角色' }}
  </button>

  <!-- 角色情报抽屉 -->
  <transition name="slide">
    <aside v-if="ui.showCharacter"
      class="fixed top-[8.5rem] right-4 z-20 w-80 max-h-[70vh] overflow-y-auto rounded-lg border border-stone-700 bg-stone-900/95 p-4 shadow-2xl">

      <!-- Header -->
      <div class="flex justify-between items-center mb-3">
        <div class="flex items-center gap-2">
          <h3 class="text-amber-200 font-semibold text-sm">角色情报</h3>
          <button v-if="npcNames.length" @click="refreshAll" :disabled="extracting"
            class="text-[11px] px-1.5 py-0.5 rounded border border-stone-600 text-stone-400 hover:text-amber-300 hover:border-amber-700 disabled:opacity-40"
            :title="extracting ? '提取中…' : 'AI 分析上下文，刷新所有角色情报'">
            {{ extracting ? '⏳' : '🔄' }}
          </button>
        </div>
        <button @click="close" class="text-stone-400 hover:text-stone-200 text-lg leading-none">✕</button>
      </div>

      <!-- 遮罩 -->
      <div @click="close" class="fixed inset-0 -z-10" />

      <!-- NPC 列表 -->
      <div v-if="npcNames.length" class="space-y-3">
        <div v-for="name in npcNames" :key="name"
          class="rounded-lg border border-stone-700 bg-stone-800/50 overflow-hidden">

          <!-- ═══ Header：名字 + 操作 ═══ -->
          <div class="flex items-center justify-between px-3 pt-2.5 pb-0.5">
            <span class="text-sm font-medium text-stone-100">{{ name }}</span>
            <button @click="refreshNpc(name)" :disabled="loading[name]"
              class="text-[10px] px-1 py-0.5 rounded border border-stone-700 text-stone-500 hover:text-amber-400 hover:border-amber-800 disabled:opacity-30"
              :title="hasProfile(name) ? '重新分析上下文' : 'AI 提取该角色情报'">
              {{ loading[name] ? '⏳' : '🔄' }}
            </button>
          </div>

          <!-- ═══ 骨架屏 ═══ -->
          <div v-if="loading[name]" class="px-3 pb-2.5 space-y-1.5 animate-pulse">
            <div class="h-2.5 bg-stone-700 rounded w-3/4"></div>
            <div class="h-2.5 bg-stone-700 rounded w-1/2"></div>
            <div class="h-2.5 bg-stone-700 rounded w-2/3"></div>
          </div>

          <!-- ═══ 内容 ═══ -->
          <template v-else>
            <div class="px-3 pb-2.5 space-y-1.5">
              <!-- 基础信息行 -->
              <p class="text-[11px] text-stone-400 leading-relaxed">
                <template v-if="getProfile(name).gender || getProfile(name).age || getProfile(name).background">
                  <span v-if="getProfile(name).gender" class="text-stone-300">{{ getProfile(name).gender }}</span>
                  <span v-if="getProfile(name).age" class="text-stone-300">{{ getProfile(name).age }}岁</span>
                  <span v-if="getProfile(name).gender || getProfile(name).age" class="text-stone-600 mx-0.5">·</span>
                  <span v-if="getProfile(name).background">{{ getProfile(name).background }}</span>
                </template>
                <span v-else class="text-stone-600 italic">点击 🔄 提取情报</span>
              </p>

              <!-- 动态关系行 -->
              <div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px]">
                <span v-if="getProfile(name).affection" class="inline-flex items-center gap-0.5 text-red-400">
                  ❤️ {{ getProfile(name).affection }}
                </span>
                <span v-if="getProfile(name).strength" class="inline-flex items-center gap-0.5 text-amber-400">
                  ⚔️ {{ getProfile(name).strength }}
                </span>
              </div>

              <!-- 性格标签 -->
              <div v-if="getProfile(name).personality.length" class="flex flex-wrap gap-1">
                <span v-for="tag in getProfile(name).personality" :key="tag"
                  class="text-[10px] px-1.5 py-0.5 rounded-full bg-stone-700/80 text-stone-300 border border-stone-600/50">
                  {{ tag }}
                </span>
              </div>

              <!-- 喜好摘要 -->
              <p v-if="getProfile(name).preferences"
                class="text-[11px] text-stone-400 leading-relaxed italic">
                💬 {{ getProfile(name).preferences }}
              </p>

              <!-- 自定义备注 textarea（自动保存） -->
              <textarea
                :value="getProfile(name).customNotes"
                @input="onCustomChange(name, $event.target.value)"
                rows="2"
                class="w-full mt-1 px-2 py-1 rounded bg-stone-700/60 border border-stone-600 text-stone-200 text-[11px] placeholder-stone-500 resize-y focus:border-amber-600/70 outline-none transition-colors"
                placeholder="手动修改或补充该角色的隐藏设定…"
              ></textarea>
            </div>
          </template>
        </div>
      </div>

      <!-- 空状态 -->
      <p v-else class="text-xs text-stone-500 py-6 text-center leading-relaxed">
        暂无已知 NPC<br>
        <span class="text-stone-600">游戏进程中出现好感度变化的角色会出现在这里</span>
      </p>
    </aside>
  </transition>

  <!-- Toast -->
  <transition name="fade">
    <div v-if="toast"
      :class="[
        'fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-lg text-sm shadow-lg',
        toastType === 'err' ? 'bg-red-900/90 text-red-100' : 'bg-emerald-800/90 text-emerald-100'
      ]">
      {{ toast }}
    </div>
  </transition>
</template>

<style>
.slide-enter-active, .slide-leave-active { transition: all 0.2s ease; }
.slide-enter-from, .slide-leave-to { opacity: 0; transform: translateX(20px); }
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
