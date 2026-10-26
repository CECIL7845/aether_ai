import { Monitor, Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'
import clsx from 'clsx'
import { auth, usage as usageApi } from '../api/endpoints'
import type { ModelsResponse, UsageResponse } from '../api/types'
import { Button, Spinner } from '../components/ui'
import { useAuth } from '../lib/auth'
import { formatTokens } from '../lib/format'
import { useToast } from '../lib/toast'
import type { ThemeChoice } from '../lib/theme'

function Meter({ label, value, max, display }: { label: string; value: number; max: number; display: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div>
      <div className="flex justify-between text-sm">
        <span>{label}</span>
        <span className="text-muted">{display}</span>
      </div>
      <div
        className="mt-1.5 h-2 overflow-hidden rounded-full bg-surface-3"
        role="progressbar"
        aria-label={label}
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className={clsx('h-full rounded-full', pct >= 90 ? 'bg-danger' : 'bg-accent')} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export function SettingsView({
  theme,
  setTheme,
  models,
}: {
  theme: ThemeChoice
  setTheme: (t: ThemeChoice) => void
  models: ModelsResponse | null
}) {
  const { user, setUser } = useAuth()
  const toast = useToast()
  const [usage, setUsage] = useState<UsageResponse | null>(null)
  const [name, setName] = useState(user?.display_name ?? '')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    usageApi.me().then(setUsage).catch((e) => toast('error', e.message))
  }, [toast])

  const section = 'rounded-2xl border border-border bg-surface p-5'
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-2xl space-y-5 px-4 py-8">
        <h1 className="text-xl font-semibold">Settings</h1>

        <section className={section} aria-labelledby="profile-h">
          <h2 id="profile-h" className="font-medium">
            Profile
          </h2>
          <p className="mt-1 text-sm text-muted">{user?.email}</p>
          <form
            className="mt-4 flex gap-2"
            onSubmit={async (e) => {
              e.preventDefault()
              setSaving(true)
              try {
                setUser(await auth.updateMe({ display_name: name.trim() }))
                toast('success', 'Profile saved.')
              } catch (err) {
                toast('error', (err as Error).message)
              } finally {
                setSaving(false)
              }
            }}
          >
            <label htmlFor="display-name" className="sr-only">
              Display name
            </label>
            <input
              id="display-name"
              value={name}
              maxLength={120}
              onChange={(e) => setName(e.target.value)}
              placeholder="Display name"
              className="min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
            />
            <Button type="submit" variant="secondary" disabled={saving}>
              Save
            </Button>
          </form>
        </section>

        <section className={section} aria-labelledby="appearance-h">
          <h2 id="appearance-h" className="font-medium">
            Appearance
          </h2>
          <div className="mt-3 grid grid-cols-3 gap-2" role="radiogroup" aria-label="Theme">
            {(
              [
                ['system', 'System', Monitor],
                ['light', 'Light', Sun],
                ['dark', 'Dark', Moon],
              ] as const
            ).map(([value, label, Icon]) => (
              <button
                key={value}
                role="radio"
                aria-checked={theme === value}
                onClick={() => setTheme(value)}
                className={clsx(
                  'flex flex-col items-center gap-1.5 rounded-xl border px-3 py-3 text-sm',
                  theme === value ? 'border-accent bg-accent-soft text-text' : 'border-border text-muted hover:text-text',
                )}
              >
                <Icon className="size-4.5" />
                {label}
              </button>
            ))}
          </div>
        </section>

        <section className={section} aria-labelledby="usage-h">
          <h2 id="usage-h" className="font-medium">
            Usage
          </h2>
          {!usage ? (
            <div className="mt-4 text-muted">
              <Spinner />
            </div>
          ) : (
            <div className="mt-4 space-y-4">
              <Meter
                label="Tokens in the last 24 hours"
                value={usage.tokens_last_24h}
                max={usage.daily_token_limit}
                display={`${formatTokens(usage.tokens_last_24h)} / ${formatTokens(usage.daily_token_limit)}`}
              />
              <Meter
                label="Estimated spend this month"
                value={Number(usage.cost_this_month_usd)}
                max={Number(usage.monthly_cost_limit_usd)}
                display={`$${Number(usage.cost_this_month_usd).toFixed(2)} / $${Number(usage.monthly_cost_limit_usd).toFixed(2)}`}
              />
              <p className="text-xs text-faint">
                Spend is estimated from provider list prices. Models without a verified price count toward the token limit only.
              </p>
              {!usage.allowed && (
                <p role="alert" className="rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">
                  {usage.reason}
                </p>
              )}
            </div>
          )}
        </section>

        <section className={section} aria-labelledby="models-h">
          <h2 id="models-h" className="font-medium">
            Models on this workspace
          </h2>
          <ul className="mt-3 divide-y divide-border text-sm">
            {models?.models.map((m) => (
              <li key={m.id} className="flex items-center justify-between gap-3 py-2">
                <span className={clsx(!m.available && 'text-faint')}>{m.label}</span>
                <span className={clsx('text-xs', m.available ? 'text-success' : 'text-faint')}>
                  {m.available ? 'Available' : 'Not configured'}
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
