import clsx from 'clsx'
import { Calculator, Check, CircleAlert, Download, Table2, Database, BarChart3, Loader2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Artifact, ChartArtifact, TableArtifact, ToolCall } from '../api/types'
import { niceTicks } from '../lib/chart'

const TOOL_LABELS: Record<string, { label: string; Icon: typeof Database }> = {
  list_datasets: { label: 'Listed datasets', Icon: Database },
  describe_dataset: { label: 'Profiled dataset', Icon: Database },
  query_dataset: { label: 'Queried data', Icon: Table2 },
  create_chart: { label: 'Created chart', Icon: BarChart3 },
  calculate: { label: 'Calculated', Icon: Calculator },
}

/** Shows which deterministic tools produced the numbers in this answer. */
export function ToolActivityList({ calls }: { calls: ToolCall[] }) {
  if (!calls.length) return null
  return (
    <ul className="mb-3 space-y-1 text-xs" aria-label="Analysis steps">
      {calls.map((c) => {
        const meta = TOOL_LABELS[c.name] ?? { label: c.name, Icon: Database }
        return (
          <li key={c.id} className={clsx('flex items-start gap-1.5', c.status === 'error' ? 'text-warning' : 'text-faint')}>
            {c.status === 'running' ? (
              <Loader2 className="mt-0.5 size-3.5 shrink-0 animate-spin" />
            ) : c.status === 'error' ? (
              <CircleAlert className="mt-0.5 size-3.5 shrink-0" />
            ) : (
              <Check className="mt-0.5 size-3.5 shrink-0 text-success" />
            )}
            <meta.Icon className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            <span>
              <span className="font-medium text-muted">{meta.label}</span>
              {c.summary && <span> · {c.summary}</span>}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return v.toLocaleString(undefined, { maximumFractionDigits: 4 })
  return String(v)
}

export function ResultTable({ table }: { table: TableArtifact }) {
  return (
    <figure className="overflow-hidden rounded-xl border border-border">
      <figcaption className="flex items-center justify-between gap-2 border-b border-border bg-surface-2 px-3 py-2 text-xs">
        <span className="font-medium text-text">{table.title}</span>
        <a
          href={`/api/analysis-results/${table.result_id}/download/`}
          className="inline-flex items-center gap-1 text-muted hover:text-text"
          aria-label={`Download ${table.title} as CSV`}
        >
          <Download className="size-3.5" /> CSV
        </a>
      </figcaption>
      <DataGrid columns={table.columns} rows={table.rows} />
      <p className="border-t border-border px-3 py-1.5 text-xs text-faint">
        Showing {table.rows.length.toLocaleString()} of {table.total_rows.toLocaleString()} row{table.total_rows === 1 ? '' : 's'} · computed from your data
      </p>
    </figure>
  )
}

function DataGrid({ columns, rows }: { columns: string[]; rows: unknown[][] }) {
  return (
    <div className="max-h-80 overflow-auto">
      <table className="w-full border-collapse text-xs">
        <thead className="sticky top-0 bg-surface">
          <tr>
            {columns.map((c) => (
              <th key={c} scope="col" className="border-b border-border px-3 py-1.5 text-left font-medium whitespace-nowrap text-muted">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="odd:bg-surface-2/40">
              {row.map((v, j) => (
                <td key={j} className={clsx('px-3 py-1 whitespace-nowrap', typeof v === 'number' && 'text-right tabular-nums')}>
                  {formatCell(v)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------- chart

const HEIGHT = 240
const PAD = { top: 12, right: 12, bottom: 34, left: 52 }

function compact(v: number): string {
  return Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(v)
}

function shortLabel(v: unknown): string {
  const s = String(v ?? '—')
  if (/^\d{4}-\d{2}-\d{2}T/.test(s)) return s.slice(0, 10)
  return s.length > 12 ? `${s.slice(0, 11)}…` : s
}

export function ChartView({ chart }: { chart: ChartArtifact }) {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(560)
  const [hover, setHover] = useState<number | null>(null)
  const [showTable, setShowTable] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(260, entry.contentRect.width)))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const { data, y: series } = chart
  const values = data.flatMap((d) => series.map((s) => d[s])).filter((v): v is number => typeof v === 'number')
  const ticks = useMemo(() => niceTicks(Math.min(0, ...values), Math.max(0, ...values)), [values])
  const yMin = ticks[0]
  const yMax = ticks[ticks.length - 1]
  const plotW = width - PAD.left - PAD.right
  const plotH = HEIGHT - PAD.top - PAD.bottom
  const yPos = (v: number) => PAD.top + plotH - ((v - yMin) / (yMax - yMin || 1)) * plotH
  const band = plotW / Math.max(1, data.length)
  const xCenter = (i: number) => PAD.left + band * i + band / 2
  const labelEvery = Math.max(1, Math.ceil(data.length / Math.max(1, Math.floor(plotW / 64))))
  const color = (i: number) => `var(--series-${i + 1})`
  const hovered = hover === null ? null : data[hover]

  return (
    <figure className="rounded-xl border border-border p-3">
      <figcaption className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium">{chart.title}</span>
        <button
          type="button"
          onClick={() => setShowTable((v) => !v)}
          aria-pressed={showTable}
          className="rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-2 hover:text-text"
        >
          {showTable ? 'Show chart' : 'Show table'}
        </button>
      </figcaption>
      {series.length > 1 && (
        <ul className="mt-2 flex flex-wrap gap-3 text-xs text-muted" aria-label="Legend">
          {series.map((s, i) => (
            <li key={s} className="flex items-center gap-1.5">
              <span className="inline-block size-2.5 rounded-sm" style={{ background: color(i) }} aria-hidden="true" />
              {s}
            </li>
          ))}
        </ul>
      )}
      {showTable ? (
        <div className="mt-2 rounded-lg border border-border">
          <DataGrid columns={[chart.x, ...series]} rows={data.map((d) => [d.x, ...series.map((s) => d[s])])} />
        </div>
      ) : (
        <div ref={ref} className="relative mt-2" onMouseLeave={() => setHover(null)}>
          <svg width={width} height={HEIGHT} role="img" aria-label={`${chart.chart_type} chart: ${chart.title}`} className="block max-w-full">
            {ticks.map((t) => (
              <g key={t}>
                <line x1={PAD.left} x2={width - PAD.right} y1={yPos(t)} y2={yPos(t)} stroke="var(--border)" strokeWidth={t === 0 ? 1.5 : 1} />
                <text x={PAD.left - 8} y={yPos(t)} dy="0.32em" textAnchor="end" fontSize={11} fill="var(--text-faint)">
                  {compact(t)}
                </text>
              </g>
            ))}
            {data.map((d, i) =>
              i % labelEvery === 0 ? (
                <text key={i} x={xCenter(i)} y={HEIGHT - PAD.bottom + 16} textAnchor="middle" fontSize={11} fill="var(--text-faint)">
                  {shortLabel(d.x)}
                </text>
              ) : null,
            )}

            {chart.chart_type === 'bar' &&
              data.map((d, i) => {
                const inner = Math.min(band * 0.75, 48 * series.length)
                const barW = Math.max(2, (inner - 2 * (series.length - 1)) / series.length)
                const start = xCenter(i) - inner / 2
                return series.map((s, j) => {
                  const v = typeof d[s] === 'number' ? (d[s] as number) : 0
                  const top = yPos(Math.max(v, 0))
                  const h = Math.abs(yPos(v) - yPos(0))
                  const r = Math.min(4, barW / 2, h)
                  const x = start + j * (barW + 2)
                  // Rounded data end, square at the baseline.
                  const path = v >= 0
                    ? `M${x},${top + h} V${top + r} Q${x},${top} ${x + r},${top} H${x + barW - r} Q${x + barW},${top} ${x + barW},${top + r} V${top + h} Z`
                    : `M${x},${top} V${top + h - r} Q${x},${top + h} ${x + r},${top + h} H${x + barW - r} Q${x + barW},${top + h} ${x + barW},${top + h - r} V${top} Z`
                  return <path key={`${i}-${s}`} d={path} fill={color(j)} opacity={hover === null || hover === i ? 1 : 0.55} />
                })
              })}

            {chart.chart_type === 'line' &&
              series.map((s, j) => {
                const pts = data
                  .map((d, i) => (typeof d[s] === 'number' ? `${xCenter(i)},${yPos(d[s] as number)}` : null))
                  .filter(Boolean)
                return <polyline key={s} points={pts.join(' ')} fill="none" stroke={color(j)} strokeWidth={2} strokeLinejoin="round" />
              })}

            {(chart.chart_type === 'scatter' || (chart.chart_type === 'line' && data.length <= 30)) &&
              series.map((s, j) =>
                data.map((d, i) =>
                  typeof d[s] === 'number' ? (
                    <circle key={`${s}-${i}`} cx={xCenter(i)} cy={yPos(d[s] as number)} r={4} fill={color(j)} stroke="var(--surface)" strokeWidth={2} />
                  ) : null,
                ),
              )}

            {hover !== null && chart.chart_type !== 'bar' && (
              <line x1={xCenter(hover)} x2={xCenter(hover)} y1={PAD.top} y2={PAD.top + plotH} stroke="var(--text-faint)" strokeDasharray="3 3" />
            )}
            {/* Invisible hit targets, wider than the marks. */}
            {data.map((_, i) => (
              <rect key={i} x={PAD.left + band * i} y={PAD.top} width={band} height={plotH} fill="transparent" onMouseEnter={() => setHover(i)} onFocus={() => setHover(i)} />
            ))}
          </svg>
          {hovered && hover !== null && (
            <div
              role="tooltip"
              className="pointer-events-none absolute top-1 z-10 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs shadow-card"
              style={{ left: Math.min(Math.max(xCenter(hover) - 70, 0), width - 150) }}
            >
              <p className="font-medium">{String(hovered.x ?? '—')}</p>
              {series.map((s, j) => (
                <p key={s} className="flex items-center gap-1.5 text-muted">
                  <span className="inline-block size-2 rounded-sm" style={{ background: color(j) }} aria-hidden="true" />
                  {s}: <span className="text-text tabular-nums">{formatCell(hovered[s])}</span>
                </p>
              ))}
            </div>
          )}
        </div>
      )}
      {chart.truncated && <p className="mt-1 text-xs text-faint">Showing the first {chart.points} points.</p>}
    </figure>
  )
}

export function ArtifactList({ artifacts }: { artifacts: Artifact[] }) {
  if (!artifacts.length) return null
  // Charts first: a chart's table is reachable via "Show table"; tables used for a chart are still listed.
  return (
    <div className="mt-3 space-y-3">
      {artifacts.map((a, i) => (a.type === 'chart' ? <ChartView key={i} chart={a} /> : <ResultTable key={i} table={a} />))}
    </div>
  )
}
