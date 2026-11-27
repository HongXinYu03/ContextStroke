<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { depthBounds, depthColorHex, edgeVectorFrom, metricSourceLabel } from '../graphUtils'
import type { GraphEdge, GraphNode, SceneGraph } from '../types'

const props = defineProps<{
  graph: SceneGraph | null
  loading: boolean
  error: string
  activeNodeId: string | null
  hoverNodeId: string | null
  hoverEdgeId: string | null
}>()

const emit = defineEmits<{
  'select-node': [id: string | null]
  'hover-node': [id: string | null]
  'hover-edge': [id: string | null]
  annotate: [
    payload: {
      instanceId: string
      category?: string | null
      metric_width?: number | null
      metric_height?: number | null
    },
  ]
  'update-mpp': [metersPerPixel: number | null]
}>()

const onlySelectedEdges = ref(false)
const onlyOccludedEdges = ref(false)
const mppInput = ref('')

const bounds = computed(() => depthBounds(props.graph))

const nodeMap = computed(() => {
  const map = new Map<string, GraphNode>()
  if (!props.graph) return map
  for (const node of props.graph.nodes) map.set(node.id, node)
  return map
})

const occludedCount = computed(
  () => props.graph?.edges.filter((edge) => edge.occlusion.occluded).length ?? 0,
)

const mppSourceText = computed(() => metricSourceLabel(props.graph?.metersPerPixelSource ?? ''))

watch(
  () => props.graph?.metersPerPixel,
  (val) => {
    mppInput.value = val !== null && val !== undefined ? String(val) : ''
  },
  { immediate: true },
)

function commitMpp() {
  const trimmed = mppInput.value.trim()
  if (!trimmed) {
    if (props.graph?.metersPerPixelSource === 'manual') {
      emit('update-mpp', null)
    } else if (props.graph?.metersPerPixel !== null && props.graph?.metersPerPixel !== undefined) {
      mppInput.value = String(props.graph.metersPerPixel)
    }
    return
  }
  const parsed = Number(trimmed)
  if (!Number.isFinite(parsed) || parsed <= 0) {
    mppInput.value =
      props.graph?.metersPerPixel !== null && props.graph?.metersPerPixel !== undefined
        ? String(props.graph.metersPerPixel)
        : ''
    return
  }
  if (props.graph?.metersPerPixel === parsed && props.graph?.metersPerPixelSource === 'manual') return
  emit('update-mpp', parsed)
}

function clearMpp() {
  mppInput.value = ''
  emit('update-mpp', null)
}

function commitCategory(node: GraphNode, event: Event) {
  const value = (event.target as HTMLInputElement).value.trim()
  if (value === node.category) return
  emit('annotate', {
    instanceId: node.id,
    category: value === '' ? null : value,
  })
}

function commitMetric(node: GraphNode, field: 'metric_width' | 'metric_height', event: Event) {
  const input = event.target as HTMLInputElement
  const trimmed = input.value.trim()
  const currentVal = field === 'metric_width' ? node.metric.width : node.metric.height
  const currentSource = field === 'metric_width' ? node.metric.widthSource : node.metric.heightSource

  if (!trimmed) {
    if (currentSource === 'manual') {
      emit('annotate', { instanceId: node.id, [field]: null })
    }
    return
  }
  const parsed = Number(trimmed)
  if (!Number.isFinite(parsed) || parsed <= 0) {
    input.value = currentSource === 'manual' && currentVal !== null ? String(currentVal) : ''
    return
  }
  if (currentSource === 'manual' && currentVal === parsed) return
  emit('annotate', { instanceId: node.id, [field]: parsed })
}

function metricInputValue(node: GraphNode, dim: 'width' | 'height'): string {
  const val = dim === 'width' ? node.metric.width : node.metric.height
  const source = dim === 'width' ? node.metric.widthSource : node.metric.heightSource
  if (source === 'manual' && val !== null) return String(val)
  return ''
}

function metricPlaceholder(node: GraphNode, dim: 'width' | 'height'): string {
  const val = dim === 'width' ? node.metric.width : node.metric.height
  const source = dim === 'width' ? node.metric.widthSource : node.metric.heightSource
  if (source === 'estimated' && val !== null) return `${Number(val.toFixed(2))} (估算)`
  return '未填'
}

type EdgeRow = {
  edge: GraphEdge
  fromLabel: string
  toLabel: string
  direction: string
  angleDeg: number
  distance: number
  depthDelta: number
  occBadge: string
  occKind: 'occludes' | 'occluded' | 'coplanar' | 'none'
}

const filteredEdges = computed<EdgeRow[]>(() => {
  if (!props.graph) return []
  const activeId = props.activeNodeId
  const rows: EdgeRow[] = []
  for (const edge of props.graph.edges) {
    if (onlyOccludedEdges.value && !edge.occlusion.occluded && !edge.occlusion.coplanarOverlap) continue
    if (onlySelectedEdges.value && activeId && edge.u !== activeId && edge.v !== activeId) continue

    const fromId = activeId && (edge.u === activeId || edge.v === activeId) ? activeId : edge.u
    const vec = edgeVectorFrom(edge, fromId)
    const fromNode = nodeMap.value.get(fromId)
    const toNode = nodeMap.value.get(vec.otherId)
    const pct = Math.round(edge.occlusion.overlapRatio * 100)

    let occBadge = ''
    let occKind: EdgeRow['occKind'] = 'none'
    if (edge.occlusion.occluded) {
      if (edge.occlusion.occluder === fromId) {
        occBadge = `挡住 · ${pct}%`
        occKind = 'occludes'
      } else {
        occBadge = `被挡 · ${pct}%`
        occKind = 'occluded'
      }
    } else if (edge.occlusion.coplanarOverlap) {
      occBadge = `共面 · ${pct}%`
      occKind = 'coplanar'
    }

    rows.push({
      edge,
      fromLabel: fromNode?.category ?? fromId,
      toLabel: toNode?.category ?? vec.otherId,
      direction: vec.direction,
      angleDeg: vec.angleDeg,
      distance: edge.distance,
      depthDelta: vec.depthDelta,
      occBadge,
      occKind,
    })
  }
  return rows
})
</script>

<template>
  <section class="graph-panel">
    <p v-if="loading && !graph" class="status">正在构建场景图…</p>
    <p v-else-if="error" class="status error">{{ error }}</p>
    <template v-else-if="graph">
      <!-- Overview -->
      <div class="overview">
        <div class="stats">
          <div class="stat">
            <span class="stat-val">{{ graph.nodes.length }}</span>
            <span class="stat-label">实例</span>
          </div>
          <div class="stat">
            <span class="stat-val">{{ graph.edges.length }}</span>
            <span class="stat-label">边</span>
          </div>
          <div class="stat">
            <span class="stat-val occ">{{ occludedCount }}</span>
            <span class="stat-label">遮挡</span>
          </div>
        </div>
        <div class="mpp-row">
          <label class="mpp-label">
            <span>米 / 像素</span>
            <span class="source-tag" :class="graph.metersPerPixelSource ?? 'none'">{{ mppSourceText }}</span>
          </label>
          <div class="mpp-controls">
            <input
              v-model="mppInput"
              type="text"
              inputmode="decimal"
              placeholder="如 0.002"
              @blur="commitMpp"
              @keydown.enter="($event.target as HTMLInputElement).blur()"
            />
            <button
              v-if="graph.metersPerPixelSource === 'manual'"
              type="button"
              class="mini-btn"
              title="清除手填值，恢复自动推算"
              @click="clearMpp"
            >
              自动
            </button>
          </div>
        </div>
        <div v-if="graph.unmatchedAnnotations.length > 0" class="unmatched-box">
          有 {{ graph.unmatchedAnnotations.length }} 条旧标注未匹配到当前实例：
          <span v-for="(item, idx) in graph.unmatchedAnnotations" :key="idx" class="unmatched-item">
            {{ item.layerName }}({{ item.category ?? '未命名' }})
          </span>
        </div>
      </div>

      <!-- Nodes List -->
      <div class="section-head">
        <h3>实例节点</h3>
        <button v-if="activeNodeId" type="button" class="mini-btn" @click="emit('select-node', null)">取消选中</button>
      </div>
      <div class="nodes-list">
        <div
          v-for="node in graph.nodes"
          :key="node.id"
          class="node-card"
          :class="{ active: node.id === activeNodeId, hovered: node.id === hoverNodeId }"
          @click="emit('select-node', node.id)"
          @pointerenter="emit('hover-node', node.id)"
          @pointerleave="emit('hover-node', null)"
        >
          <div class="node-head">
            <i
              class="depth-dot"
              :style="{ background: depthColorHex(node.depth, bounds.min, bounds.max) }"
            />
            <span class="depth-tag">D{{ node.depth }}</span>
            <code class="node-id">{{ node.id }}</code>
            <span class="coords">({{ node.center[0].toFixed(2) }}, {{ node.center[1].toFixed(2) }})</span>
          </div>
          <div class="node-fields" @click.stop>
            <input
              class="cat-input"
              type="text"
              :value="node.category"
              placeholder="类别"
              aria-label="实例类别"
              @blur="commitCategory(node, $event)"
              @keydown.enter="($event.target as HTMLInputElement).blur()"
            />
            <label class="metric-field">
              <span>宽m</span>
              <input
                type="text"
                inputmode="decimal"
                :value="metricInputValue(node, 'width')"
                :placeholder="metricPlaceholder(node, 'width')"
                :class="{ manual: node.metric.widthSource === 'manual' }"
                @blur="commitMetric(node, 'metric_width', $event)"
                @keydown.enter="($event.target as HTMLInputElement).blur()"
              />
            </label>
            <label class="metric-field">
              <span>高m</span>
              <input
                type="text"
                inputmode="decimal"
                :value="metricInputValue(node, 'height')"
                :placeholder="metricPlaceholder(node, 'height')"
                :class="{ manual: node.metric.heightSource === 'manual' }"
                @blur="commitMetric(node, 'metric_height', $event)"
                @keydown.enter="($event.target as HTMLInputElement).blur()"
              />
            </label>
          </div>
        </div>
      </div>

      <!-- Edges List -->
      <div class="section-head edges-head">
        <h3>空间关系 ({{ filteredEdges.length }})</h3>
        <div class="edge-filters">
          <label class="check-pill">
            <input v-model="onlySelectedEdges" type="checkbox" :disabled="!activeNodeId" />
            <span>选中相关</span>
          </label>
          <label class="check-pill">
            <input v-model="onlyOccludedEdges" type="checkbox" />
            <span>仅遮挡</span>
          </label>
        </div>
      </div>
      <div class="edges-list">
        <p v-if="filteredEdges.length === 0" class="empty-edges">没有符合条件的边。</p>
        <div
          v-for="row in filteredEdges"
          :key="row.edge.id"
          class="edge-row"
          :class="{ hovered: row.edge.id === hoverEdgeId }"
          @pointerenter="emit('hover-edge', row.edge.id)"
          @pointerleave="emit('hover-edge', null)"
        >
          <div class="edge-endpoints">
            <span class="ep">{{ row.fromLabel }}</span>
            <span class="arrow">→</span>
            <span class="ep">{{ row.toLabel }}</span>
            <span v-if="row.occBadge" class="occ-pill" :class="row.occKind">{{ row.occBadge }}</span>
          </div>
          <div class="edge-meta">
            <span>{{ row.direction }} · {{ row.angleDeg.toFixed(0) }}° · d={{ row.distance.toFixed(2) }}</span>
            <span>Δ深度 {{ row.depthDelta > 0 ? `+${row.depthDelta}` : row.depthDelta }}</span>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.graph-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  background: #1b1b1b;
  color: #ececec;
  overflow: hidden;
}
.status {
  margin: 0;
  padding: 12px 14px;
  color: #bdbdbd;
  font-size: 13px;
}
.status.error {
  color: #ff8d8d;
}
.overview {
  padding: 10px 14px;
  border-bottom: 1px solid #2a2a2a;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
}
.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 5px 4px;
  border-radius: 6px;
  background: #242424;
}
.stat-val {
  font-size: 15px;
  font-weight: 650;
  color: #ececec;
}
.stat-val.occ {
  color: #ff6b6b;
}
.stat-label {
  font-size: 11px;
  color: #9a9a9a;
}
.mpp-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.mpp-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: #bdbdbd;
}
.source-tag {
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 10.5px;
  background: #2a2a2a;
  color: #9a9a9a;
}
.source-tag.manual {
  background: #2f2814;
  color: #f0a202;
}
.source-tag.derived {
  background: #172d2b;
  color: #2ec4b6;
}
.mpp-controls {
  display: flex;
  gap: 6px;
}
.mpp-controls input {
  flex: 1;
  min-width: 0;
  padding: 4px 8px;
  border: 1px solid #3a3a3a;
  border-radius: 4px;
  background: #141414;
  color: #ececec;
  font: inherit;
  font-size: 12px;
}
.mpp-controls input:focus {
  outline: none;
  border-color: #f0a202;
}
.unmatched-box {
  padding: 6px 8px;
  border-radius: 5px;
  background: #2f2018;
  border: 1px solid #593a24;
  color: #f4a261;
  font-size: 11.5px;
  line-height: 1.45;
}
.unmatched-item {
  margin-left: 4px;
  color: #ffd166;
}
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px 6px;
}
.section-head h3 {
  margin: 0;
  font-size: 12.5px;
  font-weight: 650;
  color: #cccccc;
}
.edges-head {
  border-top: 1px solid #2a2a2a;
}
.mini-btn {
  padding: 2px 7px;
  border: 1px solid #3d3d3d;
  border-radius: 4px;
  background: #2a2a2a;
  color: #d5d5d5;
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}
.mini-btn:hover {
  border-color: #f0a202;
  color: #f0a202;
}
.nodes-list {
  flex: 1 1 52%;
  min-height: 0;
  overflow: auto;
  padding: 0 10px 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.node-card {
  padding: 7px 8px;
  border: 1px solid #2f2f2f;
  border-radius: 6px;
  background: #222222;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.node-card:hover,
.node-card.hovered {
  border-color: #555;
}
.node-card.active {
  border-color: #ffd166;
  background: #2b2618;
}
.node-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
}
.depth-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
}
.depth-tag {
  color: #ffd166;
  font-weight: 600;
}
.node-id {
  color: #9a9a9a;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.coords {
  margin-left: auto;
  color: #8c8c8c;
  font-size: 11px;
  flex-shrink: 0;
}
.node-fields {
  display: grid;
  grid-template-columns: 1fr 74px 74px;
  gap: 5px;
}
.cat-input,
.metric-field input {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  padding: 3px 6px;
  border: 1px solid #383838;
  border-radius: 4px;
  background: #151515;
  color: #ececec;
  font: inherit;
  font-size: 11.5px;
}
.cat-input:focus,
.metric-field input:focus {
  outline: none;
  border-color: #f0a202;
}
.metric-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 10px;
  color: #8c8c8c;
}
.metric-field input.manual {
  border-color: #6b531c;
  color: #ffd166;
}
.edge-filters {
  display: flex;
  gap: 8px;
}
.check-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #bdbdbd;
  cursor: pointer;
}
.check-pill input {
  margin: 0;
  accent-color: #f0a202;
}
.edges-list {
  flex: 1 1 48%;
  min-height: 0;
  overflow: auto;
  padding: 0 10px 10px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.empty-edges {
  margin: 8px 4px;
  color: #888;
  font-size: 12px;
}
.edge-row {
  padding: 6px 8px;
  border: 1px solid #2b2b2b;
  border-radius: 5px;
  background: #212121;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.edge-row.hovered {
  border-color: #f0a202;
  background: #2b2519;
}
.edge-endpoints {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  flex-wrap: wrap;
}
.ep {
  font-weight: 600;
  color: #ececec;
}
.arrow {
  color: #777;
}
.occ-pill {
  margin-left: auto;
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 10.5px;
}
.occ-pill.occludes {
  background: #3b1c1c;
  color: #ff8585;
}
.occ-pill.occluded {
  background: #331e28;
  color: #f48fb1;
}
.occ-pill.coplanar {
  background: #382716;
  color: #f4a261;
}
.edge-meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #9a9a9a;
}
</style>
