<script setup>
import { ref, computed, watch } from 'vue'
import { draft, saveApiKey, updateDraft, DEFAULT_WUHUN } from '../store'

const emit = defineEmits(['complete'])

function onApiKeyInput(e) { saveApiKey(e.target.value.trim()) }
const step = ref(1)
const total = 5

// 天赋档 → 先天魂力区间
const TIERS = [
  { key: '凡人档', range: '先天魂力 1-3', note: '前期吃瘪、容易卡级，逆袭感最强' },
  { key: '普通魂师档', range: '先天魂力 4-6', note: '白灵藤品质上下，需勤奋 + 际遇' },
  { key: '天才档', range: '先天魂力 7-9', note: '顶级武魂级别，前期顺风顺水' },
  { key: '怪物档', range: '先天魂力 9-10', note: '变异顶级/双生武魂，慎选——上限高但开局不得超大陆顶级天才范围' },
]
const TIER_RANGE = { '凡人档': [1, 3], '普通魂师档': [4, 6], '天才档': [7, 9], '怪物档': [9, 10] }

// 出身 → 初始金币区间
const ORIGIN_GOLD = { '平民': [5, 10], '小家族': [100, 300], '宗门子弟': [500, 800], '孤儿': [2, 5] }
// 未显式填金币时的默认值（取区间上界，对齐后端 douluo.json origin_defaults）
const ORIGIN_GOLD_HI = { '平民': 10, '小家族': 300, '宗门子弟': 800, '孤儿': 5 }

const IDENTITIES = [
  { key: '穿越者', hint: '带着现代记忆醒来，对这片大陆似懂非懂' },
  { key: '正典重生/替换', hint: '成为大陆既定剧情中某位已存在的角色，改变命运' },
  { key: '原创角色', hint: '全新的人，出生地、武魂都由你定' },
  { key: '自定义', hint: '你有别的想法，你自己说' },
]
const DIRECTIONS = ['乙女向', '重生向', '复仇向', '磕CP向', '自由/综合向', '自定义']
const BINDINGS = ['高度绑定', '半绑定', '完全脱钩']

const stepLabels = ['你是谁', '来处与秘密', '你的特质', '武魂与天赋', '初始财富']

watch(() => draft.talentTier, (t) => {
  if (t) {
    const [lo, hi] = TIER_RANGE[t]
    const v = Math.round((lo + hi) / 2)
    updateDraft('innateSoulPower', v)
  }
})

function nextStep() {
  if (step.value < total) step.value++
}
function prevStep() {
  if (step.value > 1) step.value--
}
function pickTier(t) { updateDraft('talentTier', t) }

function buildArchive() {
  return {
    character: {
      name: draft.name || '无名',
      gender: draft.gender,
      age: Number(draft.age) || 12,
      wuhun: draft.wuhun || DEFAULT_WUHUN,
      wuhun_type: draft.wuhunType,
      innate_soul_power: Number(draft.innateSoulPower) || 5,
      talent_tier: draft.talentTier || '普通魂师档',
      origin: draft.origin,
      background: draft.background,
      family: draft.family,
      secret: draft.secret,
      traits: draft.traits,
      personality: draft.personality ? draft.personality.split(/[,，]/).map(s => s.trim()).filter(Boolean) : [],
      desire_to_grow: Number(draft.desire) || 5,
      development_direction: draft.developmentDirection,
      special_items: draft.specialItems.length ? draft.specialItems.split(/[,，]/).map(s => s.trim()).filter(Boolean) : [],
      identity: draft.identity,
      identity_note: draft.identityNote,
    },
    start_location: draft.origin,
    direction: draft.direction,
    timeline_binding: draft.timelineBinding,
    // 初始金魂币：玩家显式填写优先，否则按出身取区间上界（与魂兽大陆规格 origin_defaults 对齐）
    initial_gold: draft.gold !== undefined && draft.gold !== ''
      ? Number(draft.gold)
      : (ORIGIN_GOLD_HI[draft.origin] ?? 10),
  }
}
</script>

<template>
  <div class="max-w-2xl mx-auto px-4 py-8">
    <div class="mb-6 flex items-center justify-between">
      <h2 class="text-xl font-semibold text-amber-100">创建角色</h2>
      <div class="flex gap-1 text-xs">
        <span v-for="(label, i) in stepLabels" :key="label"
          class="px-2 py-1 rounded-full"
          :class="i + 1 === step ? 'bg-amber-600 text-stone-950' : i + 1 < step ? 'bg-stone-700 text-stone-300' : 'bg-stone-800 text-stone-500'">
          {{ label }}
        </span>
      </div>
    </div>

    <!-- 第一步：你是谁 -->
    <div v-if="step === 1" class="space-y-4">
      <div>
        <p class="text-sm text-stone-400 mb-2">你的开局身份类型</p>
        <div class="grid grid-cols-2 gap-2">
          <button v-for="id in IDENTITIES" :key="id.key"
            @click="updateDraft('identity', id.key)"
            class="text-left p-3 rounded border transition"
            :class="draft.identity === id.key ? 'border-amber-500 bg-amber-900/30' : 'border-stone-700 bg-stone-900 hover:border-stone-500'">
            <div class="font-medium text-stone-200">{{ id.key }}</div>
            <div class="text-xs text-stone-400 mt-1">{{ id.hint }}</div>
          </button>
        </div>
      </div>
      <div v-if="draft.identity">
        <label class="block text-sm text-stone-400 mb-1">具体身份细节（穿越成谁/重生谁/自定义描述）</label>
        <textarea :value="draft.identityNote" @input="updateDraft('identityNote', $event.target.value)" rows="2"
          class="w-full bg-stone-900 border border-stone-700 rounded p-2 text-stone-200"
          placeholder="例如：穿越成云昊的同村少年 / 雪无痕重生回幼年 / 一柄化形的剑……"></textarea>
      </div>
      <div class="grid grid-cols-3 gap-2">
        <div>
          <label class="block text-sm text-stone-400 mb-1">姓名</label>
          <input :value="draft.name" @input="updateDraft('name', $event.target.value)" class="w-full bg-stone-900 border border-stone-700 rounded p-2" placeholder="无名" />
        </div>
        <div>
          <label class="block text-sm text-stone-400 mb-1">性别</label>
          <select :value="draft.gender" @change="updateDraft('gender', $event.target.value)" class="w-full bg-stone-900 border border-stone-700 rounded p-2">
            <option>男</option><option>女</option><option>其他</option>
          </select>
        </div>
        <div>
          <label class="block text-sm text-stone-400 mb-1">年龄（6-15）</label>
          <input :value="draft.age" @input="updateDraft('age', Number($event.target.value) || 0)" type="number" min="6" max="15" class="w-full bg-stone-900 border border-stone-700 rounded p-2" />
        </div>
      </div>
      <div>
        <label class="block text-sm text-stone-400 mb-1">出身地</label>
        <input :value="draft.origin" @input="updateDraft('origin', $event.target.value)" class="w-full bg-stone-900 border border-stone-700 rounded p-2"
          placeholder="云溪镇 / 玄冥城 / 天衡城 / 某宗门辖地……" />
      </div>
      <div>
        <label class="block text-sm text-stone-400 mb-1">出身背景</label>
        <input :value="draft.background" @input="updateDraft('background', $event.target.value)" class="w-full bg-stone-900 border border-stone-700 rounded p-2"
          placeholder="平民 / 小家族子弟 / 宗门子弟 / 玄冥圣殿相关 / 皇室旁支 / 孤儿……" />
      </div>
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

    <!-- 第二步：来处与秘密 -->
    <div v-else-if="step === 2" class="space-y-4">
      <div>
        <label class="block text-sm text-stone-400 mb-1">家庭状况</label>
        <input :value="draft.family" @input="updateDraft('family', $event.target.value)" class="w-full bg-stone-900 border border-stone-700 rounded p-2"
          placeholder="温暖和睦 / 严厉 / 孤儿 / 单亲 / 家族没落……" />
      </div>
      <div>
        <label class="block text-sm text-stone-400 mb-1">家族与魂师界的关系</label>
        <input :value="draft.background" @input="updateDraft('background', $event.target.value)" class="w-full bg-stone-900 border border-stone-700 rounded p-2"
          placeholder="家族曾有顶尖魂师已衰落 / 父母是普通魂师 / 玄冥圣殿成员后裔……" />
      </div>
      <div>
        <label class="block text-sm text-stone-400 mb-1">执念或秘密（会贯穿剧情）</label>
        <textarea :value="draft.secret" @input="updateDraft('secret', $event.target.value)" rows="2"
          class="w-full bg-stone-900 border border-stone-700 rounded p-2"
          placeholder="为家族复仇 / 寻找某物 / 一个不能告诉任何人的武魂变异……"></textarea>
      </div>
    </div>

    <!-- 第三步：你的特质 -->
    <div v-else-if="step === 3" class="space-y-4">
      <div>
        <label class="block text-sm text-stone-400 mb-1">外貌特征（2-4 个关键词）</label>
        <input :value="draft.traits" @input="updateDraft('traits', $event.target.value)" class="w-full bg-stone-900 border border-stone-700 rounded p-2"
          placeholder="瘦削，手上有茧，眼神早熟" />
      </div>
      <div>
        <label class="block text-sm text-stone-400 mb-1">性格基调（3 个词）</label>
        <input :value="draft.personality" @input="updateDraft('personality', $event.target.value)" class="w-full bg-stone-900 border border-stone-700 rounded p-2"
          placeholder="沉稳，重义，多疑" />
      </div>
      <div>
        <label class="block text-sm text-stone-400 mb-2">对"变强"的渴望程度：{{ draft.desire }} / 10</label>
        <input :value="draft.desire" @input="updateDraft('desire', Number($event.target.value) || 0)" type="range" min="0" max="10" class="w-full accent-amber-500" />
        <div class="flex justify-between text-xs text-stone-500"><span>0 随波逐流</span><span>10 不惜一切代价</span></div>
      </div>
    </div>

    <!-- 第四步：武魂与天赋 -->
    <div v-else-if="step === 4" class="space-y-4">
      <div>
        <p class="text-sm text-stone-400 mb-2">选择天赋档（决定先天魂力与武魂品质，成长速率而非上限）</p>
        <div class="grid grid-cols-2 gap-2">
          <button v-for="t in TIERS" :key="t.key"
            @click="pickTier(t.key)"
            class="text-left p-3 rounded border transition"
            :class="draft.talentTier === t.key ? 'border-amber-500 bg-amber-900/30' : 'border-stone-700 bg-stone-900 hover:border-stone-500'">
            <div class="font-medium text-stone-200">{{ t.key }} <span class="text-xs text-amber-400">{{ t.range }}</span></div>
            <div class="text-xs text-stone-400 mt-1">{{ t.note }}</div>
          </button>
        </div>
      </div>
      <div v-if="draft.talentTier" class="grid grid-cols-2 gap-2">
        <div>
          <label class="block text-sm text-stone-400 mb-1">先天魂力</label>
          <input :value="draft.innateSoulPower" @input="updateDraft('innateSoulPower', $event.target.value === '' ? null : Number($event.target.value))" type="number" min="1" max="10"
            class="w-full bg-stone-900 border border-stone-700 rounded p-2" />
        </div>
        <div>
          <label class="block text-sm text-stone-400 mb-1">武魂类型</label>
          <select :value="draft.wuhunType" @change="updateDraft('wuhunType', $event.target.value)" class="w-full bg-stone-900 border border-stone-700 rounded p-2">
            <option>器武魂</option><option>兽武魂</option><option>植物武魂</option>
            <option>食物系</option><option>辅助系</option><option>变异武魂</option>
          </select>
        </div>
      </div>
      <div>
        <label class="block text-sm text-stone-400 mb-1">武魂（可自选或按出身性格生成）</label>
        <input :value="draft.wuhun" @input="updateDraft('wuhun', $event.target.value)" class="w-full bg-stone-900 border border-stone-700 rounded p-2"
          placeholder="白灵藤 / 烈目白虎 / 琉璃塔……" />
      </div>
      <div>
        <label class="block text-sm text-stone-400 mb-1">初始发展方向</label>
        <div class="flex flex-wrap gap-2">
          <button v-for="dir in ['强攻系','敏攻系','控制系','辅助系','防御系','食物系']" :key="dir"
            @click="updateDraft('developmentDirection', dir)"
            class="px-3 py-1 rounded-full border text-sm"
            :class="draft.developmentDirection === dir ? 'border-amber-500 bg-amber-900/40 text-amber-200' : 'border-stone-700 text-stone-400'">
            {{ dir }}
          </button>
        </div>
      </div>
      <p class="text-xs text-stone-500">约束：即便选怪物档，开局也控制在魂兽大陆同级顶级天才范围内——不得开局满环、不得开局神级能力、不得携带玄机阁以外位面的功法。</p>
    </div>

    <!-- 第五步：初始财富 -->
    <div v-else class="space-y-4">
      <div>
        <label class="block text-sm text-stone-400 mb-1">初始金魂币（按出身）</label>
        <input :value="draft.gold" @input="updateDraft('gold', $event.target.value === '' ? '' : Number($event.target.value))" type="number" min="0"
          class="w-full bg-stone-900 border border-stone-700 rounded p-2" :placeholder="'平民 5-10 / 小家族 100-300 / 宗门 500+'" />
      </div>
      <div>
        <label class="block text-sm text-stone-400 mb-1">特殊物品（逗号分隔，如：祖传魂骨碎片/神秘地图/推荐信）</label>
        <input :value="draft.specialItems" @input="updateDraft('specialItems', $event.target.value)" class="w-full bg-stone-900 border border-stone-700 rounded p-2" />
      </div>
      <div class="grid grid-cols-2 gap-2">
        <div>
          <label class="block text-sm text-stone-400 mb-1">游玩方向</label>
          <select :value="draft.direction" @change="updateDraft('direction', $event.target.value)" class="w-full bg-stone-900 border border-stone-700 rounded p-2">
            <option v-for="d in DIRECTIONS" :key="d">{{ d }}</option>
          </select>
        </div>
        <div>
          <label class="block text-sm text-stone-400 mb-1">时间线绑定</label>
          <select :value="draft.timelineBinding" @change="updateDraft('timelineBinding', $event.target.value)" class="w-full bg-stone-900 border border-stone-700 rounded p-2">
            <option v-for="b in BINDINGS" :key="b">{{ b }}</option>
          </select>
        </div>
      </div>
      <p class="text-xs text-stone-500">时间线：高度绑定=大陆既定剧情固定时间触发；半绑定=等你行动进度；完全脱钩=只作背景。</p>
    </div>

    <div class="mt-8 flex justify-between">
      <button @click="prevStep" :disabled="step === 1"
        class="px-4 py-2 rounded bg-stone-800 text-stone-300 disabled:opacity-30">上一步</button>
      <button v-if="step < total" @click="nextStep"
        class="px-4 py-2 rounded bg-amber-600 text-stone-950 font-medium">下一步</button>
      <button v-else @click="emit('complete', buildArchive())"
        class="px-4 py-2 rounded bg-amber-600 text-stone-950 font-medium">查看档案卡</button>
    </div>
  </div>
</template>
