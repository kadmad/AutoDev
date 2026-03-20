/**
 * PlanContent — renders Claude plan markdown with proper formatting.
 * Uses custom components so @tailwindcss/typography is not required.
 */
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'

const components: Components = {
  // ── Headings ──────────────────────────────────────────────────────
  h1: ({ children }) => (
    <h1 className="text-xl font-bold text-gray-900 mt-6 mb-3 pb-2 border-b border-gray-200 first:mt-0">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-base font-bold text-gray-900 mt-5 mb-2 pb-1 border-b border-gray-100 first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-sm font-semibold text-gray-800 mt-4 mb-1.5 first:mt-0">
      {children}
    </h3>
  ),
  h4: ({ children }) => (
    <h4 className="text-sm font-semibold text-gray-700 mt-3 mb-1 first:mt-0">
      {children}
    </h4>
  ),

  // ── Body text ─────────────────────────────────────────────────────
  p: ({ children }) => (
    <p className="text-sm text-gray-700 leading-relaxed mb-3 last:mb-0">{children}</p>
  ),

  // ── Lists ─────────────────────────────────────────────────────────
  ul: ({ children }) => (
    <ul className="list-disc list-outside pl-5 mb-3 space-y-1 text-sm text-gray-700">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal list-outside pl-5 mb-3 space-y-1 text-sm text-gray-700">
      {children}
    </ol>
  ),
  li: ({ children }) => (
    <li className="leading-relaxed">{children}</li>
  ),

  // ── Inline code ───────────────────────────────────────────────────
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  code: ({ inline, children, ...props }: any) => {
    if (inline) {
      return (
        <code
          className="bg-gray-100 text-gray-800 rounded px-1 py-0.5 font-mono text-xs"
          {...props}
        >
          {children}
        </code>
      )
    }
    // Block code — handled by <pre>
    return (
      <code className="font-mono text-xs leading-relaxed" {...props}>
        {children}
      </code>
    )
  },

  // ── Code blocks ───────────────────────────────────────────────────
  pre: ({ children }) => (
    <pre className="bg-gray-900 rounded-lg p-4 overflow-x-auto mb-3 text-gray-100 font-mono text-xs leading-relaxed">
      {children}
    </pre>
  ),

  // ── Blockquote ────────────────────────────────────────────────────
  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-blue-300 bg-blue-50 pl-4 py-1 my-3 rounded-r text-sm text-gray-700 italic">
      {children}
    </blockquote>
  ),

  // ── Horizontal rule ───────────────────────────────────────────────
  hr: () => <hr className="my-4 border-gray-200" />,

  // ── Emphasis ─────────────────────────────────────────────────────
  strong: ({ children }) => (
    <strong className="font-semibold text-gray-900">{children}</strong>
  ),
  em: ({ children }) => (
    <em className="italic text-gray-700">{children}</em>
  ),

  // ── Links ─────────────────────────────────────────────────────────
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-blue-600 hover:underline break-words"
    >
      {children}
    </a>
  ),

  // ── Tables (GFM) ─────────────────────────────────────────────────
  table: ({ children }) => (
    <div className="overflow-x-auto mb-3">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-gray-100">{children}</thead>
  ),
  tbody: ({ children }) => (
    <tbody className="divide-y divide-gray-200">{children}</tbody>
  ),
  tr: ({ children }) => <tr>{children}</tr>,
  th: ({ children }) => (
    <th className="border border-gray-200 px-3 py-2 text-left text-xs font-semibold text-gray-700 bg-gray-50">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-gray-200 px-3 py-2 text-xs text-gray-700 align-top">
      {children}
    </td>
  ),
}

interface Props {
  content: string
}

export default function PlanContent({ content }: Props) {
  return (
    <div className="plan-content">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  )
}
