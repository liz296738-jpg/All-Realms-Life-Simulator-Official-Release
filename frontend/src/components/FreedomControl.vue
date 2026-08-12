<script setup>
import { ref, watch, onBeforeUnmount } from 'vue'
import { draft, setFreedom } from '../store'

const open = ref(false)
const root = ref(null)

// 五个档位：200 ~ 2000 字
const TIERS = [
  { value: 1, label: '精炼', chars: 200, note: '短小精悍，快节奏推进' },
  { value: 2, label: '简洁', chars: 500, note: '适度展开，节奏较快' },
  { value: 3, label: '标准', chars: 1000, note: '剧情适中 · 默认' },
  { value: 4, label: '详尽', chars: 1500, note: '细节丰富，沉浸感强' },
  { value: 5, label: '极尽', chars: 2000, note: '事无巨细，最长生成' },
]

function current() {
  return TIERS.find(t => t.value === draft.freedom) || TIERS[2]
}

function pick(v) {
  setFreedom(v)
  open.value = false
}

// 点击面板外关闭
function onDocClick(e) {
  if (root.value && !root.value.contains(e.target)) open.value = false
}
watch(open, (v) => {
  if (v) document.addEventListener('click', onDocClick)
  else document.removeEventListener('click', onDocClick)
})
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <div ref="root" class="fixed top-3 right-3 z-30">
    <button @click.stop="open = !open"
      class="px-2.5 py-1 rounded-full border text-xs font-medium transition backdrop-blur"
      :class="open ? 'border-amber-500 bg-amber-900/50 text-amber-200' : 'border-stone-700 bg-stone-900/80 text-stone-300 hover:border-amber-600 hover:text-amber-200'"
      title="自由度：控制每次选择后生成的文字多少">
      📜 {{ current().label }} · {{ current().chars }}字
    </button>

    <transition name="fade">
      <div v-if="open" class="absolute right-0 mt-2 w-64 rounded-lg border border-stone-700 bg-stone-900/95 p-4 shadow-2xl">
        <h3 class="text-amber-200 font-semibold mb-1">自由度</h3>
        <p class="text-xs text-stone-400 mb-3 leading-relaxed">
          自由度决定每次选择后 AI 生成的剧情文字多少：档位越高文字越长、细节越丰富，
          生成耗时也相应增加。五个档位从 200 字到 2000 字。
        </p>
        <div class="space-y-1.5">
          <button v-for="t in TIERS" :key="t.value" @click="pick(t.value)"
            class="w-full flex items-center justify-between gap-2 px-3 py-2 rounded text-sm transition"
            :class="draft.freedom === t.value
              ? 'border border-amber-600 bg-amber-900/50 text-amber-100'
              : 'border border-stone-700 text-stone-300 hover:bg-stone-800'">
            <span class="font-medium">{{ t.label }} <span class="text-xs text-stone-500">· {{ t.chars }}字</span></span>
            <span class="text-xs text-stone-500 text-right shrink-0">{{ t.note }}</span>
          </button>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.15s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
