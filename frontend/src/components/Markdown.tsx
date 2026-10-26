import { memo, useState, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import remarkGfm from 'remark-gfm'
import { Check, Copy } from 'lucide-react'

function textOf(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join('')
  if (node && typeof node === 'object' && 'props' in node) {
    return textOf((node as { props: { children?: ReactNode } }).props.children)
  }
  return ''
}

export function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        } catch {
          // clipboard blocked; nothing else to do
        }
      }}
      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-3 hover:text-text"
    >
      {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      {copied ? 'Copied' : label}
    </button>
  )
}

function CodeBlock({ children }: { children?: ReactNode }) {
  const child = Array.isArray(children) ? children[0] : children
  const className =
    child && typeof child === 'object' && 'props' in child ? ((child.props as { className?: string }).className ?? '') : ''
  const language = /language-([\w+-]+)/.exec(className)?.[1] ?? 'text'
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-code-bg">
      <div className="flex items-center justify-between border-b border-border px-3 py-1 text-xs text-faint">
        <span className="font-mono">{language}</span>
        <CopyButton text={textOf(children).replace(/\n$/, '')} label="Copy code" />
      </div>
      <pre className="overflow-x-auto p-3.5 font-mono text-[0.85em] leading-relaxed">{children}</pre>
    </div>
  )
}

/**
 * Renders model output. Raw HTML in the Markdown is NOT rendered (react-markdown default), which prevents
 * model- or document-injected HTML/script from executing.
 */
export const Markdown = memo(function Markdown({ content }: { content: string }) {
  return (
    <div className="prose-chat">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeHighlight, { detect: false, ignoreMissing: true }]]}
        components={{
          pre: CodeBlock,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer nofollow">
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
})
