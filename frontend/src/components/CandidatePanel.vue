<script setup lang="ts">
import { computed } from 'vue'
import { bandHex, OFF_LABEL, offHex, type BandColorMap } from '../bands'
import type { SolveResult, Track } from '../types'

const props = defineProps<{
  result: SolveResult | null
  selectedId: string | null
  solving: boolean
  error: string
  bandColors: BandColorMap
}>()

const bands = computed(() => {
  const track = props.result?.tracks.find((item) => item.id === props.selectedId) ?? props.result?.tracks[0]
  if (!track) return []
  const labels: string[] = []
  for (const segment of track.segments) {
    if (segment.relation !== 'band' || labels.includes(segment.label)) continue
    labels.push(segment.label)
  }
  return labels
})

const emit = defineEmits<{
  select: [id: string]
  clear: []
  'set-band-color': [label: string, hex: string]
}>()

function costText(track: Track): string {
  return track.cost === null ? '' : `深度变化 ${track.cost}`
}

function onColorInput(label: string, event: Event) {
  const value = (event.target as HTMLInputElement).value
  emit('set-band-color', label, value)
}
</script>

<template>
  <aside class="panel">
    <header class="panel-title">
      <h2>深度候选</h2>
      <button type="button" @click="emit('clear')">清除笔触</button>
    </header>
    <p v-if="solving" class="status">正在计算前后关系…</p>
    <p v-else-if="error" class="status error">{{ error }}</p>
    <p v-else-if="result?.message" class="status">{{ result.message }}</p>
    <p v-else-if="!result" class="status">在正视图里画一笔。每一段 on 选择一条深度带，例如 0-1、1-2。默认是深度变化最小的一条。</p>
    <div v-if="result && result.tracks.length" class="tracks">
      <button
        v-for="track in result.tracks"
        :key="track.id"
        type="button"
        class="track"
        :class="{ active: track.id === selectedId }"
        @click="emit('select', track.id)"
      >
        <span class="index">{{ track.id }}</span>
        <span class="summary">{{ track.summary }}</span>
        <span class="cost">{{ costText(track) }}</span>
      </button>
    </div>
    <ul class="legend">
      <li v-for="label in bands" :key="label">
        <label class="swatch-wrap" :title="`调整 ${label} 颜色`">
          <input
            class="swatch-input"
            type="color"
            :value="bandHex(label, bandColors)"
            @input="onColorInput(label, $event)"
          />
          <i class="swatch" :style="{ background: bandHex(label, bandColors) }" />
        </label>
        {{ label }}
      </li>
      <li>
        <label class="swatch-wrap" title="调整空白段颜色">
          <input
            class="swatch-input"
            type="color"
            :value="offHex(bandColors)"
            @input="onColorInput(OFF_LABEL, $event)"
          />
          <i class="swatch" :style="{ background: offHex(bandColors) }" />
        </label>
        空白（可跨层）
      </li>
    </ul>
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
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 16px 8px;
}
h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
}
.panel-title button,
.track {
  border: 1px solid #3d3d3d;
  border-radius: 6px;
  background: #2a2a2a;
  color: #ececec;
  font: inherit;
  cursor: pointer;
}
.panel-title button {
  font-size: 12px;
  padding: 4px 8px;
}
.status {
  margin: 0;
  padding: 0 16px 12px;
  color: #bdbdbd;
  font-size: 13px;
  line-height: 1.5;
}
.status.error {
  color: #ff8d8d;
}
.tracks {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: auto;
  padding: 0 12px 12px;
}
.track {
  display: grid;
  grid-template-columns: 22px 1fr;
  gap: 2px 8px;
  padding: 8px;
  text-align: left;
}
.track.active {
  border-color: #f0a202;
  background: #2c2618;
}
.index {
  grid-row: span 2;
  align-self: center;
  color: #f0a202;
  font-weight: 650;
}
.summary {
  font-size: 13px;
  line-height: 1.4;
}
.cost {
  color: #9a9a9a;
  font-size: 12px;
}
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
  margin: auto 0 0;
  padding: 12px 16px 16px;
  list-style: none;
  color: #bdbdbd;
  font-size: 12px;
}
.legend li {
  display: flex;
  align-items: center;
  gap: 6px;
}
.swatch-wrap {
  position: relative;
  display: inline-flex;
  width: 14px;
  height: 14px;
  cursor: pointer;
}
.swatch-input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  padding: 0;
  border: 0;
  opacity: 0;
  cursor: pointer;
}
.swatch {
  display: block;
  width: 14px;
  height: 14px;
  border-radius: 3px;
  border: 1px solid #555;
  pointer-events: none;
}
.break {
  background: #ff5a5a;
}
</style>
