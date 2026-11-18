export type DepthItem = { id: string; depth: number; background?: boolean }

export function groupByDepth<T extends DepthItem>(items: readonly T[]): { depth: number; items: T[] }[] {
  const depths = [...new Set(items.map((item) => item.depth))].sort((a, b) => a - b)
  return depths.map((depth) => ({
    depth,
    items: items.filter((item) => item.depth === depth),
  }))
}

export function pinBackground<T extends DepthItem>(items: readonly T[]): T[] {
  const background = items.find((item) => item.background)
  if (!background) return items.map((item) => ({ ...item }))
  const others = items.filter((item) => item.id !== background.id)
  const maxOther = others.reduce((max, item) => Math.max(max, item.depth), 0)
  return items.map((item) =>
    item.id === background.id
      ? { ...item, background: true, depth: maxOther + 1 }
      : { ...item, background: false },
  )
}

export function renormalize<T extends DepthItem>(items: readonly T[]): T[] {
  const depths = [...new Set(items.map((item) => item.depth))].sort((a, b) => a - b)
  const order = new Map(depths.map((depth, index) => [depth, index + 1]))
  return pinBackground(
    items.map((item) => {
      const depth = order.get(item.depth)
      return depth === undefined ? { ...item } : { ...item, depth }
    }),
  )
}

export function joinDepth<T extends DepthItem>(items: readonly T[], id: string, depth: number): T[] {
  const current = items.find((item) => item.id === id)
  if (!current) return [...items]
  if (current.background) return pinBackground(items)
  if (current.depth === depth) return pinBackground(items)
  return renormalize(items.map((item) => (item.id === id ? { ...item, depth } : { ...item })))
}

export function insertDepth<T extends DepthItem>(
  items: readonly T[],
  id: string,
  index: number,
  orderedDepths: readonly number[],
): T[] {
  const first = orderedDepths[0]
  const last = orderedDepths[orderedDepths.length - 1]
  let depth = 1
  if (orderedDepths.length === 0 || first === undefined || last === undefined) depth = 1
  else if (index <= 0) depth = first - 0.5
  else if (index >= orderedDepths.length) depth = last + 0.5
  else {
    const left = orderedDepths[index - 1]
    const right = orderedDepths[index]
    depth = left === undefined || right === undefined ? first : (left + right) / 2
  }
  return joinDepth(items, id, depth)
}

export function stepDepth<T extends DepthItem>(
  items: readonly T[],
  id: string,
  direction: 'nearer' | 'farther',
): T[] {
  const groups = groupByDepth(items)
  const current = items.find((item) => item.id === id)
  if (!current) return [...items]
  const groupIndex = groups.findIndex((group) => group.depth === current.depth)
  const group = groups[groupIndex]
  if (!group) return [...items]
  const neighbor = groups[groupIndex + (direction === 'nearer' ? -1 : 1)]
  if (!neighbor) {
    if (group.items.length === 1) return [...items]
    const depth = direction === 'nearer' ? current.depth - 0.5 : current.depth + 0.5
    return joinDepth(items, id, depth)
  }
  if (group.items.length > 1) return joinDepth(items, id, (group.depth + neighbor.depth) / 2)
  const from = group.depth
  const to = neighbor.depth
  return renormalize(
    items.map((item) => {
      if (item.depth === from) return { ...item, depth: to }
      if (item.depth === to) return { ...item, depth: from }
      return { ...item }
    }),
  )
}
