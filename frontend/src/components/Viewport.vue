<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { Line2 } from 'three/addons/lines/Line2.js'
import { LineGeometry } from 'three/addons/lines/LineGeometry.js'
import { LineMaterial } from 'three/addons/lines/LineMaterial.js'
import { bandColor } from '../bands'
import type { LayerModel, Track, ViewMode } from '../types'

const PLANE_WIDTH = 6
const SPACING = 0.42

const props = defineProps<{
  layers: LayerModel[]
  canvasWidth: number
  canvasHeight: number
  activeLayerId: string | null
  mode: ViewMode
  track: Track | null
  inkGeneration: number
}>()

const emit = defineEmits<{
  stroke: [points: number[][]]
  select: [id: string]
  transform: [payload: { id: string; x: number; y: number; scale: number }]
}>()

const host = ref<HTMLDivElement | null>(null)
const hint = ref('在画面上拖动绘制')

type PlaneRecord = {
  mesh: THREE.Mesh
  border: THREE.LineSegments
  url: string
}

let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.OrthographicCamera | null = null
let controls: OrbitControls | null = null
let hitPlane: THREE.Mesh | null = null
let frameId = 0
let observer: ResizeObserver | null = null
let drawing = false
let livePoints: { x: number; y: number }[] = []
let editing = false
let editOrigin: { x: number; y: number } | null = null
let editStart: { x: number; y: number } | null = null
let editLayer: LayerModel | null = null

const planes = new THREE.Group()
const strokes = new THREE.Group()
const records = new Map<string, PlaneRecord>()
const textures = new Map<string, THREE.Texture>()
const lineMaterials: LineMaterial[] = []
const raycaster = new THREE.Raycaster()
const loader = new THREE.TextureLoader()

function worldSize() {
  const width = PLANE_WIDTH
  const height = props.canvasWidth > 0 ? (PLANE_WIDTH * props.canvasHeight) / props.canvasWidth : PLANE_WIDTH
  return { width, height }
}

function viewAspect() {
  const element = renderer?.domElement
  if (!element || element.clientHeight === 0) return 1
  return element.clientWidth / element.clientHeight
}

function updateFrustum() {
  if (!camera) return
  const { width, height } = worldSize()
  const aspect = viewAspect()
  const imageAspect = width / height
  const halfH = aspect > imageAspect ? height / 2 : width / 2 / aspect
  const halfW = aspect > imageAspect ? halfH * aspect : width / 2
  camera.left = -halfW
  camera.right = halfW
  camera.top = halfH
  camera.bottom = -halfH
  camera.near = 0.01
  camera.far = 200
  camera.updateProjectionMatrix()
}

function frameFront(message: string) {
  if (!camera || !controls) return
  controls.enabled = false
  camera.zoom = 1
  camera.position.set(0, 0, 8)
  camera.up.set(0, 1, 0)
  controls.target.set(0, 0, 0)
  camera.lookAt(0, 0, 0)
  updateFrustum()
  controls.update()
  hint.value = message
}

function frameDraw() {
  frameFront('在画面上拖动绘制')
}

function frameEdit() {
  frameFront('拖动选中图层移动，滚轮缩放')
}

function resetToDrawView() {
  if (!camera || !controls) return
  camera.zoom = 1
  camera.position.set(0, 0, 8)
  camera.up.set(0, 1, 0)
  controls.target.set(0, 0, 0)
  camera.lookAt(0, 0, 0)
  updateFrustum()
  controls.update()
  hint.value = props.mode === 'observe' ? '已回正到绘制视角，可继续拖动旋转' : hint.value
}

function frameObserve() {
  if (!camera || !controls) return
  controls.enabled = true
  const { width, height } = worldSize()
  const maxDepth = props.layers.reduce((max, layer) => Math.max(max, layer.depth), 1)
  const midZ = -((1 + maxDepth) / 2) * SPACING
  controls.target.set(0, 0, midZ)
  camera.position.set(-width * 0.72, height * 0.4, midZ + width * 0.72)
  camera.up.set(0, 1, 0)
  camera.lookAt(controls.target)
  updateFrustum()
  controls.update()
  hint.value = '拖动旋转查看遮挡，绘制已锁定'
}

function textureFor(url: string) {
  const cached = textures.get(url)
  if (cached) return cached
  const texture = loader.load(url)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = renderer?.capabilities.getMaxAnisotropy() ?? 1
  textures.set(url, texture)
  return texture
}

function planePlacement(layer: LayerModel) {
  const full = worldSize()
  const displayWidth = layer.pixelWidth * layer.scale
  const displayHeight = layer.pixelHeight * layer.scale
  const width = full.width * (displayWidth / props.canvasWidth)
  const height = full.height * (displayHeight / props.canvasHeight)
  const cx = ((layer.x + displayWidth / 2) / props.canvasWidth - 0.5) * full.width
  const cy = (0.5 - (layer.y + displayHeight / 2) / props.canvasHeight) * full.height
  return { width, height, cx, cy }
}

function planeZ(layer: LayerModel) {
  const siblings = props.layers
    .filter((item) => item.depth === layer.depth)
    .map((item) => item.id)
    .sort()
  const index = Math.max(0, siblings.indexOf(layer.id))
  return -layer.depth * SPACING - index * 0.02
}

function disposeMesh(mesh: THREE.Mesh) {
  mesh.geometry.dispose()
  const border = mesh.children[0]
  if (border instanceof THREE.LineSegments) {
    border.geometry.dispose()
    const material = border.material
    if (Array.isArray(material)) material.forEach((item) => item.dispose())
    else material.dispose()
  }
  const material = mesh.material
  if (Array.isArray(material)) material.forEach((item) => item.dispose())
  else material.dispose()
}

function setBorder(record: PlaneRecord, active: boolean) {
  const material = record.border.material
  if (material instanceof THREE.LineBasicMaterial) material.color.set(active ? 0xffb703 : 0x6a6a6a)
}

function createPlane(layer: LayerModel): PlaneRecord {
  const place = planePlacement(layer)
  const geometry = new THREE.PlaneGeometry(place.width, place.height)
  const material = new THREE.MeshBasicMaterial({
    map: textureFor(layer.imageUrl),
    alphaTest: 0.5,
    side: THREE.DoubleSide,
    depthWrite: true,
  })
  const mesh = new THREE.Mesh(geometry, material)
  mesh.name = layer.id
  const border = new THREE.LineSegments(
    new THREE.EdgesGeometry(geometry),
    new THREE.LineBasicMaterial({ color: 0x6a6a6a }),
  )
  border.position.z = 0.02
  mesh.add(border)
  return { mesh, border, url: layer.imageUrl }
}

function syncPlanes() {
  if (!scene) return
  const alive = new Set(props.layers.map((layer) => layer.id))
  for (const [id, record] of records) {
    if (alive.has(id)) continue
    planes.remove(record.mesh)
    disposeMesh(record.mesh)
    records.delete(id)
  }
  for (const layer of props.layers) {
    let record = records.get(layer.id)
    if (!record || record.url !== layer.imageUrl) {
      if (record) {
        planes.remove(record.mesh)
        disposeMesh(record.mesh)
      }
      record = createPlane(layer)
      records.set(layer.id, record)
      planes.add(record.mesh)
    } else {
      const place = planePlacement(layer)
      record.mesh.scale.set(1, 1, 1)
      record.mesh.geometry.dispose()
      record.mesh.geometry = new THREE.PlaneGeometry(place.width, place.height)
      record.border.geometry.dispose()
      record.border.geometry = new THREE.EdgesGeometry(record.mesh.geometry)
    }
    const place = planePlacement(layer)
    record.mesh.position.set(place.cx, place.cy, planeZ(layer))
    record.mesh.visible = layer.visible
    setBorder(record, layer.id === props.activeLayerId)
  }
  if (hitPlane) {
    const { width, height } = worldSize()
    hitPlane.geometry.dispose()
    hitPlane.geometry = new THREE.PlaneGeometry(width, height)
  }
}

function pixelToWorld(x: number, y: number, slotDepth: number) {
  const { width, height } = worldSize()
  return new THREE.Vector3(
    (x / props.canvasWidth - 0.5) * width,
    (0.5 - y / props.canvasHeight) * height,
    -slotDepth * SPACING,
  )
}

function clearStrokes() {
  for (const child of [...strokes.children]) {
    strokes.remove(child)
    const geometry = (child as THREE.Object3D & { geometry?: THREE.BufferGeometry }).geometry
    geometry?.dispose()
    const material = (child as THREE.Object3D & { material?: THREE.Material | THREE.Material[] }).material
    if (Array.isArray(material)) material.forEach((item) => item.dispose())
    else material?.dispose()
  }
  lineMaterials.length = 0
}

function updateLineResolution() {
  if (!renderer) return
  const width = renderer.domElement.clientWidth
  const height = renderer.domElement.clientHeight
  for (const material of lineMaterials) material.resolution.set(width, height)
}

function addLine(positions: number[], color: number, dashed: boolean) {
  if (!renderer || positions.length < 6) return
  const geometry = new LineGeometry()
  geometry.setPositions(positions)
  const material = new LineMaterial({
    color,
    linewidth: 4,
    depthTest: props.mode === 'observe',
    depthWrite: false,
    dashed,
    dashSize: 6,
    gapSize: 4,
  })
  material.resolution.set(renderer.domElement.clientWidth, renderer.domElement.clientHeight)
  const line = new Line2(geometry, material)
  line.frustumCulled = false
  if (dashed) line.computeLineDistances()
  line.renderOrder = 2
  strokes.add(line)
  lineMaterials.push(material)
}

function addDot(x: number, y: number, slotDepth: number, color: number) {
  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(0.035, 14, 10),
    new THREE.MeshBasicMaterial({ color, depthTest: props.mode === 'observe' }),
  )
  mesh.position.copy(pixelToWorld(x, y, slotDepth))
  mesh.renderOrder = 3
  strokes.add(mesh)
}

function strokeDepth(slotDepth: number) {
  return props.mode === 'draw' ? 0 : slotDepth
}

function drawLive() {
  if (livePoints.length === 1) {
    const only = livePoints[0]
    if (only) addDot(only.x, only.y, 0, 0xffffff)
    return
  }
  const positions: number[] = []
  for (const point of livePoints) {
    const world = pixelToWorld(point.x, point.y, 0)
    positions.push(world.x, world.y, world.z)
  }
  addLine(positions, 0xffffff, false)
}

function drawTrack(track: Track) {
  for (const segment of track.segments) {
    const positions: number[] = []
    const color = segment.relation === 'off' ? 0xb0b0b0 : bandColor(segment.label)
    for (const point of segment.points) {
      const world = pixelToWorld(point.x, point.y, strokeDepth(point.slotDepth))
      positions.push(world.x, world.y, world.z)
    }
    if (segment.points.length === 1) {
      const only = segment.points[0]
      if (only) addDot(only.x, only.y, strokeDepth(only.slotDepth), color)
    } else {
      addLine(positions, color, segment.relation === 'off')
    }
  }
  for (const point of track.breaks) addDot(point.x, point.y, props.mode === 'draw' ? 0 : 0.15, 0xff5a5a)
}

function syncStroke() {
  clearStrokes()
  if (drawing) {
    drawLive()
    return
  }
  if (props.track) {
    drawTrack(props.track)
    return
  }
  if (livePoints.length >= 2) drawLive()
}

function pointerPixel(event: PointerEvent) {
  if (!renderer || !camera || !hitPlane) return null
  const rect = renderer.domElement.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) return null
  const ndc = new THREE.Vector2(
    ((event.clientX - rect.left) / rect.width) * 2 - 1,
    -((event.clientY - rect.top) / rect.height) * 2 + 1,
  )
  raycaster.setFromCamera(ndc, camera)
  const hit = raycaster.intersectObject(hitPlane)[0]
  if (!hit) return null
  const { width, height } = worldSize()
  return {
    x: (hit.point.x / width + 0.5) * props.canvasWidth,
    y: (0.5 - hit.point.y / height) * props.canvasHeight,
  }
}

function layerAt(pixel: { x: number; y: number }) {
  const ordered = [...props.layers].sort((left, right) => left.depth - right.depth)
  for (const layer of ordered) {
    if (!layer.visible) continue
    const width = layer.pixelWidth * layer.scale
    const height = layer.pixelHeight * layer.scale
    if (pixel.x >= layer.x && pixel.x <= layer.x + width && pixel.y >= layer.y && pixel.y <= layer.y + height) {
      return layer
    }
  }
  return null
}

function onPointerDown(event: PointerEvent) {
  if (props.mode === 'observe') return
  const pixel = pointerPixel(event)
  if (!pixel) return
  if (props.mode === 'edit') {
    const hit = layerAt(pixel)
    if (hit) emit('select', hit.id)
    const layer = hit ?? props.layers.find((item) => item.id === props.activeLayerId) ?? null
    if (!layer) return
    editing = true
    editLayer = { ...layer }
    editOrigin = { x: layer.x, y: layer.y }
    editStart = pixel
    try {
      renderer?.domElement.setPointerCapture(event.pointerId)
    } catch {
      // A programmatic pointer has no active id to capture.
    }
    return
  }
  drawing = true
  livePoints = [pixel]
  try {
    renderer?.domElement.setPointerCapture(event.pointerId)
  } catch {
    // A programmatic pointer has no active id to capture.
  }
  syncStroke()
}

function onPointerMove(event: PointerEvent) {
  if (props.mode === 'edit') {
    if (!editing || !editLayer || !editOrigin || !editStart) return
    const pixel = pointerPixel(event)
    if (!pixel) return
    const next = {
      id: editLayer.id,
      x: Math.round(editOrigin.x + (pixel.x - editStart.x)),
      y: Math.round(editOrigin.y + (pixel.y - editStart.y)),
      scale: editLayer.scale,
    }
    emit('transform', next)
    return
  }
  if (!drawing) return
  const pixel = pointerPixel(event)
  if (!pixel) return
  const last = livePoints[livePoints.length - 1]
  if (last && Math.hypot(pixel.x - last.x, pixel.y - last.y) < 1.5) return
  livePoints.push(pixel)
  syncStroke()
}

function onPointerUp(event: PointerEvent) {
  try {
    if (renderer?.domElement.hasPointerCapture(event.pointerId)) {
      renderer.domElement.releasePointerCapture(event.pointerId)
    }
  } catch {
    // The pointer was not captured.
  }
  if (props.mode === 'edit') {
    editing = false
    editLayer = null
    editOrigin = null
    editStart = null
    return
  }
  if (!drawing) return
  drawing = false
  if (livePoints.length >= 2) emit('stroke', livePoints.map((point) => [point.x, point.y]))
  else {
    livePoints = []
    syncStroke()
  }
}

function onWheel(event: WheelEvent) {
  if (props.mode !== 'edit') return
  const layer = props.layers.find((item) => item.id === props.activeLayerId)
  if (!layer) return
  event.preventDefault()
  const factor = event.deltaY < 0 ? 1.06 : 1 / 1.06
  const scale = Math.min(20, Math.max(0.05, Number((layer.scale * factor).toFixed(4))))
  emit('transform', { id: layer.id, x: layer.x, y: layer.y, scale })
}

function resize() {
  if (!renderer || !host.value) return
  const width = host.value.clientWidth
  const height = host.value.clientHeight
  if (width === 0 || height === 0) return
  renderer.setSize(width, height, false)
  updateFrustum()
  updateLineResolution()
}

function animate() {
  frameId = requestAnimationFrame(animate)
  if (props.mode === 'observe') controls?.update()
  if (renderer && scene && camera) renderer.render(scene, camera)
}

function init() {
  const element = host.value
  if (!element) return
  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x141414)
  camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.01, 200)
  renderer = new THREE.WebGLRenderer({ antialias: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.outputColorSpace = THREE.SRGBColorSpace
  element.appendChild(renderer.domElement)
  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = false
  controls.enabled = false
  const { width, height } = worldSize()
  hitPlane = new THREE.Mesh(
    new THREE.PlaneGeometry(width, height),
    new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false, colorWrite: false }),
  )
  scene.add(hitPlane)
  scene.add(planes)
  scene.add(strokes)
  renderer.domElement.addEventListener('pointerdown', onPointerDown)
  renderer.domElement.addEventListener('pointermove', onPointerMove)
  renderer.domElement.addEventListener('pointerup', onPointerUp)
  renderer.domElement.addEventListener('pointercancel', onPointerUp)
  renderer.domElement.addEventListener('wheel', onWheel, { passive: false })
  renderer.domElement.style.touchAction = 'none'
  if (props.mode === 'observe') frameObserve()
  else if (props.mode === 'edit') frameEdit()
  else frameDraw()
  syncPlanes()
  syncStroke()
  resize()
  animate()
}

onMounted(() => {
  init()
  if (host.value) {
    observer = new ResizeObserver(resize)
    observer.observe(host.value)
  }
})

onBeforeUnmount(() => {
  cancelAnimationFrame(frameId)
  observer?.disconnect()
  renderer?.domElement.removeEventListener('pointerdown', onPointerDown)
  renderer?.domElement.removeEventListener('pointermove', onPointerMove)
  renderer?.domElement.removeEventListener('pointerup', onPointerUp)
  renderer?.domElement.removeEventListener('pointercancel', onPointerUp)
  renderer?.domElement.removeEventListener('wheel', onWheel)
  controls?.dispose()
  clearStrokes()
  for (const record of records.values()) disposeMesh(record.mesh)
  records.clear()
  for (const texture of textures.values()) texture.dispose()
  textures.clear()
  hitPlane?.geometry.dispose()
  renderer?.dispose()
})

watch(
  () =>
    props.layers
      .map(
        (layer) =>
          `${layer.id}:${layer.depth}:${layer.imageUrl}:${layer.x}:${layer.y}:${layer.scale}:${layer.visible ? 1 : 0}`,
      )
      .join('|'),
  () => syncPlanes(),
)
watch(
  () => props.activeLayerId,
  () => {
    for (const layer of props.layers) {
      const record = records.get(layer.id)
      if (record) setBorder(record, layer.id === props.activeLayerId)
    }
  },
)
watch(
  () => props.track,
  () => syncStroke(),
  { deep: true },
)
watch(
  () => props.inkGeneration,
  () => {
    drawing = false
    livePoints = []
    syncStroke()
  },
)
watch(
  () => props.mode,
  (mode) => {
    drawing = false
    editing = false
    editLayer = null
    editOrigin = null
    editStart = null
    if (mode === 'observe') frameObserve()
    else if (mode === 'edit') frameEdit()
    else frameDraw()
    syncStroke()
  },
)
watch(
  () => [props.canvasWidth, props.canvasHeight],
  () => {
    syncPlanes()
    if (props.mode === 'observe') frameObserve()
    else if (props.mode === 'edit') frameEdit()
    else frameDraw()
    syncStroke()
  },
)
</script>

<template>
  <div class="viewport">
    <div ref="host" class="host" />
    <button v-if="mode === 'observe'" type="button" class="reset-view" @click="resetToDrawView">回正视角</button>
    <p class="hint">{{ hint }}</p>
  </div>
</template>

<style scoped>
.viewport {
  position: relative;
  height: 100%;
  min-width: 0;
  background: #141414;
}
.host {
  position: absolute;
  inset: 0;
}
.host :deep(canvas) {
  display: block;
  width: 100%;
  height: 100%;
}
.reset-view {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 2;
  border: 1px solid #3d3d3d;
  border-radius: 6px;
  background: rgb(26 26 26 / 88%);
  color: #ececec;
  font: inherit;
  font-size: 12px;
  padding: 6px 10px;
  cursor: pointer;
}
.reset-view:hover {
  border-color: #f0a202;
}
.hint {
  position: absolute;
  left: 12px;
  bottom: 12px;
  margin: 0;
  padding: 4px 8px;
  border-radius: 4px;
  background: rgb(0 0 0 / 45%);
  color: #d7d7d7;
  font-size: 12px;
  pointer-events: none;
}
</style>
