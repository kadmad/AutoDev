import axios from 'axios'

const BACKEND = import.meta.env.VITE_BACKEND_URL || ''
const BASE = BACKEND ? `${BACKEND}/api/v1` : '/api/v1'

/** Build a WebSocket URL, using the configured backend if set. */
export function makeWsUrl(path: string, token?: string): string {
  let base: string
  if (BACKEND) {
    base = BACKEND.replace(/^http/, 'ws')
  } else {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    base = `${proto}://${window.location.host}`
  }
  return token ? `${base}${path}?token=${encodeURIComponent(token)}` : `${base}${path}`
}

// ---------- Axios instance ----------

const api = axios.create({ baseURL: BASE })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('autodev_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('autodev_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// ---------- Types ----------

export interface User {
  id: string
  name: string
  email: string
  created_at: string
}

export interface Project {
  id: string
  user_id: string
  name: string
  description?: string
  monolithic_dir?: string | null
  frontend_dir?: string
  backend_dir?: string
  frontend_tech?: string
  backend_tech?: string
  test_command?: string
  gitlab_repo_url?: string
  gitlab_project_id?: string
  base_branch: string
  pr_checklist?: string[]
  git_provider?: string | null
  repo_full_name?: string | null
  zoho_portal_name?: string | null
  zoho_project_id?: string | null
  zoho_project_name?: string | null
  server_start_command?: string | null
  server_port?: number | null
  created_at: string
  updated_at: string
}

export interface GitConfig {
  id: string
  provider: string
  username: string | null
  email: string | null
  avatar_url: string | null
  token_expired: boolean
  is_connected: boolean
}

export interface PipelineRun {
  id: string
  project_id: string
  zoho_task_id?: string
  zoho_task_number?: string
  zoho_task_title?: string
  zoho_task_description?: string
  status: string
  current_stage?: string
  feature_branch?: string
  error_message?: string
  archived?: boolean
  created_at: string
  updated_at: string
  plans?: Plan[]
  agent_runs?: AgentRun[]
  test_results?: TestResult[]
  merge_requests?: MergeRequest[]
}

export interface Plan {
  id: string
  pipeline_run_id: string
  content: string
  version: number
  approved_by?: string
  approved_at?: string
  user_edits?: string
  created_at: string
}

export interface TestScenario {
  id: string
  name: string
  steps?: string
  expected?: string
  status: 'pending' | 'passed' | 'failed'
  type?: 'playwright' | 'manual'
}

export interface TestResult {
  id: string
  total: number
  passed: number
  failed: number
  skipped: number
  raw_output?: string
  scenarios?: string  // JSON-encoded TestScenario[]
  browser_test_output?: string
  browser_test_status?: 'passed' | 'failed' | 'error' | 'skipped'
  approved_by?: string
  approved_at?: string
  created_at: string
}

export interface MergeRequest {
  id: string
  gitlab_mr_id?: string
  mr_url?: string
  title?: string
  source_branch?: string
  target_branch?: string
  status: string
  created_at: string
}

export interface AgentRun {
  id: string
  agent_type: string
  status: string
  started_at?: string
  completed_at?: string
  exit_code?: number
  error?: string
}

// ---------- API calls ----------

export interface ZohoStatus {
  id: string
  user_id: string
  zoho_email: string | null
  portal_name: string
  project_id: string
  token_expired: boolean
  is_connected: boolean
  poll_interval_seconds: number
  created_at: string
}

export const authApi = {
  setup: (data: object) => api.post('/setup', data),
  login: (email: string, password: string) => api.post('/login', { email, password }),
  setupStatus: () => api.get('/setup/status'),
}

export const zohoAuthApi = {
  getAuthUrl: () => api.get<{ url: string }>('/zoho/auth/url'),
  exchangeCode: (code: string) => api.post<{ status: string; zoho: ZohoStatus }>('/zoho/auth/callback', { code }),
  getStatus: () => api.get<ZohoStatus>('/zoho/auth/status'),
  listPortals: () => api.get<{ id: string; name: string; display: string }[]>('/zoho/portals'),
  listProjects: (portal: string) => api.get<{ id: string; name: string }[]>(`/zoho/portals/${portal}/projects`),
}

export const githubAuthApi = {
  getAuthUrl: () => api.get<{ url: string }>('/github/auth/url'),
  exchangeCode: (code: string) => api.post<{ status: string; git: GitConfig }>('/github/auth/callback', { code }),
  getStatus: () => api.get<GitConfig>('/github/auth/status'),
  listRepos: () => api.get<{ full_name: string; name: string; private: boolean; default_branch: string }[]>('/github/repos'),
}

export const userApi = {
  me: () => api.get<User>('/users/me'),
  updateMe: (data: object) => api.put<User>('/users/me', data),
  zohoConfig: () => api.get('/users/me/zoho'),
  updateZoho: (data: object) => api.put('/users/me/zoho', data),
}

export const projectApi = {
  list: () => api.get<Project[]>('/projects'),
  get: (id: string) => api.get<Project>(`/projects/${id}`),
  create: (data: object) => api.post<Project>('/projects', data),
  update: (id: string, data: object) => api.put<Project>(`/projects/${id}`, data),
  delete: (id: string) => api.delete(`/projects/${id}`),
  techStacks: () => api.get('/projects/tech-stacks'),
}

export const pipelineApi = {
  list: (archived = false) => api.get<PipelineRun[]>('/pipelines', { params: { archived } }),
  get: (runId: string) => api.get<PipelineRun>(`/pipelines/${runId}`),
  trigger: (data: object) => api.post<PipelineRun>('/pipelines/trigger', data),
  cancel: (runId: string) => api.post(`/pipelines/${runId}/cancel`),
  resume: (runId: string) => api.post(`/pipelines/${runId}/resume`),
  logs: (runId: string) => api.get(`/pipelines/${runId}/logs`),

  getPlan: (runId: string) => api.get<Plan>(`/pipelines/${runId}/plan`),
  approvePlan: (runId: string, data?: object) => api.post(`/pipelines/${runId}/plan/approve`, data || {}),
  replan: (runId: string, feedback: string) => api.post(`/pipelines/${runId}/plan/replan`, { feedback }),

  getTests: (runId: string) => api.get<TestResult>(`/pipelines/${runId}/tests`),
  updateScenarios: (runId: string, scenarios: TestScenario[]) =>
    api.put(`/pipelines/${runId}/tests/scenarios`, { scenarios }),
  approveTests: (runId: string, scenarios: TestScenario[]) =>
    api.post(`/pipelines/${runId}/tests/approve`, { scenarios }),
  skipTests: (runId: string) => api.post(`/pipelines/${runId}/tests/skip`),
  reworkTests: (runId: string, feedback: string) => api.post(`/pipelines/${runId}/tests/rework`, { feedback }),
  retryPlaywright: (runId: string, scenarioIds: string[]) =>
    api.post<{ scenarios: string; browser_test_status: string }>(
      `/pipelines/${runId}/tests/retry-playwright`,
      { scenario_ids: scenarioIds },
      { timeout: 660_000 },  // 11 min — server start (5s) + 10 min test timeout
    ),

  getMR: (runId: string) => api.get<MergeRequest>(`/pipelines/${runId}/mr`),
  confirmMerge: (runId: string) => api.post(`/pipelines/${runId}/mr/confirm-merge`),
  deletePipeline: (runId: string) => api.delete(`/pipelines/${runId}`),
  bulkDelete: (opts: { run_ids?: string[]; statuses?: string[] }) =>
    api.post<{ deleted: number }>('/pipelines/bulk-delete', opts),
  archivePipeline: (runId: string) => api.post(`/pipelines/${runId}/archive`),
  unarchivePipeline: (runId: string) => api.post(`/pipelines/${runId}/unarchive`),
  bulkArchive: (run_ids?: string[]) =>
    api.post<{ archived: number }>('/pipelines/bulk-archive', { run_ids }),
  bulkUnarchive: () => api.post<{ unarchived: number }>('/pipelines/bulk-unarchive'),
  getDiff: (runId: string) => api.get<{ files: DiffFile[]; summary: string }>(`/pipelines/${runId}/diff`),
}

export interface DiffFile {
  path: string
  additions: number
  deletions: number
}

export default api
