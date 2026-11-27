<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  depthBounds,
  depthColorHex,
  edgeVectorFrom,
  exportGraphJson,
  exportSvgElement,
  formatMetricSize,
  metricSourceLabel,
} from '../graphUtils'
import type { GraphEdge, GraphEdgeFilter, GraphNode, SceneGraph } from '../types'

type LayoutMode = 'spatial' | 'layered'

const props = defineProps<{
  graph: SceneGraph | null
  sceneId: string
  edgeFilter: GraphEdgeFilter
  activeNodeId: string | null
  hoverNodeId: string | null
  hoverEdgeId: string | null
}>()

const emit = defineEmits<{
  'update:edgeFilter': [filter: GraphEdgeFilter]
  'select-node': [id: string | null]
  'hover-node': [id: string | null]
  'hover-edge': [id: string | null]
}>()

const layoutMode = ref<LayoutMode>('spatial')
const containerRef = ref<HTMLDivElement | null>(null)
const svgRef = ref<SVGSVGElement | null>(null)
const viewWidth = ref(800)
const viewHeight = ref(560)
const tx = ref(0)
const ty = ref(0)
const scale = ref(1)
const exporting = ref(false)
const pointerPos = ref<{ x: number; y: number }>({ x: 0, y: 0 })

let panning = false
let panMoved = false
let panStart = { x: 0, y: 0, tx: 0, ty: 0 }
let resizeObserver: ResizeObserver | null = null

const bounds = computed(() => depthBounds(props.graph))

const nodeMap = computed(() => {
  const map = new Map<string, GraphNode>()
  if (!props.graph) return map
  for (const node of props.graph.nodes) map.set(node.id, node)
  return map
})

const activeNode = computed(() => (props.activeNodeId ? nodeMap.value.get(props.activeNodeId) ?? null : null))

const spatialFrame = computed(() => {
  const padX = 56
  const padY = 48
  const availW = Math.max(120, viewWidth.value - padX * 2)
  const availH = Math.max(120, viewHeight.value - padY * 2)
  const fw = Math.max(1, props.graph?.frame.width ?? 16)
  const fh = Math.max(1, props.graph?.frame.height ?? 9)
  const ratio = fw / fh
  let w = availW
  let h = w / ratio
  if (h > availH) {
    h = availH
    w = h * ratio
  }
  const x = (viewWidth.value - w) / 2
  const y = (viewHeight.value - h) / 2
  return { x, y, w, h }
})

const depthColumns = computed(() => {
  const graph = props.graph
  if (!graph || graph.nodes.length === 0) return []
  const byDepth = new Map<number, GraphNode[]>()
  for (const node of graph.nodes) {
    const list = byDepth.get(node.depth) ?? []
    list.push(node)
    byDepth.set(node.depth, list)
  }
  const depths = [...byDepth.keys()].sort((a, b) => a - b)
  const padX = 72
  const padTop = 58
  const padBottom = 44
  const availW = Math.max(160, viewWidth.value - padX * 2)
  const availH = Math.max(140, viewHeight.value - padTop - padBottom)
  const colStep = depths.length > 1 ? availW / (depths.length - 1) : 0

  return depths.map((depth, colIndex) => {
    const nodes = [...(byDepth.get(depth) ?? [])].sort((a, b) => a.center[1] - b.center[1] || a.id.localeCompare(b.id))
    const x = depths.length > 1 ? padX + colIndex * colStep : viewWidth.value / 2
    const items = nodes.map((node, rowIndex) => {
      const y =
        nodes.length > 1 ? padTop + (rowIndex / (nodes.length - 1)) * availH : padTop + availH / 2
      return { node, x, y }
    })
    return { depth, colIndex, x, top: padTop - 22, bottom: viewHeight.value - padBottom + 16, items }
  })
})

const nodePositions = computed(() => {
  const map = new Map<string, { x: number; y: number; colIndex?: number }>()
  if (!props.graph) return map
  if (layoutMode.value === 'spatial') {
    const frame = spatialFrame.value
    for (const node of props.graph.nodes) {
      map.set(node.id, {
        x: frame.x + node.center[0] * frame.w,
        y: frame.y + node.center[1] * frame.h,
      })
    }
    return map
  }
  for (const col of depthColumns.value) {
    for (const item of col.items) {
      map.set(item.node.id, { x: item.x, y: item.y, colIndex: col.colIndex })
    }
  }
  return map
})

const visibleEdges = computed(() => {
  if (!props.graph) return []
  return props.graph.edges.filter((edge) => {
    if (props.edgeFilter === 'occluded') {
      return edge.occlusion.occluded || edge.occlusion.coplanarOverlap
    }
    if (props.edgeFilter === 'selected') {
      if (!props.activeNodeId) return edge.occlusion.occluded || edge.occlusion.coplanarOverlap
      return edge.u === props.activeNodeId || edge.v === props.activeNodeId
    }
    return true
  })
})

type RenderedEdge = {
  edge: GraphEdge
  path: string
  midX: number
  midY: number
  stroke: string
  strokeWidth: number
  opacity: number
  dashed: boolean
  highlighted: boolean
  showArrow: boolean
  showLabel: boolean
  labelText: string
  markerId: string
  zRank: number
}

function edgeGeometry(
  p1: { x: number; y: number; colIndex?: number },
  p2: { x: number; y: number; colIndex?: number },
  edge: GraphEdge,
) {
  const dx = p2.x - p1.x
  const dy = p2.y - p1.y
  const len = Math.hypot(dx, dy)
  if (len < 1e-3) {
    return { path: `M ${p1.x} ${p1.y} L ${p2.x} ${p2.y}`, midX: p1.x, midY: p1.y }
  }
  // Shorten endpoints slightly so arrowheads sit cleanly at node rims.
  const trim = Math.min(14, len * 0.25)
  const ux = dx / len
  const uy = dy / len
  const sx = p1.x + ux * trim
  const sy = p1.y + uy * trim
  const ex = p2.x - ux * trim
  const ey = p2.y - uy * trim

  if (layoutMode.value === 'layered') {
    const colSpan = Math.abs((p2.colIndex ?? 0) - (p1.colIndex ?? 0))
    if (colSpan > 1 || colSpan === 0) {
      const sign = edge.id.charCodeAt(0) % 2 === 0 ? 1 : -1
      const curve = colSpan === 0 ? 34 * sign : Math.min(64, 20 + colSpan * 14) * (dy >= 0 ? -1 : 1)
      const mx = (sx + ex) / 2
      const my = (sy + ey) / 2
      const nx = -uy
      const ny = ux
      const cx = mx + nx * curve
      const cy = my + ny * curve
      return {
        path: `M ${sx.toFixed(1)} ${sy.toFixed(1)} Q ${cx.toFixed(1)} ${cy.toFixed(1)} ${ex.toFixed(1)} ${ey.toFixed(1)}`,
        midX: 0.25 * sx + 0.5 * cx + 0.25 * ex,
        midY: 0.25 * sy + 0.5 * cy + 0.25 * ey,
      }
    }
  }
  return {
    path: `M ${sx.toFixed(1)} ${sy.toFixed(1)} L ${ex.toFixed(1)} ${ey.toFixed(1)}`,
    midX: (sx + ex) / 2,
    midY: (sy + ey) / 2,
  }
}

const renderedEdges = computed<RenderedEdge[]>(() => {
  const pos = nodePositions.value
  const activeId = props.activeNodeId
  const hoverN = props.hoverNodeId
  const hoverE = props.hoverEdgeId

  const list: RenderedEdge[] = []
  for (const edge of visibleEdges.value) {
    const isHoveredEdge = hoverE === edge.id
    const touchesActive = Boolean(activeId && (edge.u === activeId || edge.v === activeId))
    const touchesHover = Boolean(hoverN && (edge.u === hoverN || edge.v === hoverN))
    const highlighted = isHoveredEdge || touchesActive || touchesHover

    // Arrow direction: when an active node is selected and connected, orient from activeNode -> other;
    // otherwise for occlusion edges orient from occluder (u) -> occluded (v).
    const fromId = touchesActive && activeId ? activeId : edge.u
    const toId = fromId === edge.u ? edge.v : edge.u
    const pFrom = pos.get(fromId)
    const pTo = pos.get(toId)
    if (!pFrom || !pTo) continue

    const geom = edgeGeometry(pFrom, pTo, edge)
    const vec = edgeVectorFrom(edge, fromId)

    let stroke = '#94a3b8'
    let strokeWidth = 1.15
    let opacity = 0.18
    let dashed = true
    let markerId = 'arrow-muted'
    let zRank = 0

    if (edge.occlusion.occluded) {
      stroke = highlighted ? '#ff8585' : '#ff6b6b'
      strokeWidth = highlighted ? 3.0 : 2.1
      opacity = highlighted ? 0.96 : 0.82
      dashed = false
      markerId = 'arrow-occ'
      zRank = highlighted ? 4 : 2
    } else if (edge.occlusion.coplanarOverlap) {
      stroke = highlighted ? '#ffb876' : '#f4a261'
      strokeWidth = highlighted ? 2.8 : 2.0
      opacity = highlighted ? 0.95 : 0.78
      dashed = false
      markerId = 'arrow-coplanar'
      zRank = highlighted ? 3 : 1
    } else if (highlighted) {
      stroke = '#cbd5e1'
      strokeWidth = isHoveredEdge ? 2.2 : 1.7
      opacity = isHoveredEdge ? 0.95 : 0.78
      dashed = true
      markerId = 'arrow-active'
      zRank = 3
    }

    const showArrow = highlighted
    const showLabel = isHoveredEdge || touchesActive
    const distStr = edge.distance.toFixed(2)
    let labelText = `${vec.direction} · ${distStr}`
    if (edge.occlusion.occluded) {
      const pct = Math.round(edge.occlusion.overlapRatio * 100)
      labelText = `${vec.direction} · ${distStr} · ${pct}%`
    } else if (edge.occlusion.coplanarOverlap) {
      labelText = `${vec.direction} · 共面`
    }

    list.push({
      edge,
      path: geom.path,
      midX: geom.midX,
      midY: geom.midY,
      stroke,
      strokeWidth,
      opacity,
      dashed,
      highlighted,
      showArrow,
      showLabel,
      labelText,
      markerId,
      zRank,
    })
  }
  return list.sort((a, b) => a.zRank - b.zRank)
})

const renderedNodes = computed(() => {
  if (!props.graph) return []
  const pos = nodePositions.value
  const activeLayer = activeNode.value?.layerId ?? null
  return props.graph.nodes
    .map((node) => {
      const p = pos.get(node.id)
      if (!p) return null
      const isActive = node.id === props.activeNodeId
      const isHovered = node.id === props.hoverNodeId
      const sameLayerSibling = Boolean(activeLayer && node.layerId === activeLayer && !isActive)
      const color = depthColorHex(node.depth, bounds.value.min, bounds.value.max)
      const radius = isActive ? 11.5 : isHovered ? 10 : 8.5
      return {
        node,
        x: p.x,
        y: p.y,
        color,
        radius,
        isActive,
        isHovered,
        sameLayerSibling,
      }
    })
    .filter((item): item is NonNullable<typeof item> => item !== null)
})

const hoveredNode = computed(() => (props.hoverNodeId ? nodeMap.value.get(props.hoverNodeId) ?? null : null))
const hoveredEdge = computed(() =>
  props.hoverEdgeId && props.graph ? props.graph.edges.find((e) => e.id === props.hoverEdgeId) ?? null : null,
)

const hoveredEdgeInfo = computed(() => {
  const edge = hoveredEdge.value
  if (!edge) return null
  const fromId =
    props.activeNodeId && (edge.u === props.activeNodeId || edge.v === props.activeNodeId)
      ? props.activeNodeId
      : edge.u
  const vec = edgeVectorFrom(edge, fromId)
  const fromNode = nodeMap.value.get(fromId)
  const toNode = nodeMap.value.get(vec.otherId)
  const pct = Math.round(edge.occlusion.overlapRatio * 100)
  let occText = '无遮挡'
  if (edge.occlusion.occluded) {
    const occluderName = nodeMap.value.get(edge.occlusion.occluder ?? '')?.category ?? edge.occlusion.occluder
    occText = `${occluderName} 遮挡（重叠 ${pct}%）`
  } else if (edge.occlusion.coplanarOverlap) {
    occText = `共面重叠（${pct}%）`
  }
  return {
    fromLabel: fromNode?.category ?? fromId,
    toLabel: toNode?.category ?? vec.otherId,
    direction: vec.direction,
    angleDeg: vec.angleDeg,
    distance: edge.distance,
    depthDelta: vec.depthDelta,
    occText,
  }
})

const tooltipStyle = computed(() => {
  const pad = 14
  const maxX = Math.max(pad, viewWidth.value - 250)
  const maxY = Math.max(pad, viewHeight.value - 150)
  const left = Math.min(maxX, Math.max(pad, pointerPos.value.x + 14))
  const top = Math.min(maxY, Math.max(pad, pointerPos.value.y + 14))
  return { left: `${left}px`, top: `${top}px` }
})

function fitView() {
  tx.value = 0
  ty.value = 0
  scale.value = 1
}

function onWheel(event: WheelEvent) {
  const el = svgRef.value
  if (!el) return
  event.preventDefault()
  const rect = el.getBoundingClientRect()
  const mx = event.clientX - rect.left
  const my = event.clientY - rect.top
  const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12
  const nextScale = Math.min(5, Math.max(0.35, scale.value * factor))
  const ratio = nextScale / scale.value
  tx.value = mx - (mx - tx.value) * ratio
  ty.value = my - (my - ty.value) * ratio
  scale.value = nextScale
}

function onPointerDown(event: PointerEvent) {
  if (event.button !== 0) return
  const target = event.target as Element | null
  if (target?.closest('[data-node-id]')) return
  panning = true
  panMoved = false
  panStart = { x: event.clientX, y: event.clientY, tx: tx.value, ty: ty.value }
  try {
    svgRef.value?.setPointerCapture(event.pointerId)
  } catch {
    // Ignore synthetic pointer capture error
  }
}

function onPointerMove(event: PointerEvent) {
  const el = containerRef.value
  if (el) {
    const rect = el.getBoundingClientRect()
    pointerPos.value = { x: event.clientX - rect.left, y: event.clientY - rect.top }
  }
  if (!panning) return
  const dx = event.clientX - panStart.x
  const dy = event.clientY - panStart.y
  if (Math.hypot(dx, dy) > 3) panMoved = true
  tx.value = panStart.tx + dx
  ty.value = panStart.ty + dy
}

function onPointerUp(event: PointerEvent) {
  try {
    if (svgRef.value?.hasPointerCapture(event.pointerId)) {
      svgRef.value.releasePointerCapture(event.pointerId)
    }
  } catch {
    // Ignore
  }
  if (panning && !panMoved) {
    const target = event.target as Element | null
    if (!target?.closest('[data-node-id]')) {
      emit('select-node', null)
    }
  }
  panning = false
}

async function onExport(format: 'svg' | 'png' | 'json') {
  if (!props.graph || exporting.value) return
  if (format === 'json') {
    exportGraphJson(props.graph, props.sceneId || 'scene')
    return
  }
  if (!svgRef.value) return
  exporting.value = true
  try {
    await exportSvgElement(svgRef.value, `${props.sceneId || 'scene'}-graph-${layoutMode.value}`, format)
  } finally {
    exporting.value = false
  }
}

function syncSize() {
  const el = containerRef.value
  if (!el) return
  const w = el.clientWidth
  const h = el.clientHeight
  if (w > 0 && h > 0) {
    viewWidth.value = w
    viewHeight.value = h
  }
}

onMounted(() => {
  syncSize()
  if (containerRef.value) {
    resizeObserver = new ResizeObserver(syncSize)
    resizeObserver.observe(containerRef.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
})

watch(layoutMode, () => fitView())
</script>

<template>
  <section class="graph-canvas">
    <header class="graph-toolbar">
      <div class="seg-group" role="group" aria-label="拓扑布局">
        <button
          type="button"
          :class="{ active: layoutMode === 'spatial' }"
          @click="layoutMode = 'spatial'"
        >
          空间坐标 (x, y)
        </button>
        <button
          type="button"
          :class="{ active: layoutMode === 'layered' }"
          @click="layoutMode = 'layered'"
        >
          深度分层
        </button>
      </div>
      <div class="seg-group" role="group" aria-label="边过滤">
        <button
          type="button"
          :class="{ active: edgeFilter === 'all' }"
          @click="emit('update:edgeFilter', 'all')"
        >
          全部
        </button>
        <button
          type="button"
          :class="{ active: edgeFilter === 'occluded' }"
          @click="emit('update:edgeFilter', 'occluded')"
        >
          仅遮挡
        </button>
        <button
          type="button"
          :class="{ active: edgeFilter === 'selected' }"
          @click="emit('update:edgeFilter', 'selected')"
        >
          仅选中相关
        </button>
      </div>
      <div class="toolbar-actions">
        <button type="button" @click="fitView">适应画布</button>
        <button type="button" :disabled="!graph || exporting" @click="onExport('svg')">导出 SVG</button>
        <button type="button" :disabled="!graph || exporting" @click="onExport('png')">导出 PNG</button>
        <button type="button" :disabled="!graph" @click="onExport('json')">导出 JSON</button>
      </div>
    </header>

    <div ref="containerRef" class="canvas-stage">
      <p v-if="!graph || graph.nodes.length === 0" class="empty-tip">
        当前场景没有可识别的前景主体实例。
      </p>
      <svg
        v-else
        ref="svgRef"
        class="graph-svg"
        :viewBox="`0 0 ${viewWidth} ${viewHeight}`"
        @wheel="onWheel"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
      >
        <defs>
          <marker id="arrow-occ" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#ff8585" />
          </marker>
          <marker id="arrow-coplanar" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#ffb876" />
          </marker>
          <marker id="arrow-active" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#cbd5e1" />
          </marker>
          <marker id="arrow-muted" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto">
            <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#94a3b8" />
          </marker>
        </defs>

        <g :transform="`translate(${tx.toFixed(2)}, ${ty.toFixed(2)}) scale(${scale.toFixed(4)})`">
          <!-- Spatial layout reference frame -->
          <g v-if="layoutMode === 'spatial'" class="frame-guides">
            <rect
              :x="spatialFrame.x"
              :y="spatialFrame.y"
              :width="spatialFrame.w"
              :height="spatialFrame.h"
              fill="#191919"
              stroke="#333333"
              stroke-width="1"
              rx="4"
            />
            <line
              :x1="spatialFrame.x + spatialFrame.w * 0.5"
              :y1="spatialFrame.y"
              :x2="spatialFrame.x + spatialFrame.w * 0.5"
              :y2="spatialFrame.y + spatialFrame.h"
              stroke="#242424"
              stroke-dasharray="4 4"
            />
            <line
              :x1="spatialFrame.x"
              :y1="spatialFrame.y + spatialFrame.h * 0.5"
              :x2="spatialFrame.x + spatialFrame.w"
              :y2="spatialFrame.y + spatialFrame.h * 0.5"
              stroke="#242424"
              stroke-dasharray="4 4"
            />
            <text :x="spatialFrame.x + 4" :y="spatialFrame.y - 8" fill="#777" font-size="11">(0, 0)</text>
            <text
              :x="spatialFrame.x + spatialFrame.w - 4"
              :y="spatialFrame.y + spatialFrame.h + 15"
              fill="#777"
              font-size="11"
              text-anchor="end"
            >
              (1, 1) · {{ graph.frame.source === 'background' ? '背景画框' : '画布' }}
            </text>
          </g>

          <!-- Depth-layered column guides -->
          <g v-else class="layer-guides">
            <g v-for="col in depthColumns" :key="col.depth">
              <line
                :x1="col.x"
                :y1="col.top"
                :x2="col.x"
                :y2="col.bottom"
                stroke="#2a2a2a"
                stroke-dasharray="4 4"
              />
              <text :x="col.x" :y="col.top - 10" fill="#9a9a9a" font-size="11.5" text-anchor="middle">
                深度 {{ col.depth }}
              </text>
            </g>
          </g>

          <!-- Edges -->
          <g class="edges">
            <g v-for="item in renderedEdges" :key="item.edge.id">
              <path
                :d="item.path"
                fill="none"
                :stroke="item.stroke"
                :stroke-width="item.strokeWidth"
                :stroke-opacity="item.opacity"
                :stroke-dasharray="item.dashed ? '4 4' : undefined"
                :marker-end="item.showArrow ? `url(#${item.markerId})` : undefined"
                stroke-linecap="round"
              />
              <!-- Wide invisible hit path for easy hover -->
              <path
                :d="item.path"
                fill="none"
                stroke="transparent"
                stroke-width="14"
                class="edge-hit"
                @pointerenter="emit('hover-edge', item.edge.id)"
                @pointerleave="emit('hover-edge', null)"
              />
              <g v-if="item.showLabel" class="edge-label" pointer-events="none">
                <rect
                  :x="item.midX - item.labelText.length * 3.6 - 6"
                  :y="item.midY - 9"
                  :width="item.labelText.length * 7.2 + 12"
                  height="18"
                  rx="4"
                  fill="#141414"
                  fill-opacity="0.88"
                  :stroke="item.stroke"
                  stroke-opacity="0.55"
                  stroke-width="0.8"
                />
                <text
                  :x="item.midX"
                  :y="item.midY + 3.5"
                  fill="#ececec"
                  font-size="10.5"
                  text-anchor="middle"
                >
                  {{ item.labelText }}
                </text>
              </g>
            </g>
          </g>

          <!-- Nodes -->
          <g class="nodes">
            <g
              v-for="item in renderedNodes"
              :key="item.node.id"
              :data-node-id="item.node.id"
              class="node-group"
              @click.stop="emit('select-node', item.node.id)"
              @pointerenter="emit('hover-node', item.node.id)"
              @pointerleave="emit('hover-node', null)"
            >
              <!-- Same-layer sibling dashed outer ring -->
              <circle
                v-if="item.sameLayerSibling"
                :cx="item.x"
                :cy="item.y"
                :r="item.radius + 5"
                fill="none"
                stroke="#ffd166"
                stroke-width="1.5"
                stroke-dasharray="3 2"
                stroke-opacity="0.85"
              />
              <!-- Active / hover bright outer ring -->
              <circle
                v-if="item.isActive || item.isHovered"
                :cx="item.x"
                :cy="item.y"
                :r="item.radius + 4"
                fill="none"
                :stroke="item.isActive ? '#ffd166' : '#ffffff'"
                :stroke-width="item.isActive ? 2.4 : 1.6"
              />
              <circle
                :cx="item.x"
                :cy="item.y"
                :r="item.radius"
                :fill="item.color"
                stroke="#121212"
                stroke-width="1.8"
              />
              <!-- Compact category capsule -->
              <g pointer-events="none">
                <rect
                  :x="item.x - Math.max(22, item.node.category.length * 5.6 + 10)"
                  :y="item.y + item.radius + 5"
                  :width="Math.max(44, item.node.category.length * 11.2 + 20)"
                  height="19"
                  rx="9"
                  fill="#121212"
                  fill-opacity="0.82"
                  :stroke="item.isActive ? '#ffd166' : '#3a3a3a'"
                  stroke-width="0.9"
                />
                <text
                  :x="item.x"
                  :y="item.y + item.radius + 18"
                  :fill="item.isActive ? '#ffd166' : '#ececec'"
                  font-size="11"
                  text-anchor="middle"
                >
                  {{ item.node.category }}
                </text>
              </g>
            </g>
          </g>
        </g>
      </svg>

      <!-- Floating Tooltip -->
      <div v-if="hoveredNode" class="tooltip" :style="tooltipStyle">
        <div class="tooltip-title">
          <strong>{{ hoveredNode.category }}</strong>
          <span class="badge">深度 {{ hoveredNode.depth }}</span>
        </div>
        <div class="tooltip-row"><span>实例 ID</span><code>{{ hoveredNode.id }}</code></div>
        <div class="tooltip-row">
          <span>中心 (x, y)</span>
          <span>({{ hoveredNode.center[0].toFixed(3) }}, {{ hoveredNode.center[1].toFixed(3) }})</span>
        </div>
        <div class="tooltip-row">
          <span>度量尺寸</span>
          <span>
            {{ formatMetricSize(hoveredNode.metric.width, hoveredNode.metric.height) }}
            <em class="muted">({{ metricSourceLabel(hoveredNode.metric.source) }})</em>
          </span>
        </div>
        <div class="tooltip-row">
          <span>像素尺寸</span>
          <span>{{ Math.round(hoveredNode.pixelSize[0]) }} × {{ Math.round(hoveredNode.pixelSize[1]) }} px</span>
        </div>
      </div>

      <div v-else-if="hoveredEdgeInfo" class="tooltip" :style="tooltipStyle">
        <div class="tooltip-title">
          <strong>{{ hoveredEdgeInfo.fromLabel }} → {{ hoveredEdgeInfo.toLabel }}</strong>
        </div>
        <div class="tooltip-row">
          <span>方位 / 角度</span>
          <span>{{ hoveredEdgeInfo.direction }}（{{ hoveredEdgeInfo.angleDeg.toFixed(1) }}°）</span>
        </div>
        <div class="tooltip-row">
          <span>归一化距离</span>
          <span>{{ hoveredEdgeInfo.distance.toFixed(3) }}</span>
        </div>
        <div class="tooltip-row">
          <span>Δ 深度</span>
          <span>{{ hoveredEdgeInfo.depthDelta > 0 ? `+${hoveredEdgeInfo.depthDelta}` : hoveredEdgeInfo.depthDelta }}</span>
        </div>
        <div class="tooltip-row">
          <span>遮挡关系</span>
          <span>{{ hoveredEdgeInfo.occText }}</span>
        </div>
      </div>

      <div class="legend-bar">
        <span class="legend-item"><i class="dot" style="background: #f0a202" /> 浅层</span>
        <span class="legend-item"><i class="dot" style="background: #2ec4b6" /> 中层</span>
        <span class="legend-item"><i class="dot" style="background: #6c8cff" /> 深层</span>
        <span class="legend-item"><i class="line solid-red" /> 遮挡</span>
        <span class="legend-item"><i class="line solid-amber" /> 共面重叠</span>
        <span class="legend-item"><i class="line dashed-muted" /> 非遮挡</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.graph-canvas {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
  min-height: 0;
  background: #141414;
  color: #ececec;
}
.graph-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid #2a2a2a;
  background: #191919;
}
.seg-group {
  display: flex;
  padding: 2px;
  border-radius: 6px;
  background: #262626;
}
.seg-group button {
  border: 0;
  background: transparent;
  color: #cfcfcf;
  font: inherit;
  font-size: 12px;
  padding: 4px 9px;
  border-radius: 4px;
  cursor: pointer;
}
.seg-group button.active {
  background: #f0a202;
  color: #1a1a1a;
  font-weight: 600;
}
.toolbar-actions {
  margin-left: auto;
  display: flex;
  gap: 6px;
}
.toolbar-actions button {
  padding: 4px 8px;
  border: 1px solid #3d3d3d;
  border-radius: 4px;
  background: #262626;
  color: #e4e4e4;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.toolbar-actions button:hover:not(:disabled) {
  border-color: #f0a202;
  color: #f0a202;
}
.toolbar-actions button:disabled {
  opacity: 0.4;
  cursor: default;
}
.canvas-stage {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.graph-svg {
  display: block;
  width: 100%;
  height: 100%;
  cursor: grab;
  user-select: none;
  touch-action: none;
}
.graph-svg:active {
  cursor: grabbing;
}
.node-group {
  cursor: pointer;
}
.edge-hit {
  cursor: pointer;
}
.empty-tip {
  margin: 32px;
  color: #9a9a9a;
  font-size: 13px;
}
.tooltip {
  position: absolute;
  z-index: 10;
  min-width: 210px;
  max-width: 260px;
  padding: 8px 10px;
  border: 1px solid #3f3f3f;
  border-radius: 6px;
  background: rgb(22 22 22 / 95%);
  box-shadow: 0 8px 24px rgb(0 0 0 / 55%);
  font-size: 12px;
  pointer-events: none;
}
.tooltip-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
  padding-bottom: 5px;
  border-bottom: 1px solid #2d2d2d;
}
.badge {
  padding: 1px 6px;
  border-radius: 10px;
  background: #2d2d2d;
  color: #ffd166;
  font-size: 11px;
}
.tooltip-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  line-height: 1.55;
  color: #d6d6d6;
}
.tooltip-row > span:first-child {
  color: #8f8f8f;
}
.tooltip-row code {
  font-size: 11px;
  color: #cbd5e1;
}
.muted {
  font-style: normal;
  color: #8f8f8f;
}
.legend-bar {
  position: absolute;
  left: 10px;
  bottom: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 4px 10px;
  border-radius: 5px;
  background: rgb(16 16 16 / 82%);
  border: 1px solid #2a2a2a;
  font-size: 11px;
  color: #bdbdbd;
  pointer-events: none;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.line {
  width: 14px;
  height: 0;
  display: inline-block;
}
.solid-red {
  border-top: 2px solid #ff6b6b;
}
.solid-amber {
  border-top: 2px solid #f4a261;
}
.dashed-muted {
  border-top: 1.5px dashed #94a3b8;
}
</style>
