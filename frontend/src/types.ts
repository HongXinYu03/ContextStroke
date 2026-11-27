export type LayerModel = {
  id: string
  name: string
  depth: number
  x: number
  y: number
  scale: number
  background: boolean
  /** Frontend-only: hide plane in the viewport without deleting the layer. */
  visible: boolean
  pixelWidth: number
  pixelHeight: number
  imageUrl: string
}

export type SceneSummary = {
  id: string
  name: string
}

export type SceneDetail = {
  id: string
  name: string
  width: number
  height: number
  metersPerPixel: number | null
  layers: LayerModel[]
}

export type Hit = {
  id: string
  name: string
  depth: number
}

export type StrokePoint = {
  sample: number
  x: number
  y: number
  slotDepth: number
}

export type Segment = {
  start: number
  end: number
  relation: 'band' | 'off'
  label: string
  layerIds: string[]
  slotDepth: number | null
  points: StrokePoint[]
}

export type Track = {
  id: string
  cost: number | null
  selected: boolean
  summary: string
  segments: Segment[]
  breaks: { x: number; y: number }[]
}

export type SolveResult = {
  status: 'ok' | 'all_off' | 'discontinuous' | 'insufficient_input'
  message: string
  samples: { x: number; y: number; on: boolean; hits: Hit[] }[]
  sequences: { start: number; end: number; on: boolean }[]
  discontinuities: number[]
  tracks: Track[]
}

export type ViewMode = 'draw' | 'edit' | 'observe'

export type MetricSource = 'manual' | 'estimated' | 'unknown'

export type GraphMetric = {
  width: number | null
  height: number | null
  widthSource: MetricSource
  heightSource: MetricSource
  source: MetricSource | 'mixed'
}

export type GraphNode = {
  id: string
  layerId: string
  name: string
  category: string
  depth: number
  center: [number, number]
  centroid: [number, number]
  bbox: [number, number, number, number]
  pixelSize: [number, number]
  areaPx: number
  metric: GraphMetric
  annotated: boolean
}

export type GraphOcclusion = {
  occluded: boolean
  occluder: string | null
  overlapRatio: number
  coplanarOverlap: boolean
}

export type GraphEdge = {
  id: string
  u: string
  v: string
  dx: number
  dy: number
  distance: number
  angleDeg: number
  direction: string
  depthDelta: number
  sameLayer: boolean
  occlusion: GraphOcclusion
}

export type GraphFrame = {
  x: number
  y: number
  width: number
  height: number
  source: 'background' | 'canvas'
}

export type UnmatchedAnnotation = {
  layerId: string
  layerName: string
  seed: [number, number]
  category: string | null
  metricWidth: number | null
  metricHeight: number | null
}

export type SceneGraph = {
  frame: GraphFrame
  metersPerPixel: number | null
  metersPerPixelSource: 'manual' | 'derived' | null
  nodes: GraphNode[]
  edges: GraphEdge[]
  unmatchedAnnotations: UnmatchedAnnotation[]
}

export type WorkspaceView = 'viewport' | 'split' | 'graph'
export type GraphEdgeFilter = 'all' | 'occluded' | 'selected'
