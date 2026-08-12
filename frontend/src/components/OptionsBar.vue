<script setup>
import { ref, watch } from 'vue'
import { game } from '../store'

const emit = defineEmits(['choose', 'undo'])
const freeInput = ref('')
const open = ref(false)  // 选项栏是否展开

// 新回合开始（提交行动/流式生成）时自动收回选项栏，避免旧选项一直占位
watch(() => game.streaming, (v) => { if (v) open.value = false })

function onFreeSubmit() {
  const text = freeInput.value.trim()
  if (!text) return
  emit('choose', text)
  freeInput.value = ''
}
</script>

<template>
  <div class="border-t border-stone-800 bg-stone-950/90 px-4 py-4">
    <div class="max-w-3xl mx-auto space-y-3">
      <!-- 选项栏：正文下方的一条细栏，点击展开/收回选项（不再常驻占用文字位置） -->
      <button v-if="game.options.length && game.turnDone" type="button" @click="open = !open"
        :aria-expanded="open"
        class="w-full flex items-center justify-between px-4 py-2 rounded border text-sm transition"
        :class="open
          ? 'border-amber-600/80 bg-amber-900/20 text-amber-100'
          : 'border-stone-700 bg-stone-900 text-amber-200 hover:border-amber-600'">
        <span class="flex items-center gap-2">
          <span class="inline-block transition-transform text-xs" :class="open ? 'rotate-90' : ''">▶</span>
          <span v-if="game.options.length">下一步怎么走 · {{ game.options.length }} 个选项</span>
        </span>
        <span class="text-xs" :class="open ? 'text-amber-400' : 'text-stone-500'">{{ open ? '收起 ▲' : '展开 ▼' }}</span>
      </button>

      <!-- 展开后的选项胶囊 -->
      <div v-if="open && game.options.length && game.turnDone" class="flex flex-wrap gap-2 pt-1">
        <button v-for="opt in game.options" :key="opt.label" type="button"
          @click="emit('choose', opt.label)"
          class="px-4 py-2 rounded-full border text-sm text-amber-100 transition text-left"
          :class="opt.recommended
            ? 'border-amber-400/90 bg-amber-900/30 hover:bg-amber-900/50'
            : 'border-amber-700/70 hover:bg-amber-900/40 hover:border-amber-500'">
          <span class="font-bold text-amber-400 mr-1">[{{ opt.label }}]</span>{{ opt.text }}
          <span v-if="opt.recommended"
            class="ml-2 text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500 text-stone-950 font-semibold align-middle">系统推荐</span>
        </button>
        <!-- 后悔：退回上一回合 -->
        <button v-if="game.canUndo" @click="emit('undo')" type="button"
          class="px-4 py-2 rounded-full border border-dashed border-stone-600 text-sm text-stone-400
                 hover:border-amber-600 hover:text-amber-200 transition text-left"
          title="撤销上一次选择，回到上一回合的选项">
          ↩ 后悔
        </button>
      </div>

      <!-- 自由输入 -->
      <form @submit.prevent="onFreeSubmit" class="flex gap-2">
        <input v-model="freeInput"
          :placeholder="game.turnDone ? '输入你的行动，或：存档 / 查看笔记 / 快进到X / 切换方向…' : '世界正在书写…'"
          :disabled="!game.turnDone"
          class="flex-1 bg-stone-900 border border-stone-700 rounded px-3 py-2 text-stone-200
                 disabled:opacity-40 placeholder-stone-600" />
        <button type="submit" :disabled="!game.turnDone || !freeInput.trim()"
          class="px-4 py-2 rounded bg-amber-600 text-stone-950 font-medium disabled:opacity-30">行动</button>
      </form>
    </div>
  </div>
</template>
