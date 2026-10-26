import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, describe, expect, it } from 'vitest'
import type { ChartArtifact } from '../api/types'
import { niceTicks } from '../lib/chart'
import { ChartView, ResultTable, ToolActivityList } from './Artifacts'

beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
})

const chart: ChartArtifact = {
  type: 'chart', chart_type: 'bar', title: 'Revenue by region', x: 'region', y: ['sum(revenue)'], points: 3,
  truncated: false,
  data: [{ x: 'Accra', 'sum(revenue)': 1910.5 }, { x: 'Kumasi', 'sum(revenue)': 1080 }, { x: 'Tamale', 'sum(revenue)': 0 }],
}

describe('ChartView', () => {
  it('renders an accessible bar chart with hover tooltip and a table fallback', async () => {
    const { container } = render(<ChartView chart={chart} />)
    expect(screen.getByRole('img', { name: 'bar chart: Revenue by region' })).toBeInTheDocument()
    expect(container.querySelectorAll('path')).toHaveLength(3)
    expect(screen.queryByLabelText('Legend')).toBeNull() // single series: the title names it
    fireEvent.mouseEnter(container.querySelectorAll('rect')[0])
    expect(screen.getByRole('tooltip')).toHaveTextContent('Accra')
    expect(screen.getByRole('tooltip')).toHaveTextContent('1,910.5')
    await userEvent.click(screen.getByRole('button', { name: 'Show table' }))
    expect(screen.getByRole('table')).toHaveTextContent('Kumasi')
  })

  it('shows a legend for multiple series', () => {
    render(<ChartView chart={{ ...chart, chart_type: 'line', y: ['a', 'b'], data: [{ x: 'Jan', a: 1, b: 2 }, { x: 'Feb', a: 3, b: 1 }] }} />)
    expect(screen.getByLabelText('Legend')).toHaveTextContent('a')
  })
})

describe('ResultTable', () => {
  it('shows counts, formats numbers and links the CSV download', () => {
    render(<ResultTable table={{ type: 'table', result_id: 7, title: 'Totals', columns: ['region', 'total'], rows: [['Accra', 1910.5], ['Tamale', null]], total_rows: 3 }} />)
    expect(screen.getByText('Showing 2 of 3 rows · computed from your data')).toBeInTheDocument()
    expect(screen.getByText('1,910.5')).toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Download Totals as CSV' })).toHaveAttribute('href', '/api/analysis-results/7/download/')
  })
})

describe('ToolActivityList', () => {
  it('lists completed and failed steps', () => {
    render(<ToolActivityList calls={[
      { id: '1', name: 'query_dataset', args: {}, status: 'done', summary: '3 result row(s)' },
      { id: '2', name: 'query_dataset', args: {}, status: 'error', summary: "Unknown column 'x'" },
    ]} />)
    expect(screen.getByLabelText('Analysis steps')).toHaveTextContent("Queried data · 3 result row(s)")
    expect(screen.getByLabelText('Analysis steps')).toHaveTextContent("Unknown column 'x'")
  })
})

describe('niceTicks', () => {
  it.each([[0, 1910.5], [0, 7], [-120, 480], [0, 0.034], [5, 5]])('covers the data range %s..%s', (min, max) => {
    const ticks = niceTicks(min, max)
    expect(ticks[0]).toBeLessThanOrEqual(min)
    expect(ticks[ticks.length - 1]).toBeGreaterThanOrEqual(max)
    expect(ticks.length).toBeLessThanOrEqual(6)
  })
})
