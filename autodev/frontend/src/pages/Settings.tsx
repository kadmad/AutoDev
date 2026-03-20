import { useState, useEffect } from 'react'
import { userApi, zohoAuthApi, githubAuthApi, ZohoStatus, GitConfig } from '../services/api'
import { RefreshCw, ExternalLink } from 'lucide-react'

export default function Settings() {
  const [zoho, setZoho] = useState<ZohoStatus | null>(null)
  const [githubStatus, setGithubStatus] = useState<GitConfig | null>(null)
  const [reconnecting, setReconnecting] = useState(false)
  const [connectingGitHub, setConnectingGitHub] = useState(false)

  useEffect(() => {
    userApi.zohoConfig()
      .then((r) => setZoho(r.data as ZohoStatus))
      .catch(() => {})

    githubAuthApi.getStatus()
      .then((r) => setGithubStatus(r.data))
      .catch(() => setGithubStatus(null))
  }, [])

  const handleReconnectZoho = async () => {
    setReconnecting(true)
    try {
      const resp = await zohoAuthApi.getAuthUrl()
      window.location.href = resp.data.url
    } catch {
      setReconnecting(false)
    }
  }

  const handleConnectGitHub = async () => {
    setConnectingGitHub(true)
    try {
      const resp = await githubAuthApi.getAuthUrl()
      window.location.href = resp.data.url
    } catch {
      setConnectingGitHub(false)
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-bold">Integrations</h1>

      {/* ── Zoho ── */}
      <section className="rounded-xl border bg-white p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Zoho Projects</h2>
          {zoho && (
            <span className={`flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full ${
              zoho.is_connected ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-700'
            }`}>
              <span className={`h-1.5 w-1.5 rounded-full ${zoho.is_connected ? 'bg-green-500' : 'bg-amber-500'}`} />
              {zoho.is_connected ? `Connected as ${zoho.zoho_email || 'Zoho user'}` : 'Not connected'}
            </span>
          )}
        </div>

        <p className="text-sm text-gray-500">
          Portal name and Project ID are configured per project.{' '}
          Go to <strong>Projects → Edit Project → Zoho Project</strong> to set them.
        </p>

        <div>
          <button
            onClick={handleReconnectZoho}
            disabled={reconnecting}
            className="flex items-center gap-2 rounded-lg border px-4 py-2 text-sm hover:bg-gray-50 disabled:opacity-50"
          >
            {reconnecting ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ExternalLink className="h-4 w-4" />}
            {zoho?.is_connected ? 'Reconnect OAuth' : 'Connect Zoho OAuth'}
          </button>
        </div>

        {/* Webhook reference */}
        <div className="rounded-lg bg-gray-50 border p-3 text-xs text-gray-600 space-y-1">
          <p className="font-medium">Zoho Webhook URL</p>
          <code className="block bg-white border rounded px-2 py-1 break-all select-all">
            {'http://localhost:8000/task-assign?task_owner=${Task.CREATEDBY.EMAIL}&description=${Task.DESCRIPTION}&task_id=${Task.ID_LONG}&platform=zoho'}
          </code>
          <p className="text-red-700 font-semibold">⚠ Must use <code>Task.ID_LONG</code> (numeric, e.g. 4847260000000123456) — NOT <code>Task.TASKID</code> (e.g. TA1-T1). Using the short ID will cause Zoho status updates to fail.</p>
        </div>
      </section>

      {/* ── GitHub ── */}
      <section className="rounded-xl border bg-white p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">GitHub</h2>
          {githubStatus && (
            <span className={`flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full ${
              githubStatus.is_connected ? 'bg-green-50 text-green-700' : 'bg-gray-50 text-gray-600'
            }`}>
              <span className={`h-1.5 w-1.5 rounded-full ${githubStatus.is_connected ? 'bg-green-500' : 'bg-gray-400'}`} />
              {githubStatus.is_connected ? `Connected as ${githubStatus.username}` : 'Not connected'}
            </span>
          )}
        </div>
        <p className="text-sm text-gray-500">
          Connect GitHub to enable automatic branch creation and pull request opening.
        </p>
        <button
          onClick={handleConnectGitHub}
          disabled={connectingGitHub}
          className="flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm text-white hover:bg-black disabled:opacity-50"
        >
          {connectingGitHub ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ExternalLink className="h-4 w-4" />}
          {githubStatus?.is_connected ? 'Reconnect GitHub' : 'Connect GitHub'}
        </button>
      </section>
    </div>
  )
}
