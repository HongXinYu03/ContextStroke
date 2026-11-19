<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  addLayer,
  deleteLayer,
  exportScene,
  fetchScene,
  fetchScenes,
  importScene,
  mergeLayers,
  solveStroke,
  syncSceneDepths,
  updateLayer,
} from './api'
import CandidatePanel from './components/CandidatePanel.vue'
import LayerPanel from './components/LayerPanel.vue'
import Viewport from './components/Viewport.vue'
import { pinBackground } from './depthOrder'
import type { LayerModel, SceneDetail, SceneSummary, SolveResult, ViewMode } from './types'

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

let token = 0
let transformTimer: ReturnType<typeof setTimeout> | null = null
let transformToken = 0
let depthTimer: ReturnType<typeof setTimeout> | null = null

function currentDepths(): Record<string, number> {
  const depths: Record<string, number> = {}
  for (const layer of layers.value) depths[layer.id] = layer.depth
  return depths
}

const selectedTrack = computed(
  () => result.value?.tracks.find((track) => track.id === selectedTrackId.value) ?? null,
)

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
  inkGeneration.value += 1
  const next = await fetchScene(id)
  scene.value = next
  layers.value = next.layers
  activeLayerId.value = next.layers[0]?.id ?? null
  loading.value = false
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
      <Viewport
        :layers="layers"
        :canvas-width="scene.width"
        :canvas-height="scene.height"
        :active-layer-id="activeLayerId"
        :mode="mode"
        :track="selectedTrack"
        :ink-generation="inkGeneration"
        @stroke="onStroke"
        @select="activeLayerId = $event"
        @transform="onTransform"
      />
      <CandidatePanel
        :result="result"
        :selected-id="selectedTrackId"
        :solving="solving"
        :error="error"
        @select="selectedTrackId = $event"
        @clear="clearStroke"
      />
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
.scene-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #bdbdbd;
  font-size: 13px;
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
</style>
