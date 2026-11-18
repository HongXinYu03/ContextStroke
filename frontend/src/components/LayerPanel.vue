<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { groupByDepth, insertDepth, joinDepth, stepDepth } from '../depthOrder'
import type { LayerModel } from '../types'

const props = defineProps<{
  layers: LayerModel[]
  activeId: string | null
  busy: boolean
}>()

const emit = defineEmits<{
  select: [id: string]
  reorder: [layers: LayerModel[]]
  add: [file: File]
  remove: []
  merge: [ids: string[]]
  transform: [payload: { id: string; x: number; y: number; scale: number }]
  background: [id: string]
}>()

const active = computed(() => props.layers.find((layer) => layer.id === props.activeId) ?? null)

const fileInput = ref<HTMLInputElement | null>(null)
const checked = ref<string[]>([])

watch(
  () => props.layers.map((layer) => layer.id).join('|'),
  () => {
    const alive = new Set(props.layers.map((layer) => layer.id))
    checked.value = checked.value.filter((id) => alive.has(id))
  },
)

function toggle(id: string) {
  if (checked.value.includes(id)) {
    checked.value = checked.value.filter((item) => item !== id)
    return
  }
  checked.value = [...checked.value, id].slice(-2)
}

function onFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (file) emit('add', file)
}

function askRemove() {
  const layer = props.layers.find((item) => item.id === props.activeId)
  if (!layer) return
  if (!window.confirm(`删除「${layer.name}」？`)) return
  emit('remove')
}

const draggingId = ref<string | null>(null)
const dropGap = ref<number | null>(null)
const dropDepth = ref<number | null>(null)

const groups = computed(() => groupByDepth(props.layers))

function clearDrop() {
  draggingId.value = null
  dropGap.value = null
  dropDepth.value = null
}

function onDragStart(id: string, event: DragEvent) {
  draggingId.value = id
  event.dataTransfer?.setData('text/plain', id)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

function onDropGroup(depth: number) {
  if (!draggingId.value) return
  emit('reorder', joinDepth(props.layers, draggingId.value, depth))
  clearDrop()
}

function onDropGap(index: number) {
  if (!draggingId.value) return
  emit(
    'reorder',
    insertDepth(
      props.layers,
      draggingId.value,
      index,
      groups.value.map((group) => group.depth),
    ),
  )
  clearDrop()
}
</script>

<template>
  <aside class="panel">
    <header class="panel-title">
      <h2>深度顺序</h2>
      <p>1 为最前。拖到一组上即并入该深度，拖到间隙则单独成层。勾选两个图层后可以合并。在「调整」模式里拖动并滚轮缩放。</p>
      <div class="tools">
        <button type="button" :disabled="busy" @click="fileInput?.click()">添加图层</button>
        <button type="button" :disabled="busy || !activeId" @click="askRemove">删除</button>
        <button type="button" :disabled="busy || checked.length !== 2" @click="emit('merge', checked)">合并</button>
        <button
          type="button"
          :disabled="busy || !activeId || active?.background"
          @click="activeId && emit('background', activeId)"
        >
          设为背景
        </button>
        <input ref="fileInput" class="file" type="file" accept="image/png,.png" @change="onFile" />
      </div>
      <div v-if="active" class="transform">
        <label>
          X
          <input
            type="number"
            :value="active.x"
            :disabled="busy"
            @change="
              emit('transform', {
                id: active.id,
                x: Number(($event.target as HTMLInputElement).value),
                y: active.y,
                scale: active.scale,
              })
            "
          />
        </label>
        <label>
          Y
          <input
            type="number"
            :value="active.y"
            :disabled="busy"
            @change="
              emit('transform', {
                id: active.id,
                x: active.x,
                y: Number(($event.target as HTMLInputElement).value),
                scale: active.scale,
              })
            "
          />
        </label>
        <label>
          缩放%
          <input
            type="number"
            min="5"
            max="2000"
            step="1"
            :value="Math.round(active.scale * 100)"
            :disabled="busy"
            @change="
              emit('transform', {
                id: active.id,
                x: active.x,
                y: active.y,
                scale: Math.max(0.05, Number(($event.target as HTMLInputElement).value) / 100),
              })
            "
          />
        </label>
      </div>
    </header>
    <div v-if="groups.length === 0" class="empty">场景里还没有图层</div>
    <div v-else class="groups" @dragend="clearDrop">
      <template v-for="(group, index) in groups" :key="group.depth">
        <div
          class="drop-gap"
          :class="{ active: dropGap === index }"
          @dragover.prevent="dropGap = index"
          @drop.stop.prevent="onDropGap(index)"
        />
        <section
          class="group"
          :class="{ dropping: dropDepth === group.depth }"
          @dragover.prevent="dropDepth = group.depth"
          @drop.stop.prevent="onDropGroup(group.depth)"
        >
          <div class="group-label">
            <span>深度 {{ group.depth }}</span>
            <span v-if="group.depth === 1" class="near">最前</span>
            <span v-if="group.items.some((layer) => layer.background)" class="near">背景</span>
          </div>
          <article
            v-for="layer in group.items"
            :key="layer.id"
            class="layer"
            :class="{ active: layer.id === activeId, dragging: layer.id === draggingId }"
            :draggable="!layer.background"
            @click="emit('select', layer.id)"
            @dragstart="!layer.background && onDragStart(layer.id, $event)"
          >
            <img class="thumb" :src="layer.imageUrl" :alt="layer.name" draggable="false" />
            <div class="meta">
              <label class="check" @click.stop>
                <input
                  type="checkbox"
                  :checked="checked.includes(layer.id)"
                  :disabled="layer.background"
                  @change="toggle(layer.id)"
                />
                合并
              </label>
              <strong>{{ layer.name }}{{ layer.background ? ' · 背景' : '' }}</strong>
              <div class="steps">
                <button
                  type="button"
                  :disabled="layer.background"
                  @click.stop="emit('reorder', stepDepth(layers, layer.id, 'nearer'))"
                >
                  更近
                </button>
                <button
                  type="button"
                  :disabled="layer.background"
                  @click.stop="emit('reorder', stepDepth(layers, layer.id, 'farther'))"
                >
                  更远
                </button>
              </div>
            </div>
          </article>
        </section>
      </template>
      <div
        class="drop-gap"
        :class="{ active: dropGap === groups.length }"
        @dragover.prevent="dropGap = groups.length"
        @drop.stop.prevent="onDropGap(groups.length)"
      />
    </div>
  </aside>
</template>

<style scoped>
.panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #1b1b1b;
  color: #ececec;
}
.panel-title {
  padding: 16px 16px 8px;
}
h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
}
p {
  margin: 6px 0 0;
  color: #9a9a9a;
  font-size: 12px;
  line-height: 1.45;
}
.groups {
  overflow: auto;
  padding: 4px 8px 16px;
}
.group {
  border: 1px solid #2e2e2e;
  border-radius: 8px;
  background: #222;
}
.group.dropping {
  border-color: #f0a202;
}
.group-label {
  display: flex;
  justify-content: space-between;
  padding: 8px 10px 4px;
  color: #bdbdbd;
  font-size: 12px;
}
.near {
  color: #f0a202;
}
.layer {
  display: flex;
  gap: 10px;
  margin: 6px;
  padding: 6px;
  border-radius: 6px;
  cursor: grab;
}
.layer.active {
  background: #2c2618;
}
.layer.dragging {
  opacity: 0.45;
}
.thumb {
  width: 72px;
  height: 54px;
  object-fit: contain;
  border-radius: 4px;
  background-color: #2a2a2a;
  background-image:
    linear-gradient(45deg, #3a3a3a 25%, transparent 25%),
    linear-gradient(-45deg, #3a3a3a 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, #3a3a3a 75%),
    linear-gradient(-45deg, transparent 75%, #3a3a3a 75%);
  background-size: 12px 12px;
  background-position:
    0 0,
    0 6px,
    6px -6px,
    -6px 0;
}
.meta {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-width: 0;
}
.meta strong {
  font-size: 13px;
  font-weight: 600;
}
.steps {
  display: flex;
  gap: 6px;
}
button {
  border: 1px solid #3d3d3d;
  border-radius: 4px;
  background: #2a2a2a;
  color: #ececec;
  font: inherit;
  font-size: 12px;
  padding: 2px 8px;
  cursor: pointer;
}
button:hover:not(:disabled) {
  border-color: #f0a202;
}
button:disabled {
  opacity: 0.45;
  cursor: default;
}
.tools {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
.transform {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  margin-top: 10px;
}
.transform label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: #9a9a9a;
  font-size: 11px;
}
.transform input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #3d3d3d;
  border-radius: 4px;
  background: #2a2a2a;
  color: #ececec;
  font: inherit;
  font-size: 12px;
  padding: 4px 6px;
}
.file {
  display: none;
}
.check {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #9a9a9a;
  font-size: 12px;
}
.drop-gap {
  height: 8px;
  margin: 2px 10px;
  border-radius: 4px;
}
.drop-gap.active {
  height: 14px;
  background: #f0a202;
}
.empty {
  padding: 16px;
  color: #9a9a9a;
}
</style>
