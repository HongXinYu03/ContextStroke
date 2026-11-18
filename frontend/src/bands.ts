const BANDS = [0xf0a202, 0x4ea1ff, 0x3dbe7a, 0xd46ad4, 0xff7a59, 0xf2d04b]

export function bandColor(label: string): number {
  const match = /^(\d+)-\d+$/.exec(label)
  const index = match?.[1] === undefined ? -1 : Number(match[1])
  if (index < 0) return 0xb0b0b0
  return BANDS[index % BANDS.length] ?? 0xb0b0b0
}

export function bandHex(label: string): string {
  return `#${bandColor(label).toString(16).padStart(6, '0')}`
}
