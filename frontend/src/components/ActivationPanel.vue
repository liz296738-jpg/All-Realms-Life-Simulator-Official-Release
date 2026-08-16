<script setup>
import { ref, watch } from 'vue'
import { api } from '../api'
import { ui, clientId, entitlement, refreshEntitlement, setSubscriptionCode, markEntitlement, setActivationOpen, fmtDate } from '../store'
import wechatQr from '../assets/wechat-pay-qr.jpg'

const code = ref('')
const busy = ref(false)
const msg = ref('')            // 错误提示
const okMsg = ref('')          // 成功提示
const copied = ref(false)

function close() {
  if (busy.value) return
  setActivationOpen(false)
  msg.value = ''
  okMsg.value = ''
  copied.value = false
}

// 打开弹窗时重新拉取订阅/试玩状态：门禁 403 后试玩次数已变化，避免展示过期数字
watch(() => ui.activationOpen, (open) => {
  if (open) {
    msg.value = ''
    okMsg.value = ''
    refreshEntitlement()
  }
})

async function submit() {
  const c = code.value.trim()
  if (!c || busy.value) return
  busy.value = true
  msg.value = ''
  okMsg.value = ''
  try {
    const d = await api.activate({ code: c, client_id: clientId() })
    markEntitlement({ paid: true, paidUntil: d.paid_until, trialUsed: 0 })
    setSubscriptionCode(d.code)
    setActivationOpen(true, '')  // 保持面板开启，清除门禁错误提示
    code.value = ''
    okMsg.value = `激活成功！订阅至 ${fmtDate(d.paid_until)}。`
  } catch (e) {
    msg.value = e.message
  } finally {
    busy.value = false
  }
}

async function copyText(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
    throw new Error('no-clipboard-api')
  } catch {
    // 降级：选中文本 + execCommand 复制（非 https / 权限受限等旧环境）
    try {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      const ok = document.execCommand('copy')
      document.body.removeChild(ta)
      return ok
    } catch {
      return false
    }
  }
}

async function copyCode() {
  const c = entitlement.subscriptionCode
  if (!c) return
  if (await copyText(c)) {
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } else {
    msg.value = '自动复制失败，请长按激活码文字手动复制后保存'
  }
}


const trialLeft = () => Math.max(0, entitlement.trialLimit - entitlement.trialUsed)
</script>

<template>
  <div v-if="ui.activationOpen" class="fixed inset-0 z-50 bg-black/70 flex items-center justify-center px-4"
    @click.self="close">
    <div class="w-full max-w-sm rounded-xl border border-stone-700 bg-stone-900 p-5 shadow-2xl max-h-[90vh] overflow-y-auto">
      <div class="flex items-center justify-between mb-4">
        <h2 class="font-medium text-amber-200">订阅 / 激活码</h2>
        <button @click="close" class="text-stone-500 hover:text-stone-300 text-lg leading-none">✕</button>
      </div>

      <!-- 当前状态 -->
      <div class="text-sm mb-4">
        <p v-if="entitlement.paid" class="text-emerald-400">
          ✓ 已订阅 · 无限游玩（至 {{ fmtDate(entitlement.paidUntil) }}）
        </p>
        <p v-else class="text-stone-300">
          免费试玩中 · 剩余 {{ trialLeft() }} / {{ entitlement.trialLimit }} 回合
        </p>
      </div>

      <!-- 本机激活码（多端共用）：已订阅即展示，可随时复制 -->
      <div v-if="entitlement.paid && entitlement.subscriptionCode"
        class="mb-4 rounded-md border border-amber-800/50 bg-amber-950/30 p-3">
        <p class="text-[11px] text-amber-300/90 mb-1">你的激活码（同一天内换设备 / 换浏览器，重新输入它即可恢复，请保存）</p>
        <div class="flex items-center gap-2">
          <code class="flex-1 break-all font-mono text-xs text-amber-100 leading-relaxed select-all">
            {{ entitlement.subscriptionCode }}
          </code>
          <button @click="copyCode"
            class="shrink-0 text-xs px-2 py-1 rounded border border-amber-700 text-amber-300 hover:bg-amber-800/40 transition">
            {{ copied ? '已复制 ✓' : '复制' }}
          </button>
        </div>
        <p class="text-[11px] text-stone-500 mt-1">每个激活码对应一天，从对应日起 30 天内可激活；激活后至对应日 + 30 天到期。</p>
      </div>

      <!-- 触发原因 -->
      <p v-if="ui.activationMsg" class="text-xs text-amber-300/90 bg-amber-950/40 border border-amber-800/40 rounded p-2 mb-3">
        {{ ui.activationMsg }}
      </p>

      <!-- 主推通道（小红书自动发货，置顶） -->
      <div class="mb-3 rounded-lg border-2 border-red-500/60 bg-red-500/15 p-3 text-center">
        <p class="text-sm font-bold text-red-300 mb-2">⭐ 推荐：最快获取，24小时自动发货</p>
        <a href="http://xhslink.cn/o/7t8lsg92E0e" target="_blank" rel="noopener noreferrer"
          class="inline-block px-5 py-2.5 rounded-lg bg-red-500 text-white font-semibold hover:bg-red-400 transition text-sm">
          📕 去小红书店铺购买
        </a>
        <p class="text-[11px] text-red-300/80 mt-1.5">付款后自动发货激活码，无需等待人工回复</p>
      </div>

      <!-- 备用通道（微信扫码，下移） -->
      <div class="mb-3 rounded-lg border border-stone-700 bg-stone-800/60 p-3 text-center">
        <p class="text-[11px] text-stone-500 mb-2">—— 备用通道 ——</p>
        <img :src="wechatQr" alt="微信收款码" class="w-32 h-32 mx-auto rounded object-contain bg-white p-1 mb-2" />
        <p class="text-sm text-stone-200 font-medium mb-1">微信扫码支付 1 元</p>
        <p class="text-xs text-stone-400 leading-relaxed">
          扫码支付 1 元后，在支付记录详情里点<span class="text-amber-300 font-medium">「联系收款方」</span>，<br/>
          告诉对方要激活码即可——确认收款后把<b>当天</b>的码回复给你。<br/>
          在对应日起 30 天内激活即可，激活后无限游玩至到期日，到期后再领新码续费。
        </p>
      </div>

      <!-- 微信防催更免责声明（核心） -->
      <p class="mb-2 rounded-md border border-orange-500/60 bg-orange-500/10 p-2.5 text-xs leading-relaxed text-orange-300 font-medium">
        ⚠️ 温馨提示：博主回复微信信息不及时，通常只能在每天晚上统一回复并发放激活码。如果您比较着急游玩，请务必使用上方的小红书自动发货通道！
      </p>

      <!-- 防风控提示 -->
      <p class="mb-2 rounded-md border border-amber-700/40 bg-amber-950/30 p-2.5 text-xs leading-relaxed text-amber-400">
        ⚠️ 温馨提示：如果微信扫码提示风险、无法支付或长时间未回复，请务必使用上方【小红书】推荐通道自动获取激活码。
      </p>

      <!-- 输码激活 -->
      <input v-model="code" @keyup.enter="submit" :disabled="busy"
        placeholder="粘贴激活码，如 XXXX-XXXX-XXXX"
        class="w-full mb-2 px-3 py-2 rounded-md bg-stone-800 border border-stone-600 text-stone-100 placeholder-stone-500 focus:border-amber-500 outline-none" />
      <button @click="submit" :disabled="busy"
        class="w-full py-2.5 rounded-lg bg-amber-600 text-stone-950 font-medium hover:bg-amber-500 disabled:opacity-50 transition">
        {{ busy ? '激活中…' : '激活' }}
      </button>

      <p v-if="okMsg" class="text-xs text-emerald-400 mt-3">{{ okMsg }}</p>
      <p v-if="msg" class="text-xs text-red-400 mt-3">{{ msg }}</p>
      <p class="text-[11px] text-stone-600 mt-3 text-center">
        激活码不泄露设备信息；请勿把激活码随意转发给别人。
      </p>
    </div>
  </div>
</template>
