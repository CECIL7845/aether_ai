import { ChevronDown } from 'lucide-react'
import type { ModelInfo } from '../api/types'

export function ModelPicker({
  models,
  value,
  onChange,
  disabled,
}: {
  models: ModelInfo[]
  value: string
  onChange: (id: string) => void
  disabled?: boolean
}) {
  const available = models.filter((m) => m.available)
  if (!available.length) return <span className="text-sm text-danger">No models configured</span>
  const groups: Record<string, ModelInfo[]> = {}
  for (const m of available) (groups[m.provider] ??= []).push(m)
  return (
    <label className="relative inline-flex items-center">
      <span className="sr-only">Model</span>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="appearance-none rounded-lg bg-transparent py-1.5 pr-7 pl-2.5 text-sm font-medium text-text hover:bg-surface-2 disabled:opacity-50"
      >
        {Object.entries(groups).map(([provider, list]) => (
          <optgroup key={provider} label={provider === 'gemini' ? 'Google Gemini' : provider === 'anthropic' ? 'Anthropic Claude' : provider}>
            {list.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2 size-4 text-muted" aria-hidden="true" />
    </label>
  )
}
