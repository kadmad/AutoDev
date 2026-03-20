import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { projectApi, githubAuthApi, GitConfig } from '../services/api'
import GuidanceNote from '../components/GuidanceNote'

const FRONTEND_STACKS = ['react', 'next', 'vue', 'angular']
const BACKEND_STACKS = ['fastapi', 'django', 'express', 'rails']

export default function ProjectForm() {
  const navigate = useNavigate()
  const { id } = useParams()
  const isEdit = Boolean(id)

  const [form, setForm] = useState({
    name: '',
    description: '',
    monolithic_dir: '',
    frontend_dir: '',
    backend_dir: '',
    frontend_tech: 'react',
    backend_tech: 'fastapi',
    test_command: 'npx playwright test',
    gitlab_repo_url: '',
    gitlab_project_id: '',
    gitlab_token: '',
    base_branch: 'develop',
    pr_checklist: ['Code reviewed', 'Tests pass', 'Documentation updated'],
    git_provider: '' as '' | 'github' | 'gitlab',
    repo_full_name: '',
    zoho_portal_name: '',
    zoho_project_id: '',
    zoho_project_name: '',
    server_start_command: '',
    server_port: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [newChecklistItem, setNewChecklistItem] = useState('')
  const [githubStatus, setGithubStatus] = useState<GitConfig | null>(null)
  const [githubRepos, setGithubRepos] = useState<{ full_name: string; name: string; private: boolean; default_branch: string }[]>([])
  const [connectingGitHub, setConnectingGitHub] = useState(false)

  // Load GitHub connection status on mount
  useEffect(() => {
    githubAuthApi.getStatus()
      .then((resp) => setGithubStatus(resp.data))
      .catch(() => setGithubStatus(null))
  }, [])

  // Load repos when GitHub is connected and GitHub provider is selected
  useEffect(() => {
    if (form.git_provider === 'github' && githubStatus?.is_connected) {
      githubAuthApi.listRepos()
        .then((resp) => setGithubRepos(resp.data))
        .catch(() => setGithubRepos([]))
    }
  }, [form.git_provider, githubStatus])

  useEffect(() => {
    if (isEdit && id) {
      projectApi.get(id).then((resp) => {
        const p = resp.data
        setForm({
          name: p.name,
          description: p.description || '',
          monolithic_dir: p.monolithic_dir || '',
          frontend_dir: p.frontend_dir || '',
          backend_dir: p.backend_dir || '',
          frontend_tech: p.frontend_tech || 'react',
          backend_tech: p.backend_tech || 'fastapi',
          test_command: p.test_command || 'npx playwright test',
          gitlab_repo_url: p.gitlab_repo_url || '',
          gitlab_project_id: p.gitlab_project_id || '',
          gitlab_token: '',
          base_branch: p.base_branch || 'develop',
          pr_checklist: p.pr_checklist || [],
          git_provider: (p.git_provider as '' | 'github' | 'gitlab') || '',
          repo_full_name: p.repo_full_name || '',
          zoho_portal_name: p.zoho_portal_name || '',
          zoho_project_id: p.zoho_project_id || '',
          zoho_project_name: p.zoho_project_name || '',
          server_start_command: p.server_start_command || '',
          server_port: p.server_port ? String(p.server_port) : '',
        })
      })
    }
  }, [id, isEdit])

  const handleConnectGitHub = async () => {
    setConnectingGitHub(true)
    try {
      const resp = await githubAuthApi.getAuthUrl()
      window.location.href = resp.data.url
    } catch {
      setConnectingGitHub(false)
    }
  }

  const handleSubmit = async () => {
    setLoading(true)
    setError('')
    try {
      const payload = {
        ...form,
        monolithic_dir: form.monolithic_dir || null,
        pr_checklist: form.pr_checklist.filter(Boolean),
        git_provider: form.git_provider || null,
        repo_full_name: form.repo_full_name || null,
        zoho_portal_name: form.zoho_portal_name || null,
        zoho_project_id: form.zoho_project_id || null,
        zoho_project_name: form.zoho_project_name || null,
        server_start_command: form.server_start_command || null,
        server_port: form.server_port ? parseInt(form.server_port, 10) : null,
      }
      if (isEdit && id) {
        await projectApi.update(id, payload)
      } else {
        await projectApi.create(payload)
      }
      navigate('/projects')
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Failed to save project')
    } finally {
      setLoading(false)
    }
  }

  const set = (key: string, value: string) => setForm((prev) => ({ ...prev, [key]: value }))

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-6">{isEdit ? 'Edit Project' : 'New Project'}</h1>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 border border-red-200 text-red-700 p-3 text-sm">{error}</div>
      )}

      <div className="space-y-6">
        {/* Basic Info */}
        <section className="rounded-xl border bg-white p-5 space-y-4">
          <h2 className="font-semibold">Basic Information</h2>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Project Name *</label>
            <input
              className="w-full rounded-lg border px-3 py-2 text-sm"
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              placeholder="My App"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              className="w-full rounded-lg border px-3 py-2 text-sm"
              value={form.description}
              onChange={(e) => set('description', e.target.value)}
              rows={2}
              placeholder="Brief description of the project"
            />
          </div>
        </section>

        {/* Directories */}
        <section className="rounded-xl border bg-white p-5 space-y-4">
          <h2 className="font-semibold">Project Directories</h2>
          <GuidanceNote title="Absolute Paths Required">
            <p>These must be absolute paths on the machine where AutoDev is running.</p>
            <p>Example: <code>/home/user/projects/myapp</code></p>
          </GuidanceNote>

          {/* Monolithic */}
          <div>
            <div className="flex items-center gap-2 mb-1">
              <label className="block text-sm font-medium text-gray-700">Monolithic Directory</label>
              <span className="text-xs bg-purple-50 text-purple-700 border border-purple-200 rounded px-1.5 py-0.5">
                Django / Rails / full-stack in one dir
              </span>
            </div>
            <input
              className="w-full rounded-lg border px-3 py-2 text-sm font-mono"
              value={form.monolithic_dir}
              onChange={(e) => set('monolithic_dir', e.target.value)}
              placeholder="/absolute/path/to/project"
            />
            <p className="mt-1 text-xs text-gray-400">
              Set this when backend + frontend share one directory. A single agent implements all changes here.
              Leave blank and use the fields below for separate frontend/backend directories.
            </p>
          </div>

          {/* Separator */}
          {!form.monolithic_dir && (
            <>
              <div className="flex items-center gap-3">
                <div className="flex-1 border-t border-gray-200" />
                <span className="text-xs text-gray-400">or split directories</span>
                <div className="flex-1 border-t border-gray-200" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Frontend Directory</label>
                <input
                  className="w-full rounded-lg border px-3 py-2 text-sm font-mono"
                  value={form.frontend_dir}
                  onChange={(e) => set('frontend_dir', e.target.value)}
                  placeholder="/absolute/path/to/frontend"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Backend Directory</label>
                <input
                  className="w-full rounded-lg border px-3 py-2 text-sm font-mono"
                  value={form.backend_dir}
                  onChange={(e) => set('backend_dir', e.target.value)}
                  placeholder="/absolute/path/to/backend"
                />
              </div>
            </>
          )}
        </section>

        {/* Tech Stack */}
        <section className="rounded-xl border bg-white p-5 space-y-4">
          <h2 className="font-semibold">Tech Stack</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Frontend</label>
              <select
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={form.frontend_tech}
                onChange={(e) => set('frontend_tech', e.target.value)}
              >
                {FRONTEND_STACKS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Backend</label>
              <select
                className="w-full rounded-lg border px-3 py-2 text-sm"
                value={form.backend_tech}
                onChange={(e) => set('backend_tech', e.target.value)}
              >
                {BACKEND_STACKS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Test Command</label>
            <input
              className="w-full rounded-lg border px-3 py-2 text-sm font-mono"
              value={form.test_command}
              onChange={(e) => set('test_command', e.target.value)}
              placeholder="npx playwright test"
            />
          </div>
        </section>

        {/* Git Provider */}
        <section className="rounded-xl border bg-white p-5 space-y-4">
          <h2 className="font-semibold">Git Provider</h2>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
            <select
              className="w-full rounded-lg border px-3 py-2 text-sm"
              value={form.git_provider}
              onChange={(e) => setForm((p) => ({ ...p, git_provider: e.target.value as '' | 'github' | 'gitlab', repo_full_name: '' }))}
            >
              <option value="">None</option>
              <option value="github">GitHub</option>
              <option value="gitlab">GitLab</option>
            </select>
          </div>

          {/* GitHub fields */}
          {form.git_provider === 'github' && (
            <div className="space-y-3">
              {githubStatus?.is_connected ? (
                <>
                  <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
                    <span className="h-2 w-2 rounded-full bg-green-500 shrink-0" />
                    Connected as <strong>{githubStatus.username}</strong>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Repository</label>
                    {githubRepos.length > 0 ? (
                      <select
                        className="w-full rounded-lg border px-3 py-2 text-sm"
                        value={form.repo_full_name}
                        onChange={(e) => set('repo_full_name', e.target.value)}
                      >
                        <option value="">Select a repository…</option>
                        {githubRepos.map((r) => (
                          <option key={r.full_name} value={r.full_name}>
                            {r.full_name}{r.private ? ' (private)' : ''}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        className="w-full rounded-lg border px-3 py-2 text-sm font-mono"
                        value={form.repo_full_name}
                        onChange={(e) => set('repo_full_name', e.target.value)}
                        placeholder="owner/repo"
                      />
                    )}
                  </div>
                </>
              ) : (
                <div className="space-y-2">
                  <p className="text-sm text-gray-500">Connect your GitHub account to enable automatic PR creation.</p>
                  <button
                    type="button"
                    onClick={handleConnectGitHub}
                    disabled={connectingGitHub}
                    className="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm text-white hover:bg-black disabled:opacity-50"
                  >
                    {connectingGitHub ? 'Redirecting…' : 'Connect GitHub'}
                  </button>
                  <div className="pt-1">
                    <label className="block text-sm font-medium text-gray-700 mb-1">Or enter repo manually</label>
                    <input
                      className="w-full rounded-lg border px-3 py-2 text-sm font-mono"
                      value={form.repo_full_name}
                      onChange={(e) => set('repo_full_name', e.target.value)}
                      placeholder="owner/repo"
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* GitLab fields */}
          {form.git_provider === 'gitlab' && (
            <div className="space-y-3">
              <GuidanceNote title="GitLab Personal Access Token">
                <p>Go to <strong>GitLab → User Settings → Access Tokens</strong></p>
                <p>Required scopes: <code>api</code>, <code>read_repository</code>, <code>write_repository</code></p>
                <p>Project ID: found in <strong>GitLab → Project → Settings → General</strong></p>
              </GuidanceNote>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">GitLab Repo URL</label>
                <input
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  value={form.gitlab_repo_url}
                  onChange={(e) => set('gitlab_repo_url', e.target.value)}
                  placeholder="https://gitlab.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">GitLab Project ID</label>
                <input
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  value={form.gitlab_project_id}
                  onChange={(e) => set('gitlab_project_id', e.target.value)}
                  placeholder="12345"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Personal Access Token {isEdit && <span className="text-gray-400">(leave blank to keep existing)</span>}
                </label>
                <input
                  type="password"
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  value={form.gitlab_token}
                  onChange={(e) => set('gitlab_token', e.target.value)}
                  placeholder={isEdit ? '••••••••' : 'glpat-xxxx'}
                />
              </div>
            </div>
          )}

          {/* Base branch — always shown */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Base Branch</label>
            <input
              className="w-full rounded-lg border px-3 py-2 text-sm font-mono"
              value={form.base_branch}
              onChange={(e) => set('base_branch', e.target.value)}
              placeholder="develop"
            />
          </div>
        </section>

        {/* Zoho Project */}
        <section className="rounded-xl border bg-white p-5 space-y-4">
          <h2 className="font-semibold">Zoho Project</h2>
          <p className="text-xs text-gray-500">
            Override the global Zoho settings for this project. Leave blank to use the account-level defaults from Settings.
          </p>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Portal Name</label>
            <input
              className="w-full rounded-lg border px-3 py-2 text-sm font-mono"
              value={form.zoho_portal_name}
              onChange={(e) => set('zoho_portal_name', e.target.value)}
              placeholder="mycompany"
            />
            <p className="mt-1 text-xs text-gray-400">
              From <code>projectsapi.zoho.com/restapi/portal/<strong>mycompany</strong>/</code>
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Project ID</label>
            <input
              className="w-full rounded-lg border px-3 py-2 text-sm font-mono"
              value={form.zoho_project_id}
              onChange={(e) => set('zoho_project_id', e.target.value)}
              placeholder="4847260000000000001"
            />
            <p className="mt-1 text-xs text-gray-400">
              Numeric ID from the Zoho Projects URL or API response.
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Zoho Project Name
              <span className="ml-1.5 text-xs font-normal text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded">used for routing</span>
            </label>
            <input
              className="w-full rounded-lg border px-3 py-2 text-sm"
              value={form.zoho_project_name}
              onChange={(e) => set('zoho_project_name', e.target.value)}
              placeholder="My Zoho Project"
            />
            <p className="mt-1 text-xs text-gray-400">
              The name of the Zoho project exactly as it appears in Zoho. When a task webhook arrives,
              AutoDev matches it to this project by Zoho Project ID first, then by this name.
            </p>
          </div>
        </section>

        {/* Playwright Testing */}
        <section className="rounded-xl border bg-white p-5 space-y-4">
          <h2 className="font-semibold">Playwright Testing</h2>
          <p className="text-xs text-gray-500">
            AutoDev will auto-generate Playwright end-to-end tests in a separate temp directory and run them against your server.
            Leave blank to skip test generation.
          </p>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Server Start Command</label>
            <input
              className="w-full rounded-lg border px-3 py-2 text-sm font-mono"
              value={form.server_start_command}
              onChange={(e) => set('server_start_command', e.target.value)}
              placeholder="uvicorn main:app --port 8001"
            />
            <p className="mt-1 text-xs text-gray-400">
              Command to start your app's server before running tests. Must bind to the port below.
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Server Port</label>
            <input
              className="w-full rounded-lg border px-3 py-2 text-sm font-mono"
              type="number"
              value={form.server_port}
              onChange={(e) => set('server_port', e.target.value)}
              placeholder="8001"
            />
            <p className="mt-1 text-xs text-gray-400">
              Port your server listens on. Playwright will wait for it before running tests.
            </p>
          </div>
        </section>

        {/* PR Checklist */}
        <section className="rounded-xl border bg-white p-5 space-y-4">
          <h2 className="font-semibold">PR Checklist Items</h2>
          <div className="space-y-2">
            {form.pr_checklist.map((item, i) => (
              <div key={i} className="flex gap-2">
                <input
                  className="flex-1 rounded-lg border px-3 py-1.5 text-sm"
                  value={item}
                  onChange={(e) => {
                    const list = [...form.pr_checklist]
                    list[i] = e.target.value
                    setForm((p) => ({ ...p, pr_checklist: list }))
                  }}
                />
                <button
                  onClick={() => setForm((p) => ({ ...p, pr_checklist: p.pr_checklist.filter((_, j) => j !== i) }))}
                  className="text-red-400 hover:text-red-600 px-2"
                >
                  ✕
                </button>
              </div>
            ))}
            <div className="flex gap-2">
              <input
                className="flex-1 rounded-lg border px-3 py-1.5 text-sm"
                value={newChecklistItem}
                onChange={(e) => setNewChecklistItem(e.target.value)}
                placeholder="Add checklist item..."
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && newChecklistItem.trim()) {
                    setForm((p) => ({ ...p, pr_checklist: [...p.pr_checklist, newChecklistItem.trim()] }))
                    setNewChecklistItem('')
                  }
                }}
              />
              <button
                onClick={() => {
                  if (newChecklistItem.trim()) {
                    setForm((p) => ({ ...p, pr_checklist: [...p.pr_checklist, newChecklistItem.trim()] }))
                    setNewChecklistItem('')
                  }
                }}
                className="rounded-lg bg-gray-100 px-3 py-1.5 text-sm hover:bg-gray-200"
              >
                Add
              </button>
            </div>
          </div>
        </section>

        <div className="flex gap-3">
          <button
            onClick={() => navigate('/projects')}
            className="flex-1 rounded-lg border px-4 py-2 text-sm hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!form.name || loading}
            className="flex-1 rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? 'Saving...' : isEdit ? 'Save Changes' : 'Create Project'}
          </button>
        </div>
      </div>
    </div>
  )
}
