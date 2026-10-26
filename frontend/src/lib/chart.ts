/** Round-numbered axis ticks whose range always covers [min, max], so no mark is clipped. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) return max === 0 ? [0, 1] : [Math.min(0, min), Math.max(0, max)]
  const span = max - min
  const mag = 10 ** Math.floor(Math.log10(span / count))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => Math.ceil(max / s) - Math.floor(min / s) <= count) ?? 10 * mag
  const first = Math.floor(min / step)
  const last = Math.ceil(max / step)
  const ticks = []
  for (let i = first; i <= last; i++) ticks.push(Number((i * step).toPrecision(12)))
  return ticks
}
