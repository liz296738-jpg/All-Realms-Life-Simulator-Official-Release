// API 客户端 + SSE 流式消费
// postSse 用 fetch 读取 POST 响应的 SSE 流，回调 onText/onDelta/onDone。

// 统一的 JSON 响应处理：非 2xx 时抛带后端 detail 的错误，而不是悄悄当作成功
async function parseJson(resp) {
  const body = await resp.json().catch(() => ({}))
  if (!resp.ok) throw new Error(body.detail || `请求失败 ${resp.status}`)
  return body
}

export async function postSse(url, body, handlers, timeoutMs = 90000) {
  const controller = new AbortController()
  let timer
  let cancelled = false
  const timeout = new Promise((_, rej) => {
    timer = setTimeout(() => {
      cancelled = true
      controller.abort() // 真正断开 fetch，避免后台继续读取
      rej(new Error('请求超时，请刷新后重试'))
    }, timeoutMs)
  })
  const stream = (async () => {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.detail || `请求失败 ${resp.status}`)
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    let completed = false // 是否收到后端的 done（回合已完整落账）
    while (true) {
      let chunk
      try {
        chunk = await reader.read()
      } catch {
        break // abort() 后流被取消，静默结束
      }
      if (chunk.done) break
      buf += decoder.decode(chunk.value, { stream: true })
      let idx
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const raw = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        const lines = raw.split('\n')
        const evt = (lines.find(l => l.startsWith('event:')) || 'event: message').slice(7).trim()
        const dataLine = lines.find(l => l.startsWith('data:'))
        if (!dataLine) continue
        const data = JSON.parse(dataLine.slice(5).trim())
        if (cancelled) break
        if (evt === 'text' && handlers.onText) handlers.onText(data.content)
        else if (evt === 'delta' && handlers.onDelta) handlers.onDelta(data)
        else if (evt === 'done') completed = true
        else if (evt === 'error') throw new Error(data.message || '服务器返回错误')
      }
    }
    // 只有收到后端 done 才认为回合完整；被中途掐断（无 done、未取消）按失败抛错，
    // 否则玩家会看到"没报错的半截回合"，且残篇可能被当作完整回合归档。
    if (!cancelled && !completed) throw new Error('生成被中断，请重试')
    if (!cancelled && handlers.onDone) handlers.onDone()
  })()
  try {
    return await Promise.race([stream, timeout])
  } finally {
    clearTimeout(timer)
  }
}

// GET JSON 请求（世界列表）：带超时与 abort
async function getJson(url, timeoutMs = 15000) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    let resp
    try {
      resp = await fetch(url, { signal: controller.signal })
    } catch {
      throw new Error('请求超时或网络中断，请重试')
    }
    return await parseJson(resp)
  } finally {
    clearTimeout(timer)
  }
}

// multipart/form-data 请求（上传小说建世界）：不手动设 Content-Type，
// 让浏览器自动带 multipart boundary；耗时较长故超时放宽到 180s。
async function postForm(url, formData, timeoutMs = 180000) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    let resp
    try {
      resp = await fetch(url, { method: 'POST', body: formData, signal: controller.signal })
    } catch {
      throw new Error('请求超时或网络中断，请重试')
    }
    return await parseJson(resp)
  } finally {
    clearTimeout(timer)
  }
}

// 普通 JSON 请求（激活/查询）：带超时与 abort，避免后端不可达时把用户
// 卡在"处理中"状态无限等待。
async function postJson(url, body, timeoutMs = 15000) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    let resp
    try {
      resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
    } catch {
      throw new Error('请求超时或网络中断，请重试')
    }
    return await parseJson(resp)
  } finally {
    clearTimeout(timer)
  }
}

export const api = {
  health: () => fetch('/api/health').then(parseJson),
  saves: (client_id) => fetch(`/api/saves?client_id=${encodeURIComponent(client_id || '')}`).then(parseJson),
  save: (session_id) =>
    fetch('/api/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id }) }).then(parseJson),
  resume: (session_id) =>
    fetch('/api/resume', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id }) }).then(parseJson),
  undo: (session_id) =>
    fetch('/api/undo', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id }) }).then(parseJson),
  load: (savepoint_id) =>
    fetch('/api/load', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ savepoint_id }) }).then(parseJson),
  del: (session_id) =>
    fetch('/api/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id }) }).then(parseJson),
  export: (session_id) =>
    fetch('/api/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id }) }).then(parseJson),
  activate: ({ code, client_id }) => postJson('/api/activate', { code, client_id }),
  entitlement: ({ client_id, code }) => postJson('/api/entitlement', { client_id, code }),
  // 世界系统
  worlds: (client_id) => getJson(`/api/worlds?client_id=${encodeURIComponent(client_id || '')}`),
  buildWorld: (formData) => postForm('/api/worlds/build', formData, 180000),
  deleteWorld: ({ world_id, client_id }) => postJson('/api/worlds/delete', { world_id, client_id }),
  updateNpcs: ({ session_id, client_id, npcs }) =>
    postJson('/api/update-npcs', { session_id, client_id, npcs }),
  extractNpcProfiles: ({ session_id, npc_names, client_id, api_key }) =>
    postJson('/api/extract-npc-profiles', { session_id, npc_names, client_id, api_key }, 30000),
  // 数据备份：导出全部世界+存档为 JSON 文件（下载用 blob）
  exportAll: ({ client_id }) =>
    fetch('/api/export-all', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id }),
    }).then(resp => {
      if (!resp.ok) return parseJson(resp)  // 抛错误
      return resp.blob()
    }),
  // 数据恢复：上传备份 JSON 文件
  importAll: (formData) => postForm('/api/import-all', formData, 60000),
}
