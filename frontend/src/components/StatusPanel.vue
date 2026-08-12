<script setup>
import { computed } from 'vue'
import { game, ui, worldName, togglePanel } from '../store'

const st = computed(() => game.state)

// 等级字段：由后端 state.meta.level_field 驱动（soul_level / realm / heart）
const levelField = computed(() => st.value?.meta?.level_field || '')
const levelValue = computed(() => {
  const lf = levelField.value
  if (!lf || !st.value?.character) return null
  return st.value.character[lf]
})

// 魂环（仅魂兽大陆有 soul_rings 数组，其他世界自动为空）
const rings = computed(() => st.value?.soul_rings || [])
const affections = computed(() => {
  const a = st.value?.affection || {}
  return Object.entries(a).filter(([, v]) => v !== 0).sort((x, y) => y[1] - x[1])
})
const resources = computed(() => {
  const r = st.value?.resources || {}
  return Object.entries(r).filter(([, v]) => v !== 0)
})
const stats = computed(() => {
  const s = st.value?.stats || {}
  return Object.entries(s).filter(([, v]) => v !== 0)
})
const factions = computed(() => {
  const f = st.value?.faction || {}
  return Object.entries(f).filter(([, v]) => v !== 0)
})
/** 角色字段（动态遍历，去重空值 / 对象值）。 */
const characterFields = computed(() => {
  const c = st.value?.character || {}
  return Object.entries(c)
    .filter(([, v]) => v !== '' && v !== null && v !== undefined && typeof v !== 'object')
    .map(([k, v]) => ({ key: k, label: k, value: Array.isArray(v) ? v.join('、') : String(v) }))
})
</script>

<template>
  <!-- 折叠按钮 -->
  <button @click="togglePanel('showStatus', !ui.showStatus)"
    class="fixed top-14 right-4 z-30 px-3 py-1.5 rounded-full bg-stone-800/90 border border-stone-700 text-sm text-stone-300 hover:bg-stone-700">
    {{ ui.showStatus ? '收起 ✕' : '☰ 状态' }}
  </button>

  <!-- 状态栏抽屉 -->
  <transition name="slide">
    <aside v-if="ui.showStatus && st"
      class="fixed top-24 right-4 z-20 w-80 max-h-[80vh] overflow-y-auto rounded-lg border border-stone-700 bg-stone-900/95 p-4 shadow-2xl">

      <!-- ── 标题：世界名 + 等级 ── -->
      <h3 class="text-amber-200 font-semibold mb-3">
        {{ worldName(st) }}
        <span v-if="levelValue != null" class="text-amber-300 font-medium ml-1">
          · {{ levelField }} {{ levelValue }}
        </span>
      </h3>

      <!-- ── 角色字段（动态遍历） ── -->
      <dl v-if="characterFields.length" class="text-xs space-y-1.5">
        <div v-for="row in characterFields" :key="row.key" class="flex justify-between">
          <dt class="text-stone-400">{{ row.label }}</dt>
          <dd class="text-stone-100 text-right">{{ row.value }}</dd>
        </div>
      </dl>

      <!-- ── 所在地 / 时间 ── -->
      <dl class="text-xs space-y-1.5 mt-2">
        <div class="flex justify-between"><dt class="text-stone-400">所在地</dt><dd class="text-stone-100 text-right">{{ st.location.place }}</dd></div>
        <div class="flex justify-between"><dt class="text-stone-400">时间</dt><dd class="text-stone-100">{{ st.location.date }}（{{ st.location.season }}）</dd></div>
      </dl>

      <!-- ── 魂环（有 soul_rings 的 world 才渲染） ── -->
      <template v-if="rings.length">
        <h4 class="text-stone-300 text-xs font-semibold mt-4 mb-1">魂环配置</h4>
        <div class="text-xs space-y-1">
          <div v-for="r in rings" :key="r.slot" class="text-stone-200">
            第{{ r.slot }}环 · {{ r.years }}年 · {{ r.beast }}
            <span class="text-stone-500">（{{ r.skill }}）</span>
          </div>
        </div>
      </template>

      <!-- ── 资源（动态遍历） ── -->
      <template v-if="resources.length">
        <h4 class="text-stone-300 text-xs font-semibold mt-4 mb-1">资源</h4>
        <p class="text-xs text-stone-200">{{ resources.map(([k, v]) => `${k} ${v}`).join('、') }}</p>
      </template>

      <!-- ── 属性（动态遍历） ── -->
      <template v-if="stats.length">
        <h4 class="text-stone-300 text-xs font-semibold mt-4 mb-1">属性</h4>
        <p class="text-xs text-stone-200">{{ stats.map(([k, v]) => `${k} ${v}`).join('、') }}</p>
      </template>

      <!-- ── 势力声望（动态遍历） ── -->
      <template v-if="factions.length">
        <h4 class="text-stone-300 text-xs font-semibold mt-4 mb-1">势力声望</h4>
        <p class="text-xs text-stone-200">{{ factions.map(([k, v]) => `${k} ${v}`).join('、') }}</p>
      </template>

      <!-- ── 好感度 ── -->
      <h4 class="text-stone-300 text-xs font-semibold mt-4 mb-1">好感度</h4>
      <div v-if="affections.length" class="text-xs space-y-0.5">
        <div v-for="[name, val] in affections" :key="name" class="flex justify-between">
          <span class="text-stone-300">{{ name }}</span>
          <span :class="val >= 0 ? 'text-emerald-400' : 'text-red-400'">{{ val > 0 ? '+' : '' }}{{ val }}</span>
        </div>
      </div>
      <p v-else class="text-xs text-stone-500">暂无变化的好感</p>

      <!-- ── 道具 ── -->
      <h4 class="text-stone-300 text-xs font-semibold mt-4 mb-1">道具</h4>
      <p class="text-xs text-stone-200">{{ st.inventory.length ? st.inventory.join('、') : '无' }}</p>

      <!-- ── 笔记 ── -->
      <h4 class="text-stone-300 text-xs font-semibold mt-4 mb-1">笔记</h4>
      <div v-if="st.notes.length" class="text-xs space-y-0.5">
        <p v-for="(n, i) in st.notes" :key="i" class="text-stone-300">· {{ n }}</p>
      </div>
      <p v-else class="text-xs text-stone-500">暂无</p>

      <!-- ── 元信息 ── -->
      <div class="mt-4 pt-3 border-t border-stone-700 text-[11px] text-stone-500 space-y-0.5">
        <p>游玩方向：{{ st.meta.direction }} · 时间线：{{ st.meta.timeline_binding }}</p>
        <p>回合 {{ st.meta.turn }} · 回溯剩余 {{ st.meta.rewind_left }} 次 · 成就 {{ st.meta.achievements.length }}</p>
      </div>
    </aside>
  </transition>
</template>

<style>
.slide-enter-active, .slide-leave-active { transition: all 0.2s ease; }
.slide-enter-from, .slide-leave-to { opacity: 0; transform: translateX(20px); }
</style>
