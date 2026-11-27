import type {
  GraphEdge,
  GraphNode,
  LayerModel,
  MetricSource,
  SceneDetail,
  SceneGraph,
  SceneSummary,
  Segment,
  SolveResult,
  StrokePoint,
  Track,
  UnmatchedAnnotation,
} from './types'

type RawLayer = {
  id: string
  name: string
  depth: number
  x: number
  y: number
  scale?: number
  background?: boolean
  pixel_width: number
  pixel_height: number
  image_url: string
}

type RawScene = {
  id: string
  name: string
  width: number
  height: number
  meters_per_pixel?: number | null
  layers: RawLayer[]
}

type RawGraphMetric = {
  width: number | null
  height: number | null
  width_source: MetricSource
  height_source: MetricSource
  source: MetricSource | 'mixed'
}

type RawGraphNode = {
  id: string
  layer_id: string
  name: string
  category: string
  depth: number
  center: [number, number]
  centroid: [number, number]
  bbox: [number, number, number, number]
  pixel_size: [number, number]
  area_px: number
  metric: RawGraphMetric
  annotated: boolean
}

type RawGraphOcclusion = {
  occluded: boolean
  occluder: string | null
  overlap_ratio: number
  coplanar_overlap: boolean
}

type RawGraphEdge = {
  id: string
  u: string
  v: string
  dx: number
  dy: number
  distance: number
  angle_deg: number
  direction: string
  depth_delta: number
  same_layer: boolean
  occlusion: RawGraphOcclusion
}

type RawUnmatchedAnnotation = {
  layer_id: string
  layer_name: string
  seed: [number, number]
  category: string | null
  metric_width: number | null
  metric_height: number | null
}

type RawSceneGraph = {
  frame: {
    x: number
    y: number
    width: number
    height: number
    source: 'background' | 'canvas'
  }
  meters_per_pixel: number | null
  meters_per_pixel_source: 'manual' | 'derived' | null
  nodes: RawGraphNode[]
  edges: RawGraphEdge[]
  unmatched_annotations: RawUnmatchedAnnotation[]
}

type RawPoint = { sample: number; x: number; y: number; slot_depth: number }

type RawSegment = {
  start: number
  end: number
  relation: Segment['relation']
  label: string
  layer_ids: string[]
  slot_depth: number | null
  points: RawPoint[]
}

type RawTrack = {
  id: string
  cost: number | null
  selected: boolean
  summary: string
  segments: RawSegment[]
  breaks: { x: number; y: number }[]
}

type RawSolve = {
  status: SolveResult['status']
  message: string
  samples: SolveResult['samples']
  sequences: SolveResult['sequences']
  discontinuities: number[]
  tracks: RawTrack[]
}

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    // The body is not JSON.
  }
  return `请求失败（${response.status}）`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch {
    throw new Error('无法连接后端，请确认 8001 端口已启动。')
  }
  if (!response.ok) throw new Error(await readError(response))
  return (await response.json()) as T
}

function mapLayer(layer: RawLayer): LayerModel {
  return {
    id: layer.id,
    name: layer.name,
    depth: layer.depth,
    x: layer.x,
    y: layer.y,
    scale: layer.scale && layer.scale > 0 ? layer.scale : 1,
    background: Boolean(layer.background),
    visible: true,
    pixelWidth: layer.pixel_width,
    pixelHeight: layer.pixel_height,
    imageUrl: layer.image_url,
  }
}

function mapPoint(point: RawPoint): StrokePoint {
  return { sample: point.sample, x: point.x, y: point.y, slotDepth: point.slot_depth }
}

function mapTrack(track: RawTrack): Track {
  return {
    id: track.id,
    cost: track.cost,
    selected: track.selected,
    summary: track.summary,
    breaks: track.breaks,
    segments: track.segments.map((segment) => ({
      start: segment.start,
      end: segment.end,
      relation: segment.relation,
      label: segment.label,
      layerIds: segment.layer_ids,
      slotDepth: segment.slot_depth,
      points: segment.points.map(mapPoint),
    })),
  }
}

export function fetchScenes(): Promise<SceneSummary[]> {
  return request<SceneSummary[]>('/api/scenes')
}

function mapScene(scene: RawScene): SceneDetail {
  return {
    id: scene.id,
    name: scene.name,
    width: scene.width,
    height: scene.height,
    metersPerPixel: scene.meters_per_pixel ?? null,
    layers: scene.layers.map(mapLayer),
  }
}

function mapGraphNode(node: RawGraphNode): GraphNode {
  return {
    id: node.id,
    layerId: node.layer_id,
    name: node.name,
    category: node.category,
    depth: node.depth,
    center: node.center,
    centroid: node.centroid,
    bbox: node.bbox,
    pixelSize: node.pixel_size,
    areaPx: node.area_px,
    metric: {
      width: node.metric.width,
      height: node.metric.height,
      widthSource: node.metric.width_source,
      heightSource: node.metric.height_source,
      source: node.metric.source,
    },
    annotated: node.annotated,
  }
}

function mapGraphEdge(edge: RawGraphEdge): GraphEdge {
  return {
    id: edge.id,
    u: edge.u,
    v: edge.v,
    dx: edge.dx,
    dy: edge.dy,
    distance: edge.distance,
    angleDeg: edge.angle_deg,
    direction: edge.direction,
    depthDelta: edge.depth_delta,
    sameLayer: edge.same_layer,
    occlusion: {
      occluded: edge.occlusion.occluded,
      occluder: edge.occlusion.occluder,
      overlapRatio: edge.occlusion.overlap_ratio,
      coplanarOverlap: edge.occlusion.coplanar_overlap,
    },
  }
}

function mapUnmatched(item: RawUnmatchedAnnotation): UnmatchedAnnotation {
  return {
    layerId: item.layer_id,
    layerName: item.layer_name,
    seed: item.seed,
    category: item.category,
    metricWidth: item.metric_width,
    metricHeight: item.metric_height,
  }
}

function mapSceneGraph(raw: RawSceneGraph): SceneGraph {
  return {
    frame: raw.frame,
    metersPerPixel: raw.meters_per_pixel,
    metersPerPixelSource: raw.meters_per_pixel_source,
    nodes: raw.nodes.map(mapGraphNode),
    edges: raw.edges.map(mapGraphEdge),
    unmatchedAnnotations: raw.unmatched_annotations.map(mapUnmatched),
  }
}

export async function fetchScene(id: string): Promise<SceneDetail> {
  return mapScene(await request<RawScene>(`/api/scenes/${id}`))
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = ''
  const chunk = 0x8000
  for (let index = 0; index < bytes.length; index += chunk) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunk))
  }
  return btoa(binary)
}

export async function addLayer(sceneId: string, file: File, depth: number): Promise<SceneDetail> {
  const bytes = new Uint8Array(await file.arrayBuffer())
  return mapScene(
    await request<RawScene>(`/api/scenes/${sceneId}/layers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: file.name, image_base64: bytesToBase64(bytes), depth }),
    }),
  )
}

export async function deleteLayer(sceneId: string, layerId: string): Promise<SceneDetail> {
  return mapScene(await request<RawScene>(`/api/scenes/${sceneId}/layers/${encodeURIComponent(layerId)}`, { method: 'DELETE' }))
}

export async function mergeLayers(sceneId: string, ids: [string, string], depth: number): Promise<SceneDetail> {
  return mapScene(
    await request<RawScene>(`/api/scenes/${sceneId}/layers/merge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids, depth }),
    }),
  )
}

export async function updateLayer(
  sceneId: string,
  layerId: string,
  body: { x?: number; y?: number; scale?: number; background?: boolean },
): Promise<SceneDetail> {
  return mapScene(
    await request<RawScene>(`/api/scenes/${sceneId}/layers/${encodeURIComponent(layerId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  )
}

export async function syncSceneDepths(sceneId: string, depths: Record<string, number>): Promise<SceneDetail> {
  return mapScene(
    await request<RawScene>(`/api/scenes/${sceneId}/depths`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ depths }),
    }),
  )
}

export async function exportScene(sceneId: string, depths: Record<string, number>): Promise<void> {
  let response: Response
  try {
    response = await fetch(`/api/scenes/${sceneId}/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ depths }),
    })
  } catch {
    throw new Error('无法连接后端，请确认 8001 端口已启动。')
  }
  if (!response.ok) throw new Error(await readError(response))
  const blob = await response.blob()
  const header = response.headers.get('Content-Disposition') ?? ''
  const matched = /filename\*?=(?:UTF-8''|")?([^\";]+)/i.exec(header)
  const filename = matched?.[1] ? decodeURIComponent(matched[1].replace(/"/g, '')) : `${sceneId}.zip`
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export async function importScene(file: File, name?: string): Promise<SceneDetail> {
  const body = new FormData()
  body.append('file', file)
  if (name) body.append('name', name)
  return mapScene(await request<RawScene>('/api/scenes/import', { method: 'POST', body }))
}

export async function solveStroke(body: {
  scene: string
  depths: Record<string, number>
  stroke: number[][]
}): Promise<SolveResult> {
  const result = await request<RawSolve>('/api/solve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return {
    status: result.status,
    message: result.message,
    samples: result.samples,
    sequences: result.sequences,
    discontinuities: result.discontinuities,
    tracks: result.tracks.map(mapTrack),
  }
}

export async function fetchSceneGraph(
  sceneId: string,
  depths?: Record<string, number>,
): Promise<SceneGraph> {
  const raw = await request<RawSceneGraph>(`/api/scenes/${encodeURIComponent(sceneId)}/graph`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(depths ? { depths } : {}),
  })
  return mapSceneGraph(raw)
}

export async function annotateInstance(
  sceneId: string,
  instanceId: string,
  body: {
    category?: string | null
    metric_width?: number | null
    metric_height?: number | null
    depths?: Record<string, number>
  },
): Promise<SceneGraph> {
  const raw = await request<RawSceneGraph>(
    `/api/scenes/${encodeURIComponent(sceneId)}/instances/${encodeURIComponent(instanceId)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  )
  return mapSceneGraph(raw)
}

export async function updateSceneMeta(
  sceneId: string,
  body: { meters_per_pixel: number | null },
): Promise<SceneDetail> {
  return mapScene(
    await request<RawScene>(`/api/scenes/${encodeURIComponent(sceneId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  )
}
