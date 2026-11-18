export type LayerModel = {
  id: string
  name: string
  depth: number
  x: number
  y: number
  scale: number
  background: boolean
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
