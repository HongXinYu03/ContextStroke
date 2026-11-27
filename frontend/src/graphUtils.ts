import type { GraphEdge, SceneGraph } from './types'

const DIRECTIONS = ['右', '右上', '上', '左上', '左', '左下', '下', '右下'] as const

export function wrapAngle(angle: number): number {
  const wrapped = (((angle + 180) % 360) + 360) % 360 - 180
  return wrapped === -180 ? 180 : wrapped
}

export function directionLabel(angleDeg: number, distance: number): string {
  if (distance <= 1e-9) return '重合'
  const mod = (((angleDeg + 22.5) % 360) + 360) % 360
  const index = Math.floor(mod / 45) % 8
  return DIRECTIONS[index] ?? '右'
}

export type EdgeVector = {
  dx: number
  dy: number
  angleDeg: number
  direction: string
  otherId: string
  depthDelta: number
}

/**
 * Antisymmetric vector read matching backend `SceneEdge.vector_from`.
 * Returns vector pointing from `nodeId` to the other endpoint.
 */
export function edgeVectorFrom(edge: GraphEdge, nodeId: string): EdgeVector {
  if (nodeId === edge.u) {
    return {
      dx: edge.dx,
      dy: edge.dy,
      angleDeg: edge.angleDeg,
      direction: edge.direction,
      otherId: edge.v,
      depthDelta: edge.depthDelta,
    }
  }
  const angleDeg = Number(wrapAngle(edge.angleDeg + 180).toFixed(3))
  return {
    dx: -edge.dx,
    dy: -edge.dy,
    angleDeg,
    direction: directionLabel(angleDeg, edge.distance),
    otherId: edge.u,
    depthDelta: -edge.depthDelta,
  }
}

function lerpChannel(a: number, b: number, t: number): number {
  return Math.round(a + (b - a) * t)
}

function toHex(r: number, g: number, b: number): string {
  return `#${[r, g, b].map((c) => c.toString(16).padStart(2, '0')).join('')}`
}

const COLOR_SHALLOW: [number, number, number] = [0xf0, 0xa2, 0x02] // #f0a202
const COLOR_MID: [number, number, number] = [0x2e, 0xc4, 0xb6] // #2ec4b6
const COLOR_DEEP: [number, number, number] = [0x6c, 0x8c, 0xff] // #6c8cff

export function depthColorHex(depth: number, minDepth: number, maxDepth: number): string {
  if (maxDepth <= minDepth) return toHex(...COLOR_SHALLOW)
  const t = Math.max(0, Math.min(1, (depth - minDepth) / (maxDepth - minDepth)))
  if (t <= 0.5) {
    const k = t * 2
    return toHex(
      lerpChannel(COLOR_SHALLOW[0], COLOR_MID[0], k),
      lerpChannel(COLOR_SHALLOW[1], COLOR_MID[1], k),
      lerpChannel(COLOR_SHALLOW[2], COLOR_MID[2], k),
    )
  }
  const k = (t - 0.5) * 2
  return toHex(
    lerpChannel(COLOR_MID[0], COLOR_DEEP[0], k),
    lerpChannel(COLOR_MID[1], COLOR_DEEP[1], k),
    lerpChannel(COLOR_MID[2], COLOR_DEEP[2], k),
  )
}

export function depthColorNumber(depth: number, minDepth: number, maxDepth: number): number {
  return Number.parseInt(depthColorHex(depth, minDepth, maxDepth).slice(1), 16)
}

export function depthBounds(graph: SceneGraph | null): { min: number; max: number } {
  if (!graph || graph.nodes.length === 0) return { min: 1, max: 1 }
  let min = Infinity
  let max = -Infinity
  for (const node of graph.nodes) {
    if (node.depth < min) min = node.depth
    if (node.depth > max) max = node.depth
  }
  return { min, max }
}

export function formatMetricSize(width: number | null, height: number | null): string {
  if (width === null && height === null) return '—'
  const w = width === null ? '?' : `${Number(width.toFixed(2))}m`
  const h = height === null ? '?' : `${Number(height.toFixed(2))}m`
  return `${w} × ${h}`
}

export function metricSourceLabel(source: string): string {
  if (source === 'manual') return '手填'
  if (source === 'estimated') return '估算'
  if (source === 'mixed') return '混合'
  if (source === 'derived') return '自动推算'
  return '未设置'
}

function triggerDownload(url: string, filename: string, revoke = true) {
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  if (revoke) setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function exportGraphJson(graph: SceneGraph, sceneId: string): void {
  const payload = JSON.stringify(graph, null, 2)
  const blob = new Blob([payload], { type: 'application/json;charset=utf-8' })
  triggerDownload(URL.createObjectURL(blob), `${sceneId}-scene-graph.json`)
}

export async function exportSvgElement(
  svgEl: SVGSVGElement,
  filename: string,
  format: 'svg' | 'png',
): Promise<void> {
  const rect = svgEl.getBoundingClientRect()
  const width = Math.max(1, Math.round(rect.width || 960))
  const height = Math.max(1, Math.round(rect.height || 640))

  const clone = svgEl.cloneNode(true) as SVGSVGElement
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  clone.setAttribute('width', String(width))
  clone.setAttribute('height', String(height))
  if (!clone.getAttribute('viewBox')) {
    clone.setAttribute('viewBox', `0 0 ${width} ${height}`)
  }

  // Inline background rect and font style so standalone SVG / PNG looks identical.
  const styleEl = document.createElementNS('http://www.w3.org/2000/svg', 'style')
  styleEl.textContent = `
    text { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; }
  `
  clone.insertBefore(styleEl, clone.firstChild)

  const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
  bg.setAttribute('x', '0')
  bg.setAttribute('y', '0')
  bg.setAttribute('width', String(width))
  bg.setAttribute('height', String(height))
  bg.setAttribute('fill', '#141414')
  clone.insertBefore(bg, styleEl.nextSibling)

  const serializer = new XMLSerializer()
  const source = serializer.serializeToString(clone)

  if (format === 'svg') {
    const blob = new Blob([source], { type: 'image/svg+xml;charset=utf-8' })
    triggerDownload(URL.createObjectURL(blob), `${filename}.svg`)
    return
  }

  const svgBlob = new Blob([source], { type: 'image/svg+xml;charset=utf-8' })
  const svgUrl = URL.createObjectURL(svgBlob)
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const image = new Image()
      image.onload = () => resolve(image)
      image.onerror = () => reject(new Error('无法渲染拓扑图 PNG'))
      image.src = svgUrl
    })
    const scale = 2
    const canvas = document.createElement('canvas')
    canvas.width = width * scale
    canvas.height = height * scale
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('浏览器不支持 Canvas 2D')
    ctx.scale(scale, scale)
    ctx.fillStyle = '#141414'
    ctx.fillRect(0, 0, width, height)
    ctx.drawImage(img, 0, 0, width, height)
    const pngUrl = canvas.toDataURL('image/png')
    triggerDownload(pngUrl, `${filename}.png`, false)
  } finally {
    URL.revokeObjectURL(svgUrl)
  }
}
