import { Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, FolderKanban, LogOut, AlertTriangle, RefreshCw, Settings } from 'lucide-react'
import { useEffect, useState } from 'react'
import { zohoAuthApi, githubAuthApi, pipelineApi, ZohoStatus, GitConfig } from '../services/api'
import { useAuth } from '../context/AuthContext'

const ATTENTION_STAGES = ['plan_review', 'test_review', 'mr_open']

interface Props {
  children: React.ReactNode
}

export default function Layout({ children }: Props) {
  const location = useLocation()
  const { clearToken } = useAuth()
  const [zohoStatus, setZohoStatus] = useState<ZohoStatus | null>(null)
  const [githubStatus, setGithubStatus] = useState<GitConfig | null>(null)
  const [reconnecting, setReconnecting] = useState(false)
  const [attentionCount, setAttentionCount] = useState(0)

  const zohoNeedsConfig = zohoStatus && (
    zohoStatus.portal_name === 'pending' || zohoStatus.project_id === 'pending' || !zohoStatus.is_connected
  )

  const nav = [
    { href: '/', label: 'Dashboard', icon: LayoutDashboard },
    { href: '/projects', label: 'Projects', icon: FolderKanban },
    { href: '/settings', label: 'Integrations', icon: Settings, warn: zohoNeedsConfig },
  ]

  // Poll Zoho connection status every 60 s
  useEffect(() => {
    const check = async () => {
      try {
        const resp = await zohoAuthApi.getStatus()
        setZohoStatus(resp.data)
      } catch {
        // 404 = not configured yet — ignore
      }
    }
    check()
    const id = setInterval(check, 60_000)
    return () => clearInterval(id)
  }, [])

  // Poll GitHub connection status every 60 s
  useEffect(() => {
    const check = async () => {
      try {
        const resp = await githubAuthApi.getStatus()
        setGithubStatus(resp.data)
      } catch {
        // 404 = not connected yet — ignore
      }
    }
    check()
    const id = setInterval(check, 60_000)
    return () => clearInterval(id)
  }, [])

  // Poll attention count every 10 s
  useEffect(() => {
    const poll = async () => {
      try {
        const resp = await pipelineApi.list()
        const count = resp.data.filter((r) => ATTENTION_STAGES.includes(r.status)).length
        setAttentionCount(count)
      } catch {
        // ignore
      }
    }
    poll()
    const id = setInterval(poll, 10_000)
    return () => clearInterval(id)
  }, [])

  const handleReconnect = async () => {
    setReconnecting(true)
    try {
      const resp = await zohoAuthApi.getAuthUrl()
      window.location.href = resp.data.url
    } catch {
      setReconnecting(false)
    }
  }

  const showBanner = zohoStatus && (zohoStatus.token_expired || !zohoStatus.is_connected)

  return (
    <div className="flex min-h-screen flex-col">
      {/* Token expired banner */}
      {showBanner && (
        <div className="flex items-center justify-between gap-3 bg-amber-500 px-4 py-2 text-sm text-white">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>
              <strong>Zoho connection expired.</strong> Task status updates are paused until you reconnect.
            </span>
          </div>
          <button
            onClick={handleReconnect}
            disabled={reconnecting}
            className="flex shrink-0 items-center gap-1 rounded-md bg-white/20 px-3 py-1 text-xs font-medium hover:bg-white/30 disabled:opacity-60"
          >
            <RefreshCw className={`h-3 w-3 ${reconnecting ? 'animate-spin' : ''}`} />
            {reconnecting ? 'Redirecting…' : 'Reconnect to Zoho'}
          </button>
        </div>
      )}

      <div className="flex flex-1">
        <aside className="w-56 bg-gray-900 text-white flex flex-col">
          <div className="p-4 border-b border-gray-700">
            <h1 className="text-lg font-bold text-blue-400">AutoDev</h1>
            <p className="text-xs text-gray-400">Lifecycle Automation</p>
            {/* Zoho connection dot */}
            {zohoStatus && (
              <div className="mt-2 flex items-center gap-1.5">
                <span className={`h-2 w-2 rounded-full ${zohoStatus.is_connected ? 'bg-green-400' : 'bg-amber-400'}`} />
                <span className="text-xs text-gray-400">
                  Zoho {zohoStatus.is_connected ? 'connected' : 'not connected'}
                </span>
              </div>
            )}
            {/* GitHub connection dot */}
            {githubStatus && (
              <div className="mt-1 flex items-center gap-1.5">
                <span className={`h-2 w-2 rounded-full ${githubStatus.is_connected ? 'bg-green-400' : 'bg-amber-400'}`} />
                <span className="text-xs text-gray-400">
                  GitHub {githubStatus.is_connected ? `(${githubStatus.username})` : 'not connected'}
                </span>
              </div>
            )}
          </div>
          <nav className="flex-1 p-3 space-y-1">
            {nav.map(({ href, label, icon: Icon, warn }) => (
              <Link
                key={href}
                to={href}
                className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors ${
                  location.pathname === href
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-300 hover:bg-gray-700'
                }`}
              >
                <Icon className="h-4 w-4" />
                <span className="flex-1">{label}</span>
                {href === '/' && attentionCount > 0 && (
                  <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-orange-500 px-1 text-xs font-bold text-white">
                    {attentionCount}
                  </span>
                )}
                {warn && href !== '/' && (
                  <span className="h-2 w-2 rounded-full bg-amber-400 shrink-0" />
                )}
              </Link>
            ))}
          </nav>
          <button
            onClick={clearToken}
            className="flex items-center gap-2 p-4 text-sm text-gray-400 hover:text-white border-t border-gray-700"
          >
            <LogOut className="h-4 w-4" />
            Logout
          </button>
        </aside>
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  )
}
