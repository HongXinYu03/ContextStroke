/** Default hues spaced by the golden angle so neighboring depth indices stay distinct. */
const GOLDEN = 137.508
const STORAGE_KEY = 'contextstroke.bandColors'

/** Legend / storage key for off (blank) stroke segments. */
export const OFF_LABEL = '空白'
export const DEFAULT_OFF_HEX = '#b0b0b0'

export type BandColorMap = Record<string, string>

export function defaultBandHex(label: string): string {
  if (label === OFF_LABEL) return DEFAULT_OFF_HEX
  const match = /^(\d+)-\d+$/.exec(label)
  if (match?.[1] === undefined) return DEFAULT_OFF_HEX
  const index = Number(match[1])
  return hslToHex((index * GOLDEN) % 360, 72, 56)
}

export function offHex(overrides?: BandColorMap): string {
  return bandHex(OFF_LABEL, overrides)
}

export function offColor(overrides?: BandColorMap): number {
  return bandColor(OFF_LABEL, overrides)
}

export function bandHex(label: string, overrides?: BandColorMap): string {
  const custom = overrides?.[label]
  if (custom && /^#[0-9a-fA-F]{6}$/.test(custom)) return custom.toLowerCase()
  return defaultBandHex(label)
}

export function bandColor(label: string, overrides?: BandColorMap): number {
  const hex = bandHex(label, overrides)
  return Number.parseInt(hex.slice(1), 16)
}

export function loadBandColors(): BandColorMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object') return {}
    const next: BandColorMap = {}
    for (const [label, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof value === 'string' && /^#[0-9a-fA-F]{6}$/.test(value)) next[label] = value.toLowerCase()
    }
    return next
  } catch {
    return {}
  }
}

export function saveBandColors(map: BandColorMap): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(map))
}

function hslToHex(h: number, s: number, l: number): string {
  const sat = s / 100
  const light = l / 100
  const chroma = (1 - Math.abs(2 * light - 1)) * sat
  const x = chroma * (1 - Math.abs(((h / 60) % 2) - 1))
  const m = light - chroma / 2
  let r = 0
  let g = 0
  let b = 0
  if (h < 60) [r, g, b] = [chroma, x, 0]
  else if (h < 120) [r, g, b] = [x, chroma, 0]
  else if (h < 180) [r, g, b] = [0, chroma, x]
  else if (h < 240) [r, g, b] = [0, x, chroma]
  else if (h < 300) [r, g, b] = [x, 0, chroma]
  else [r, g, b] = [chroma, 0, x]
  const to = (channel: number) =>
    Math.round((channel + m) * 255)
      .toString(16)
      .padStart(2, '0')
  return `#${to(r)}${to(g)}${to(b)}`
}
