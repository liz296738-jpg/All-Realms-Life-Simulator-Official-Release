<script setup>
// 通用创建向导：完全由世界规格 creation_schema.steps 驱动。
// 字段类型：text / textarea / number / select / boolean（未知类型按 text 兜底）。
import { ref, reactive, computed } from 'vue'
import { draft, saveApiKey } from '../store'

const props = defineProps({ world: { type: Object, required: true } })
const emit = defineEmits(['complete'])

const schema = props.world?.creation_schema || { steps: [] }
const steps = schema.steps && schema.steps.length ? schema.steps : [
  { step: '基础信息', fields: [
    { key: 'name', label: '姓名', type: 'text', placeholder: '你的名字' },
    { key: 'identity', label: '身份背景', type: 'textarea', placeholder: '简述你的出身与来历' },
  ] },
]
const step = ref(1)

const form = reactive({})
for (const st of steps) {
  for (const f of st.fields || []) {
    if (!(f.key in form)) form[f.key] = f.default ?? (f.type === 'boolean' ? true : '')
  }
}

function onApiKeyInput(e) { saveApiKey(e.target.value.trim()) }

const current = computed(() => steps[step.value - 1])
const coerce = (f) => {
  const v = form[f.key]
  if (f.type === 'number') return v === '' ? undefined : Number(v)
  if (f.type === 'boolean') return !!v
  if (f.type === 'multiselect') {
    if (Array.isArray(v)) return v
    return String(v || '').split(/[,，]/).map(s => s.trim()).filter(Boolean)
  }
  return v
}

function nextStep() { if (step.value < steps.length) step.value++ }
function prevStep() { if (step.value > 1) step.value-- }

function buildArchive() {
  const character = {}
  for (const st of steps) for (const f of st.fields || []) character[f.key] = coerce(f)
  return { character }
}
</script>

<template>
  <div class="max-w-2xl mx-auto px-4 py-8">
    <div class="mb-6 flex items-center justify-between">
      <h2 class="text-xl font-semibold text-amber-100">创建角色 · {{ world.name }}</h2>
      <div class="flex flex-wrap gap-1 text-xs">
        <span v-for="(st, i) in steps" :key="st.step"
          class="px-2 py-1 rounded-full"
          :class="i + 1 === step ? 'bg-amber-600 text-stone-950' : i + 1 < step ? 'bg-stone-700 text-stone-300' : 'bg-stone-800 text-stone-500'">
          {{ st.step }}
        </span>
      </div>
    </div>

    <!-- 当前步骤字段 -->
    <div class="space-y-4">
      <div v-for="f in current.fields" :key="f.key">
        <label class="block text-sm text-stone-400 mb-1">
          {{ f.label || f.key }}<span v-if="f.required" class="text-red-400"> *</span>
          <span v-if="f.hint" class="text-xs text-stone-500">（{{ f.hint }}）</span>
        </label>
        <!-- select -->
        <select v-if="f.type === 'select'" v-model="form[f.key]"
          class="w-full bg-stone-900 border border-stone-700 rounded p-2 text-stone-200">
          <option v-for="opt in (f.options || [])" :key="typeof opt === 'object' ? opt.value : opt" :value="typeof opt === 'object' ? opt.value : opt">
            {{ typeof opt === 'object' ? (opt.label || opt.value) : opt }}
          </option>
        </select>
        <!-- textarea -->
        <textarea v-else-if="f.type === 'textarea'" v-model="form[f.key]" :rows="f.rows || 3"
          :placeholder="f.placeholder || ''"
          class="w-full bg-stone-900 border border-stone-700 rounded p-2 text-stone-200"></textarea>
        <!-- number -->
        <input v-else-if="f.type === 'number'" v-model="form[f.key]" type="number"
          :min="f.min" :max="f.max" :step="f.step || 1" :placeholder="f.placeholder || ''"
          class="w-full bg-stone-900 border border-stone-700 rounded p-2 text-stone-200" />
        <!-- boolean -->
        <label v-else-if="f.type === 'boolean'" class="flex items-center gap-2 cursor-pointer">
          <input v-model="form[f.key]" type="checkbox" class="accent-amber-500 w-4 h-4" />
          <span class="text-sm text-stone-300">{{ f.checkbox_label || '是' }}</span>
        </label>
        <!-- multiselect：文本输入，逗号分隔多选 -->
        <input v-else-if="f.type === 'multiselect'" v-model="form[f.key]" type="text"
          :placeholder="f.placeholder || '（多选，用逗号分隔）'"
          class="w-full bg-stone-900 border border-stone-700 rounded p-2 text-stone-200" />
        <!-- text 兜底 -->
        <input v-else v-model="form[f.key]" type="text" :placeholder="f.placeholder || ''"
          class="w-full bg-stone-900 border border-stone-700 rounded p-2 text-stone-200" />
      </div>

      <!-- API Key（BYOK，与魂兽大陆向导一致） -->
      <div class="pt-2 border-t border-stone-800">
        <label class="block text-sm text-amber-200 mb-1">DeepSeek API Key（可选）</label>
        <input :value="draft.apiKey" type="password" @input="onApiKeyInput" autocomplete="off"
          class="w-full bg-stone-900 border border-stone-700 rounded p-2 font-mono text-sm"
          placeholder="sk-... 你自己的 Key，不填则使用站点默认额度" />
        <p class="text-xs text-stone-500 mt-1">
          填自己的 Key 就不会消耗网站主人的额度。Key 仅保存在你本地浏览器，只用于你这场游戏，不会存入存档。
        </p>
      </div>
    </div>

    <div class="mt-8 flex justify-between">
      <button @click="prevStep" :disabled="step === 1"
        class="px-4 py-2 rounded bg-stone-800 text-stone-300 disabled:opacity-30">上一步</button>
      <button v-if="step < steps.length" @click="nextStep"
        class="px-4 py-2 rounded bg-amber-600 text-stone-950 font-medium">下一步</button>
      <button v-else @click="emit('complete', buildArchive())"
        class="px-4 py-2 rounded bg-amber-600 text-stone-950 font-medium">查看档案卡</button>
    </div>
  </div>
</template>
