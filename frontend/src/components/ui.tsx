import clsx from 'clsx'
import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

const variants: Record<Variant, string> = {
  primary: 'bg-accent text-accent-contrast hover:bg-accent-strong',
  secondary: 'border border-border bg-surface text-text hover:bg-surface-2',
  ghost: 'text-muted hover:bg-surface-2 hover:text-text',
  danger: 'bg-danger text-white hover:opacity-90',
}

export function Button({
  variant = 'primary',
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; children: ReactNode }) {
  return (
    <button
      {...props}
      className={clsx(
        'inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        variants[variant],
        className,
      )}
    >
      {children}
    </button>
  )
}

export function IconButton({
  label,
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; children: ReactNode }) {
  return (
    <button
      {...props}
      aria-label={label}
      title={label}
      className={clsx(
        'inline-flex size-8 items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-text disabled:opacity-40',
        className,
      )}
    >
      {children}
    </button>
  )
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={clsx('inline-block size-4 animate-spin rounded-full border-2 border-current border-r-transparent', className)}
    />
  )
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={clsx('inline-flex items-center gap-2 font-semibold tracking-tight', className)}>
      <svg viewBox="0 0 32 32" className="size-7" aria-hidden="true">
        <rect width="32" height="32" rx="8" className="fill-accent" />
        <path d="M16 6 25 26h-4.2l-1.7-4h-6.2l-1.7 4H7L16 6Zm0 7.6-2.1 5.1h4.2L16 13.6Z" className="fill-accent-contrast" />
      </svg>
      Aether
    </span>
  )
}
