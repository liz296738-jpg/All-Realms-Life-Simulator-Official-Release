import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ breaks: true, linkify: false })

// 完整叙述 → markdown HTML（回合完成后渲染，供回合记录回放）
export function renderMd(text) {
  return md.render(text)
}

// 流式期间剥掉 markdown 残留符号，避免露出 ** 等未闭合标记
export function stripArtifacts(text) {
  return text
    .replace(/\*\*/g, '')
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
}

// 剥掉叙述末尾 AI 自带的选项块（【选项】A. B. C. D. 或自定义世界的裸选项连排）。
// 选项已由下方可折叠选项栏提供，正文里再混一份会"占用文字的显示位置"。
// 只裁最后一个【选项】之后的部分；正文中途出现"选项"字样不截断。
const OPTION_LINE_RE = /^\s*[A-Da-d][.、．]\s*/
export function stripOptionsBlock(text) {
  let t = (text || '').replace(/\r\n/g, '\n')
  const idx = t.lastIndexOf('【选项】')
  if (idx >= 0) t = t.slice(0, idx)
  const lines = t.split('\n')
  // 去掉结尾的空行与正文/选项之间的 --- 分隔行
  while (lines.length && /^\s*(?:---)?\s*$/.test(lines[lines.length - 1])) lines.pop()
  // 自定义世界可能没有【选项】标记：去掉结尾连排 ≥2 行的选项行
  let tail = 0
  for (let i = lines.length - 1; i >= 0; i--) {
    if (OPTION_LINE_RE.test(lines[i])) tail++
    else break
  }
  if (tail >= 2) lines.length -= tail
  return lines.join('\n').trim()
}
