import { Children, isValidElement, memo, useState, type ReactNode } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

function CodeBlock({ children }: { children?: ReactNode }) {
  const child = Children.toArray(children)[0]
  const code = isValidElement<{ children?: ReactNode; className?: string }>(child) ? child : null
  const text = String(code?.props.children ?? '')
  const language = /language-([^\s]+)/.exec(code?.props.className ?? '')?.[1] ?? 'code'
  const [copyState, setCopyState] = useState<'ready' | 'copied' | 'failed'>('ready')

  async function copy() {
    try { await navigator.clipboard.writeText(text); setCopyState('copied') }
    catch { setCopyState('failed') }
  }

  return <div className="code-block">
    <div className="code-toolbar"><span>{language}</span><button type="button" onClick={() => void copy()} aria-label="Copy code">{copyState === 'copied' ? 'Copied!' : copyState === 'failed' ? 'Select text to copy' : 'Copy code'}</button><span className="sr-only" role="status">{copyState === 'copied' ? 'Code copied to clipboard.' : copyState === 'failed' ? 'Clipboard unavailable. Select the code and copy it manually.' : ''}</span></div>
    <pre tabIndex={0}>{children}</pre>
  </div>
}

const components: Components = {
  h1: 'h3',
  h2: 'h4',
  h3: 'h5',
  pre: CodeBlock,
  a: ({ href, children }) => href
    ? <a href={href} target={href.startsWith('#') ? undefined : '_blank'} rel="noopener noreferrer">{children}</a>
    : <span>{children}</span>,
  // A model-provided image must not make a remote request merely by being displayed.
  img: ({ src, alt }) => typeof src === 'string' && src
    ? <a href={src} target="_blank" rel="noopener noreferrer">Image: {alt || 'open image'}</a>
    : <span>{alt || 'Image'}</span>,
  table: ({ children }) => <div className="markdown-table" role="region" aria-label="Scrollable table" tabIndex={0}><table>{children}</table></div>,
}
const plugins = [remarkGfm]

export const Markdown = memo(function Markdown({ text }: { text: string }) {
  return <div className="markdown"><ReactMarkdown remarkPlugins={plugins} components={components} skipHtml>{text}</ReactMarkdown></div>
})
