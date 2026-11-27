<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  addLayer,
  annotateInstance,
  deleteLayer,
  exportScene,
  fetchScene,
  fetchSceneGraph,
  fetchScenes,
  importScene,
  mergeLayers,
  solveStroke,
  syncSceneDepths,
  updateLayer,
  updateSceneMeta,
} from './api'
import { loadBandColors, saveBandColors, type BandColorMap } from './bands'
import CandidatePanel from './components/CandidatePanel.vue'
import GraphPanel from './components/GraphPanel.vue'
import LayerPanel from './components/LayerPanel.vue'
import SceneGraphCanvas from './components/SceneGraphCanvas.vue'
import Viewport from './components/Viewport.vue'
import type { ExportPngMode } from './components/Viewport.vue'
import { pinBackground } from './depthOrder'
import type {
  GraphEdgeFilter,
  LayerModel,
  SceneDetail,
  SceneGraph,
  SceneSummary,
  SolveResult,
  ViewMode,
  WorkspaceView,
} from './types'

const scenes = ref<SceneSummary[]>([])
const scene = ref<SceneDetail | null>(null)
const layers = ref<LayerModel[]>([])
const activeLayerId = ref<string | null>(null)
const mode = ref<ViewMode>('draw')
const stroke = ref<number[][]>([])
const result = ref<SolveResult | null>(null)
const selectedTrackId = ref<string | null>(null)
const solving = ref(false)
const error = ref('')
const loading = ref(true)
const inkGeneration = ref(0)
const layerBusy = ref(false)
const importInput = ref<HTMLInputElement | null>(null)
const viewportRef = ref<InstanceType<typeof Viewport> | null>(null)
const bandColors = ref<BandColorMap>(loadBandColors())
const pngMenuOpen = ref(false)
const pngExporting = ref(false)
const showLayerBorders = ref(true)
const showGraph = ref(true)
const workspaceView = ref<WorkspaceView>('viewport')
const rightTab = ref<'candidates' | 'graph'>('candidates')
const graph = ref<SceneGraph | null>(null)
const graphLoading = ref(false)
const graphError = ref('')
const graphEdgeFilter = ref<GraphEdgeFilter>('all')
const activeNodeId = ref<string | null>(null)
const hoverNodeId = ref<string | null>(null)
const hoverEdgeId = ref<string | null>(null)

function setBandColor(label: string, hex: string) {
  bandColors.value = { ...bandColors.value, [label]: hex.toLowerCase() }
  saveBandColors(bandColors.value)
}

let token = 0
let graphToken = 0
let graphTimer: ReturnType<typeof setTimeout> | null = null
let transformTimer: ReturnType<typeof setTimeout> | null = null
let transformToken = 0
let depthTimer: ReturnType<typeof setTimeout> | null = null

function setWorkspaceView(next: WorkspaceView) {
  workspaceView.value = next
  if (next === 'split' || next === 'graph') {
    rightTab.value = 'graph'
  }
}

function onSelectNode(id: string | null) {
  activeNodeId.value = id
  if (!id || !graph.value) return
  const node = graph.value.nodes.find((item) => item.id === id)
  if (node) activeLayerId.value = node.layerId
}

async function refreshGraph() {
  const currentScene = scene.value
  if (!currentScene) return
  const current = ++graphToken
  graphLoading.value = true
  graphError.value = ''
  try {
    const next = await fetchSceneGraph(currentScene.id, currentDepths())
    if (current !== graphToken) return
    graph.value = next
    if (activeNodeId.value && !next.nodes.some((n) => n.id === activeNodeId.value)) {
      activeNodeId.value = null
    }
  } catch (reason) {
    if (current !== graphToken) return
    graphError.value = reason instanceof Error ? reason.message : '场景图加载失败'
  } finally {
    if (current === graphToken) graphLoading.value = false
  }
}

function scheduleGraphRefresh(delay = 250) {
  if (graphTimer) clearTimeout(graphTimer)
  graphTimer = setTimeout(() => {
    graphTimer = null
    void refreshGraph()
  }, delay)
}

async function onAnnotateInstance(payload: {
  instanceId: string
  category?: string | null
  metric_width?: number | null
  metric_height?: number | null
}) {
  const currentScene = scene.value
  if (!currentScene) return
  const current = ++graphToken
  graphError.value = ''
  try {
    const { instanceId, ...fields } = payload
    const next = await annotateInstance(currentScene.id, instanceId, {
      ...fields,
      depths: currentDepths(),
    })
    if (current !== graphToken) return
    graph.value = next
  } catch (reason) {
    if (current !== graphToken) return
    graphError.value = reason instanceof Error ? reason.message : '实例标注保存失败'
  }
}

async function onUpdateMpp(metersPerPixel: number | null) {
  const currentScene = scene.value
  if (!currentScene) return
  graphError.value = ''
  try {
    const updated = await updateSceneMeta(currentScene.id, { meters_per_pixel: metersPerPixel })
    if (scene.value && scene.value.id === updated.id) {
      scene.value = { ...scene.value, metersPerPixel: updated.metersPerPixel }
    }
    await refreshGraph()
  } catch (reason) {
    graphError.value = reason instanceof Error ? reason.message : '场景比例更新失败'
  }
}

function currentDepths(): Record<string, number> {
  const depths: Record<string, number> = {}
  for (const layer of layers.value) depths[layer.id] = layer.depth
  return depths
}

const selectedTrack = computed(
  () => result.value?.tracks.find((track) => track.id === selectedTrackId.value) ?? null,
)

const canExportPng = computed(() => Boolean(scene.value && !layerBusy.value && !pngExporting.value))
const canExportStrokePng = computed(() => Boolean(canExportPng.value && selectedTrack.value))

async function onExportPng(mode: ExportPngMode) {
  if (!viewportRef.value || !scene.value) return
  if (mode === 'clean') {
    if (!canExportPng.value) return
  } else if (!canExportStrokePng.value || !selectedTrack.value) {
    return
  }
  pngMenuOpen.value = false
  pngExporting.value = true
  error.value = ''
  try {
    const dataUrl = viewportRef.value.exportPng(mode)
    const anchor = document.createElement('a')
    anchor.href = dataUrl
    const suffix =
      mode === 'clean' ? 'clean' : `track-${selectedTrack.value?.id ?? '0'}-${mode}`
    anchor.download = `${scene.value.id}-${suffix}.png`
    anchor.click()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '导出 PNG 失败'
  } finally {
    pngExporting.value = false
  }
}

const depthSignature = computed(() => layers.value.map((layer) => `${layer.id}:${layer.depth}`).join('|'))

function applyResult(next: SolveResult) {
  result.value = next
  selectedTrackId.value = next.tracks.find((track) => track.selected)?.id ?? next.tracks[0]?.id ?? null
}

async function solveCurrent() {
  const currentScene = scene.value
  const points = stroke.value
  if (!currentScene || points.length < 2) return
  const current = ++token
  solving.value = true
  error.value = ''
  const depths: Record<string, number> = {}
  for (const layer of layers.value) depths[layer.id] = layer.depth
  try {
    const next = await solveStroke({ scene: currentScene.id, depths, stroke: points })
    if (current !== token) return
    applyResult(next)
  } catch (reason) {
    if (current !== token) return
    error.value = reason instanceof Error ? reason.message : '求解失败'
  } finally {
    if (current === token) solving.value = false
  }
}

async function loadScene(id: string) {
  token += 1
  loading.value = true
  error.value = ''
  stroke.value = []
  result.value = null
  selectedTrackId.value = null
  graph.value = null
  activeNodeId.value = null
  hoverNodeId.value = null
  hoverEdgeId.value = null
  inkGeneration.value += 1
  const next = await fetchScene(id)
  scene.value = next
  layers.value = next.layers
  activeLayerId.value = next.layers[0]?.id ?? null
  loading.value = false
  void refreshGraph()
}

function keepLocalFields(next: SceneDetail): LayerModel[] {
  const local = new Map(layers.value.map((layer) => [layer.id, layer]))
  return pinBackground(
    next.layers.map((layer) => {
      const previous = local.get(layer.id)
      return {
        ...layer,
        depth: previous?.depth ?? layer.depth,
        visible: previous?.visible ?? layer.visible,
      }
    }),
  )
}

function onToggleVisible(id: string) {
  layers.value = layers.value.map((layer) =>
    layer.id === id ? { ...layer, visible: !layer.visible } : layer,
  )
  if (scene.value) scene.value = { ...scene.value, layers: layers.value }
}

function applyScene(next: SceneDetail) {
  const merged = keepLocalFields(next)
  scene.value = { ...next, layers: merged, width: next.width, height: next.height }
  layers.value = merged
}

function applyLocalTransform(payload: { id: string; x: number; y: number; scale: number }) {
  layers.value = layers.value.map((layer) =>
    layer.id === payload.id ? { ...layer, x: payload.x, y: payload.y, scale: payload.scale } : layer,
  )
  if (scene.value) scene.value = { ...scene.value, layers: layers.value }
}

async function persistTransform(payload: { id: string; x: number; y: number; scale: number }) {
  const current = scene.value
  if (!current) return
  const currentToken = ++transformToken
  try {
    const next = await updateLayer(current.id, payload.id, {
      x: payload.x,
      y: payload.y,
      scale: payload.scale,
    })
    if (currentToken !== transformToken) return
    applyScene(next)
    if (stroke.value.length >= 2) void solveCurrent()
    scheduleGraphRefresh()
  } catch (reason) {
    if (currentToken !== transformToken) return
    error.value = reason instanceof Error ? reason.message : '图层位置更新失败'
  }
}

function onTransform(payload: { id: string; x: number; y: number; scale: number }) {
  applyLocalTransform(payload)
  if (transformTimer) clearTimeout(transformTimer)
  transformTimer = setTimeout(() => {
    transformTimer = null
    void persistTransform(payload)
  }, 180)
}

async function onBackground(id: string) {
  const current = scene.value
  if (!current || layerBusy.value) return
  layerBusy.value = true
  error.value = ''
  try {
    applyScene(await updateLayer(current.id, id, { background: true }))
    activeLayerId.value = id
    if (stroke.value.length >= 2) void solveCurrent()
    scheduleGraphRefresh()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '设置背景失败'
  } finally {
    layerBusy.value = false
  }
}

function onReorder(next: LayerModel[]) {
  layers.value = pinBackground(next)
  if (depthTimer) clearTimeout(depthTimer)
  depthTimer = setTimeout(() => {
    depthTimer = null
    void persistDepths()
  }, 250)
}

async function persistDepths() {
  const current = scene.value
  if (!current) return
  try {
    await syncSceneDepths(current.id, currentDepths())
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '深度顺序保存失败'
  }
}

async function onExportScene() {
  const current = scene.value
  if (!current || layerBusy.value) return
  layerBusy.value = true
  error.value = ''
  try {
    await exportScene(current.id, currentDepths())
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '导出场景失败'
  } finally {
    layerBusy.value = false
  }
}

async function onImportFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || layerBusy.value) return
  layerBusy.value = true
  error.value = ''
  try {
    const imported = await importScene(file)
    scenes.value = await fetchScenes()
    await loadScene(imported.id)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '导入场景失败'
    loading.value = false
  } finally {
    layerBusy.value = false
  }
}

async function onAddLayer(file: File) {
  const current = scene.value
  if (!current || layerBusy.value) return
  layerBusy.value = true
  error.value = ''
  const previous = new Set(layers.value.map((layer) => layer.id))
  const depth = layers.value.reduce((max, layer) => Math.max(max, layer.depth), 0) + 1
  try {
    const next = await addLayer(current.id, file, depth)
    applyScene(next)
    activeLayerId.value = layers.value.find((layer) => !previous.has(layer.id))?.id ?? activeLayerId.value
    scheduleGraphRefresh()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '添加图层失败'
  } finally {
    layerBusy.value = false
  }
}

async function onDeleteLayer() {
  const current = scene.value
  const layerId = activeLayerId.value
  if (!current || !layerId || layerBusy.value) return
  layerBusy.value = true
  error.value = ''
  try {
    applyScene(await deleteLayer(current.id, layerId))
    if (!layers.value.some((layer) => layer.id === activeLayerId.value)) {
      activeLayerId.value = layers.value[0]?.id ?? null
    }
    scheduleGraphRefresh()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '删除图层失败'
  } finally {
    layerBusy.value = false
  }
}

async function onMergeLayers(ids: string[]) {
  const current = scene.value
  const first = ids[0]
  const second = ids[1]
  if (!current || !first || !second || layerBusy.value) return
  const left = layers.value.find((layer) => layer.id === first)
  const right = layers.value.find((layer) => layer.id === second)
  if (!left || !right) return
  layerBusy.value = true
  error.value = ''
  const previous = new Set(layers.value.map((layer) => layer.id))
  try {
    applyScene(await mergeLayers(current.id, [first, second], Math.min(left.depth, right.depth)))
    activeLayerId.value = layers.value.find((layer) => !previous.has(layer.id))?.id ?? layers.value[0]?.id ?? null
    scheduleGraphRefresh()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '合并图层失败'
  } finally {
    layerBusy.value = false
  }
}

function onStroke(points: number[][]) {
  stroke.value = points
  result.value = null
  selectedTrackId.value = null
  void solveCurrent()
}

function clearStroke() {
  token += 1
  stroke.value = []
  result.value = null
  selectedTrackId.value = null
  solving.value = false
  error.value = ''
  inkGeneration.value += 1
}

onMounted(async () => {
  try {
    scenes.value = await fetchScenes()
    const first = scenes.value[0]
    if (!first) {
      error.value = '没有可用场景'
      loading.value = false
      return
    }
    await loadScene(first.id)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '场景加载失败'
    loading.value = false
  }
})

watch(depthSignature, (value, previous) => {
  if (previous === undefined || value === previous) return
  if (stroke.value.length >= 2) void solveCurrent()
  scheduleGraphRefresh()
})
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="brand">ContextStroke</div>
      <div class="modes" role="group" aria-label="视图模式">
        <button type="button" :class="{ active: mode === 'draw' }" :aria-pressed="mode === 'draw'" @click="mode = 'draw'">
          绘制
        </button>
        <button type="button" :class="{ active: mode === 'edit' }" :aria-pressed="mode === 'edit'" @click="mode = 'edit'">
          调整
        </button>
        <button
          type="button"
          :class="{ active: mode === 'observe' }"
          :aria-pressed="mode === 'observe'"
          @click="mode = 'observe'"
        >
          观察
        </button>
      </div>
      <button
        type="button"
        class="border-toggle"
        :class="{ active: showLayerBorders }"
        :aria-pressed="showLayerBorders"
        :disabled="!scene"
        :title="showLayerBorders ? '隐藏图层边框' : '显示图层边框'"
        @click="showLayerBorders = !showLayerBorders"
      >
        {{ showLayerBorders ? '隐藏边框' : '显示边框' }}
      </button>
      <button
        type="button"
        class="border-toggle"
        :class="{ active: showGraph }"
        :aria-pressed="showGraph"
        :disabled="!scene"
        :title="showGraph ? '隐藏 3D 视口中的场景图叠加' : '在 3D 视口中叠加场景图'"
        @click="showGraph = !showGraph"
      >
        {{ showGraph ? '隐藏图叠加' : '显示图叠加' }}
      </button>
      <div class="modes view-switch" role="group" aria-label="工作区视图">
        <button
          type="button"
          :class="{ active: workspaceView === 'viewport' }"
          :aria-pressed="workspaceView === 'viewport'"
          @click="setWorkspaceView('viewport')"
        >
          场景
        </button>
        <button
          type="button"
          :class="{ active: workspaceView === 'split' }"
          :aria-pressed="workspaceView === 'split'"
          @click="setWorkspaceView('split')"
        >
          分栏
        </button>
        <button
          type="button"
          :class="{ active: workspaceView === 'graph' }"
          :aria-pressed="workspaceView === 'graph'"
          @click="setWorkspaceView('graph')"
        >
          拓扑图
        </button>
      </div>
      <div class="scene-tools">
        <label v-if="scenes.length > 0" class="scene-picker">
          场景
          <select
            :value="scene?.id ?? ''"
            :disabled="layerBusy || loading"
            @change="loadScene(($event.target as HTMLSelectElement).value)"
          >
            <option v-for="item in scenes" :key="item.id" :value="item.id">{{ item.name }}</option>
          </select>
        </label>
        <button type="button" :disabled="!scene || layerBusy" @click="onExportScene">导出场景</button>
        <div class="png-export">
          <button
            type="button"
            :disabled="!canExportPng"
            title="导出正视角 PNG（可选带笔触或纯场景）"
            @click="pngMenuOpen = !pngMenuOpen"
          >
            导出 PNG
          </button>
          <div v-if="pngMenuOpen" class="png-menu" role="menu">
            <button
              type="button"
              role="menuitem"
              :disabled="!canExportStrokePng"
              :title="canExportStrokePng ? '' : '请先选择一条深度候选'"
              @click="onExportPng('occlude')"
            >
              真遮挡
            </button>
            <button
              type="button"
              role="menuitem"
              :disabled="!canExportStrokePng"
              :title="canExportStrokePng ? '' : '请先选择一条深度候选'"
              @click="onExportPng('ghost')"
            >
              遮挡可辨
            </button>
            <button type="button" role="menuitem" @click="onExportPng('clean')">无笔触</button>
            <button
              type="button"
              role="menuitem"
              :disabled="!canExportStrokePng"
              :title="
                canExportStrokePng
                  ? '场景底图 + 连续笔触几何（不分 on/off，无遮挡）'
                  : '请先选择一条深度候选'
              "
              @click="onExportPng('stroke')"
            >
              仅笔触
            </button>
          </div>
        </div>
        <button type="button" :disabled="layerBusy" @click="importInput?.click()">导入场景</button>
        <input
          ref="importInput"
          class="file"
          type="file"
          accept=".zip,application/zip"
          @change="onImportFile"
        />
      </div>
    </header>
    <p v-if="loading" class="banner">正在加载场景…</p>
    <p v-else-if="!scene && error" class="banner error">{{ error }}</p>
    <main v-else-if="scene" class="workspace">
      <LayerPanel
        :layers="layers"
        :active-id="activeLayerId"
        :busy="layerBusy"
        @select="activeLayerId = $event"
        @reorder="onReorder"
        @add="onAddLayer"
        @remove="onDeleteLayer"
        @merge="onMergeLayers"
        @transform="onTransform"
        @background="onBackground"
        @toggle-visible="onToggleVisible"
      />
      <div class="center-stage" :class="workspaceView">
        <Viewport
          v-show="workspaceView !== 'graph'"
          ref="viewportRef"
          :layers="layers"
          :canvas-width="scene.width"
          :canvas-height="scene.height"
          :active-layer-id="activeLayerId"
          :mode="mode"
          :track="selectedTrack"
          :ink-generation="inkGeneration"
          :band-colors="bandColors"
          :show-layer-borders="showLayerBorders"
          :graph="graph"
          :show-graph="showGraph"
          :edge-filter="graphEdgeFilter"
          :active-node-id="activeNodeId"
          :hover-node-id="hoverNodeId"
          :hover-edge-id="hoverEdgeId"
          @stroke="onStroke"
          @select="activeLayerId = $event"
          @transform="onTransform"
          @select-node="onSelectNode"
          @hover-node="hoverNodeId = $event"
        />
        <SceneGraphCanvas
          v-if="workspaceView !== 'viewport'"
          :graph="graph"
          :scene-id="scene.id"
          :edge-filter="graphEdgeFilter"
          :active-node-id="activeNodeId"
          :hover-node-id="hoverNodeId"
          :hover-edge-id="hoverEdgeId"
          @update:edge-filter="graphEdgeFilter = $event"
          @select-node="onSelectNode"
          @hover-node="hoverNodeId = $event"
          @hover-edge="hoverEdgeId = $event"
        />
      </div>
      <div class="right-pane">
        <div class="right-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            :class="{ active: rightTab === 'candidates' }"
            :aria-selected="rightTab === 'candidates'"
            @click="rightTab = 'candidates'"
          >
            深度候选
          </button>
          <button
            type="button"
            role="tab"
            :class="{ active: rightTab === 'graph' }"
            :aria-selected="rightTab === 'graph'"
            @click="rightTab = 'graph'"
          >
            场景图
            <span v-if="graph" class="tab-badge">{{ graph.nodes.length }}</span>
          </button>
        </div>
        <CandidatePanel
          v-if="rightTab === 'candidates'"
          :result="result"
          :selected-id="selectedTrackId"
          :solving="solving"
          :error="error"
          :band-colors="bandColors"
          @select="selectedTrackId = $event"
          @clear="clearStroke"
          @set-band-color="setBandColor"
        />
        <GraphPanel
          v-else
          :graph="graph"
          :loading="graphLoading"
          :error="graphError"
          :active-node-id="activeNodeId"
          :hover-node-id="hoverNodeId"
          :hover-edge-id="hoverEdgeId"
          @select-node="onSelectNode"
          @hover-node="hoverNodeId = $event"
          @hover-edge="hoverEdgeId = $event"
          @annotate="onAnnotateInstance"
          @update-mpp="onUpdateMpp"
        />
      </div>
    </main>
  </div>
</template>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #121212;
  color: #ececec;
}
.topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  height: 52px;
  padding: 0 16px;
  border-bottom: 1px solid #2a2a2a;
  background: #171717;
}
.brand {
  font-weight: 680;
  letter-spacing: 0.01em;
}
.modes {
  display: flex;
  padding: 2px;
  border-radius: 8px;
  background: #2a2a2a;
}
.modes button,
.scene-picker select {
  border: 0;
  background: transparent;
  color: #d5d5d5;
  font: inherit;
  cursor: pointer;
}
.modes button {
  padding: 6px 14px;
  border-radius: 6px;
}
.modes button.active {
  background: #f0a202;
  color: #1a1a1a;
}
.border-toggle {
  padding: 6px 12px;
  border: 1px solid #3d3d3d;
  border-radius: 6px;
  background: #2a2a2a;
  color: #d5d5d5;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}
.border-toggle.active {
  border-color: #f0a202;
  color: #f0a202;
}
.border-toggle:disabled {
  opacity: 0.45;
  cursor: default;
}
.scene-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #bdbdbd;
  font-size: 13px;
}
.png-export {
  position: relative;
}
.png-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  min-width: 120px;
  padding: 4px;
  border: 1px solid #3d3d3d;
  border-radius: 6px;
  background: #1f1f1f;
  box-shadow: 0 8px 24px rgb(0 0 0 / 45%);
}
.png-menu button {
  width: 100%;
  margin: 0;
  padding: 6px 10px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #ececec;
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}
.png-menu button:hover:not(:disabled) {
  background: #2c2618;
  color: #f0a202;
}
.png-menu button:disabled {
  opacity: 0.4;
  cursor: default;
}
.scene-picker select,
.scene-tools button {
  margin-left: 0;
  padding: 4px 8px;
  border: 1px solid #3d3d3d;
  border-radius: 4px;
  background: #2a2a2a;
  color: #ececec;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.scene-tools button:hover:not(:disabled) {
  border-color: #f0a202;
}
.scene-tools button:disabled,
.scene-picker select:disabled {
  opacity: 0.45;
  cursor: default;
}
.file {
  display: none;
}
.banner {
  margin: 24px;
  color: #bdbdbd;
}
.banner.error {
  color: #ff8d8d;
}
.workspace {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 320px;
  flex: 1;
  min-height: 0;
}
.workspace > :first-child,
.workspace > :last-child {
  min-height: 0;
  border-right: 1px solid #2a2a2a;
}
.workspace > :last-child {
  border-right: 0;
  border-left: 1px solid #2a2a2a;
}
.center-stage {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  min-width: 0;
  min-height: 0;
}
.center-stage.split {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
}
.center-stage.split > :first-child {
  border-right: 1px solid #2a2a2a;
}
.right-pane {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: #1b1b1b;
}
.right-pane > :last-child {
  flex: 1;
  min-height: 0;
}
.right-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  border-bottom: 1px solid #2a2a2a;
  background: #171717;
}
.right-tabs button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 9px 10px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: #9f9f9f;
  font: inherit;
  font-size: 13px;
  font-weight: 550;
  cursor: pointer;
}
.right-tabs button.active {
  color: #f0a202;
  border-bottom-color: #f0a202;
  background: #1f1d17;
}
.tab-badge {
  padding: 0 6px;
  border-radius: 10px;
  background: #2c2c2c;
  color: #d5d5d5;
  font-size: 11px;
  font-weight: 600;
}
.right-tabs button.active .tab-badge {
  background: #3a2f14;
  color: #ffd166;
}
</style>
