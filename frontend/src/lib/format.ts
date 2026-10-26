export function formatTokens(n: number | null | undefined): string {
  if (n == null) return '—'
  return n >= 1000 ? `${(n / 1000).toFixed(n >= 10_000 ? 0 : 1)}k` : String(n)
}

export function formatCost(usd: string | null | undefined): string | null {
  if (usd == null) return null
  const v = Number(usd)
  if (v === 0) return '$0'
  return v < 0.01 ? `<$0.01` : `$${v.toFixed(2)}`
}

/** Groups conversations for the sidebar: Today / Previous 7 days / Older. */
export function dateGroup(iso: string, now = new Date()): string {
  const d = new Date(iso)
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  if (d.getTime() >= startOfToday) return 'Today'
  if (d.getTime() >= startOfToday - 7 * 86_400_000) return 'Previous 7 days'
  return 'Older'
}
