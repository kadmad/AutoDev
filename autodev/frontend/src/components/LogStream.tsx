import { useEffect, useRef, useState } from 'react'
import { makeWsUrl } from '../services/api'
import { fmtTime } from '../utils/time'

interface LogLine {
  type: 'log' | 'stage' | 'error'
  line?: string
  stage?: string
  agent?: string
  ts?: string
  message?: string
}

interface Props {
  runId: string
  isActive: boolean
}

const AGENT_COLORS: Record<string, string> = {
  planner: 'text-cyan-400',
  backend_developer: 'text-green-400',
  frontend_developer: 'text-lime-400',
  test_runner: 'text-yellow-400',
  pr_creator: 'text-pink-400',
  zoho_updater: 'text-purple-400',
  system: 'text-gray-400',
}

export default function LogStream({ runId, isActive }: Props) {
  const [lines, setLines] = useState<LogLine[]>([])
  const [wsStatus, setWsStatus] = useState<'connecting' | 'open' | 'closed' | 'error'>('connecting')
  const bottomRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const userScrolledUp = useRef(false)
  const retryTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryCount = useRef(0)
  const unmounted = useRef(false)

  useEffect(() => {
    unmounted.current = false
    retryCount.current = 0
    setLines([])
    setWsStatus('connecting')

    function connect() {
      if (unmounted.current) return
      const ws = new WebSocket(makeWsUrl(`/ws/pipeline/${runId}`))

      ws.onopen = () => {
        retryCount.current = 0
        setWsStatus('open')
      }

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data) as LogLine
          setLines((prev) => [...prev.slice(-2000), data])
        } catch {
          setLines((prev) => [...prev.slice(-2000), { type: 'log', line: e.data }])
        }
      }

      ws.onerror = () => setWsStatus('error')

      ws.onclose = () => {
        if (unmounted.current) return
        setWsStatus('closed')
        // Auto-reconnect with backoff (max 30s)
        const delay = Math.min(1000 * 2 ** retryCount.current, 30000)
        retryCount.current += 1
        retryTimeout.current = setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      unmounted.current = true
      if (retryTimeout.current) clearTimeout(retryTimeout.current)
    }
  }, [runId])

  // Track whether user has scrolled up manually
  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    userScrolledUp.current = distanceFromBottom > 60
  }

  // Only auto-scroll when user is already at (or near) the bottom
  useEffect(() => {
    if (!userScrolledUp.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [lines])

  return (
    <div>
      {/* Status bar */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-gray-500">Live Logs</span>
        <span className="flex items-center gap-1.5 text-xs">
          <span className={`h-1.5 w-1.5 rounded-full ${
            wsStatus === 'open' && isActive ? 'bg-green-400 animate-pulse' :
            wsStatus === 'open' ? 'bg-gray-400' :
            wsStatus === 'connecting' ? 'bg-yellow-400 animate-pulse' :
            wsStatus === 'error' ? 'bg-red-400' : 'bg-gray-500'
          }`} />
          <span className="text-gray-400">
            {wsStatus === 'open' && isActive ? 'Streaming live' :
             wsStatus === 'open' ? 'Loaded' :
             wsStatus === 'connecting' ? 'Connecting...' :
             wsStatus === 'error' ? 'Connection error' : 'Disconnected'}
          </span>
        </span>
      </div>

      {/* Log panel */}
      <div ref={scrollRef} onScroll={handleScroll} className="h-96 overflow-y-auto rounded-lg bg-gray-950 p-4 font-mono text-xs leading-5 border border-gray-800">
        {lines.length === 0 ? (
          <p className="text-gray-600 italic">
            {wsStatus === 'connecting' ? 'Connecting...' : 'Waiting for logs...'}
          </p>
        ) : (
          lines.map((l, i) => (
            <div key={i} className="whitespace-pre-wrap break-words">
              {l.type === 'stage' ? (
                <div className="my-1.5 border-t border-gray-800 pt-1.5">
                  <span className="text-yellow-400 font-semibold">
                    ══ {l.stage?.replace(/_/g, ' ').toUpperCase()} ══
                  </span>
                  {l.ts && (
                    <span className="ml-2 text-gray-600 text-[10px]">
                      {fmtTime(l.ts)}
                    </span>
                  )}
                </div>
              ) : l.type === 'error' ? (
                <span className="text-red-400">[error] {l.message}</span>
              ) : (
                <span>
                  {l.agent && l.agent !== 'system' && (
                    <span className={`${AGENT_COLORS[l.agent] ?? 'text-blue-400'} mr-1 font-semibold`}>
                      [{l.agent}]
                    </span>
                  )}
                  <span className="text-gray-200">{l.line}</span>
                </span>
              )}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
