import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  Plus, RefreshCw, ClipboardCheck, GitMerge, FlaskConical,
  Bell, Square, RotateCcw, ExternalLink, X, ChevronLeft, ChevronRight, Search, Trash2, Archive, ArchiveRestore,
} from 'lucide-react'
import { pipelineApi, projectApi, PipelineRun, Project, makeWsUrl } from '../services/api'
import { fmtDateTime } from '../utils/time'
import StatusBadge from '../components/StatusBadge'

// Gate stages that need human attention
const ATTENTION_STAGES = ['plan_review', 'testing', 'mr_open'] as const
// Active processing stages
const ACTIVE_STAGES = ['task_received', 'planning', 'developing', 'creating_mr']

const ATTENTION_META: Record<string, {
  label: string; action: string; icon: React.ElementType
  color: string; border: string; bg: string; iconCls: string; btnCls: string
}> = {
  plan_review: {
    label: 'Plan ready for review',
    action: 'Review Plan',
    icon: ClipboardCheck,
    color: 'orange',
    border: 'border-orange-200',
    bg: 'bg-orange-50',
    iconCls: 'text-orange-500',
    btnCls: 'bg-orange-600 hover:bg-orange-700',
  },
  testing: {
    label: 'Manual testing required',
    action: 'Run Tests',
    icon: FlaskConical,
    color: 'purple',
    border: 'border-purple-200',
    bg: 'bg-purple-50',
    iconCls: 'text-purple-500',
    btnCls: 'bg-purple-600 hover:bg-purple-700',
  },
  mr_open: {
    label: 'MR open — review and merge',
    action: 'View MR',
    icon: GitMerge,
    color: 'indigo',
    border: 'border-indigo-200',
    bg: 'bg-indigo-50',
    iconCls: 'text-indigo-500',
    btnCls: 'bg-indigo-600 hover:bg-indigo-700',
  },
}

// Human-readable label for filter chip in table header
const FILTER_LABEL: Record<string, string> = {
  __active__: 'Active',
  completed: 'Completed',
  failed: 'Failed',
  plan_review: 'Plan Review',
  testing: 'Testing',
  mr_open: 'MR Open',
}

export default function Dashboard() {
  const [runs, setRuns] = useState<PipelineRun[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [showTrigger, setShowTrigger] = useState(false)
  const TRIGGER_EMPTY = { project_id: '', zoho_task_id: '', zoho_task_number: '', zoho_task_title: '' }
  const [triggerData, setTriggerData] = useState(TRIGGER_EMPTY)
  const [triggering, setTriggering] = useState(false)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [cleaningUp, setCleaningUp] = useState(false)
  const [archiveMode, setArchiveMode] = useState(false)
  const [bulkArchiving, setBulkArchiving] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [selectionBusy, setSelectionBusy] = useState(false)
  const [confirmModal, setConfirmModal] = useState<{
    title: string
    message: string
    variant: 'danger' | 'warning'
    confirmLabel: string
    onConfirm: () => Promise<void>
  } | null>(null)
  const [filterKey, setFilterKey] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(25)
  const wsRef = useRef<WebSocket | null>(null)
  const carouselRef = useRef<HTMLDivElement | null>(null)

  const fetchData = async (archived = archiveMode) => {
    setLoading(true)
    try {
      const [runsResp, projResp] = await Promise.all([
        pipelineApi.list(archived),
        projectApi.list(),
      ])
      setRuns(runsResp.data)
      setProjects(projResp.data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData(archiveMode)

    const token = localStorage.getItem('autodev_token')
    if (!token) return

    const wsUrl = makeWsUrl('/ws/pipelines', token)
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'pipeline_update') {
          setRuns((prev) => {
            const exists = prev.some((r) => r.id === msg.run_id)
            if (exists) {
              return prev.map((r) =>
                r.id === msg.run_id
                  ? { ...r, status: msg.status, current_stage: msg.stage }
                  : r
              )
            }
            fetchData()
            return prev
          })
        }
      } catch { /* ignore */ }
    }

    // Fall back to polling if WS fails or drops
    const startPolling = () => {
      const interval = setInterval(fetchData, 10000)
      return interval
    }
    let pollInterval: ReturnType<typeof setInterval> | null = null
    ws.onerror = () => { pollInterval = startPolling() }
    ws.onclose = () => { if (!pollInterval) pollInterval = startPolling() }

    return () => { ws.close(); if (pollInterval) clearInterval(pollInterval) }
  }, [])

  // Re-fetch when archive mode changes
  useEffect(() => { fetchData(archiveMode) }, [archiveMode])

  // Reset page + clear selection when filter, search, or page size changes
  useEffect(() => { setPage(0); setSelectedIds(new Set()) }, [filterKey, searchQuery, pageSize, archiveMode])

  // ── Derived data ──────────────────────────────────────────────────
  const needsAttention = runs.filter((r) =>
    (ATTENTION_STAGES as readonly string[]).includes(r.status)
  )

  const TERMINAL = ['completed', 'failed']
  const GATES = ['plan_review', 'testing', 'mr_open']
  const stats = {
    total: runs.length,
    active: runs.filter((r) => !TERMINAL.includes(r.status) && !GATES.includes(r.status)).length,
    completed: runs.filter((r) => r.status === 'completed').length,
    failed: runs.filter((r) => r.status === 'failed').length,
  }

  const statusFiltered =
    filterKey === null ? runs
    : filterKey === '__active__' ? runs.filter((r) => !['completed', 'failed'].includes(r.status))
    : runs.filter((r) => r.status === filterKey)

  const q = searchQuery.toLowerCase().trim()
  const filteredRuns = q
    ? statusFiltered.filter((r) => {
        const title = (r.zoho_task_title || r.zoho_task_id || '').toLowerCase()
        const taskNum = (r.zoho_task_number || '').toLowerCase()
        const projectName = (projects.find((p) => p.id === r.project_id)?.name || '').toLowerCase()
        return title.includes(q) || taskNum.includes(q) || projectName.includes(q)
      })
    : statusFiltered

  const totalPages = Math.ceil(filteredRuns.length / pageSize)
  const pagedRuns = filteredRuns.slice(page * pageSize, (page + 1) * pageSize)

  // ── Actions ───────────────────────────────────────────────────────
  const handleTrigger = async () => {
    setTriggering(true)
    try {
      await pipelineApi.trigger(triggerData)
      setShowTrigger(false)
      setTriggerData(TRIGGER_EMPTY)
      await fetchData()
    } catch (e) { console.error(e) }
    finally { setTriggering(false) }
  }

  const handleStop = async (runId: string) => {
    setActionLoading(runId + ':stop')
    try {
      await pipelineApi.cancel(runId)
      setRuns((prev) =>
        prev.map((r) => r.id === runId ? { ...r, status: 'failed', current_stage: 'failed' } : r)
      )
    } catch (e) { console.error(e) }
    finally { setActionLoading(null) }
  }

  const handleRestart = async (runId: string) => {
    setActionLoading(runId + ':restart')
    try {
      await pipelineApi.resume(runId)
      setRuns((prev) =>
        prev.map((r) => r.id === runId ? { ...r, status: 'task_received', current_stage: 'task_received', error_message: undefined } : r)
      )
    } catch (e) { console.error(e) }
    finally { setActionLoading(null) }
  }

  const handleDelete = (runId: string) => {
    setConfirmModal({
      title: 'Delete Pipeline',
      message: 'This pipeline run will be permanently deleted from the database. This cannot be undone.',
      variant: 'danger',
      confirmLabel: 'Delete',
      onConfirm: async () => {
        setActionLoading(runId + ':delete')
        try {
          await pipelineApi.deletePipeline(runId)
          setRuns((prev) => prev.filter((r) => r.id !== runId))
        } finally {
          setActionLoading(null)
        }
      },
    })
  }

  const handleCleanUp = () => {
    const cleanable = runs.filter((r) => r.status === 'completed' || r.status === 'failed')
    if (!cleanable.length) return
    setConfirmModal({
      title: 'Clean Up Pipelines',
      message: `This will permanently delete all ${cleanable.length} completed and failed pipeline run(s). This cannot be undone.`,
      variant: 'danger',
      confirmLabel: `Delete ${cleanable.length} Runs`,
      onConfirm: async () => {
        setCleaningUp(true)
        try {
          await pipelineApi.bulkDelete({ statuses: ['completed', 'failed'] })
          await fetchData()
        } finally {
          setCleaningUp(false)
        }
      },
    })
  }

  const handleArchive = async (runId: string) => {
    setActionLoading(runId + ':archive')
    try {
      await pipelineApi.archivePipeline(runId)
      setRuns((prev) => prev.filter((r) => r.id !== runId))
    } catch (e) { console.error(e) }
    finally { setActionLoading(null) }
  }

  const handleUnarchive = async (runId: string) => {
    setActionLoading(runId + ':unarchive')
    try {
      await pipelineApi.unarchivePipeline(runId)
      setRuns((prev) => prev.filter((r) => r.id !== runId))
    } catch (e) { console.error(e) }
    finally { setActionLoading(null) }
  }

  const handleBulkArchive = () => {
    const archivable = runs.filter((r) => r.status === 'completed' || r.status === 'failed')
    if (!archivable.length) return
    setConfirmModal({
      title: 'Archive All Completed/Failed',
      message: `${archivable.length} completed/failed pipeline run(s) will be moved to the archive. You can restore them any time.`,
      variant: 'warning',
      confirmLabel: `Archive ${archivable.length} Runs`,
      onConfirm: async () => {
        setBulkArchiving(true)
        try {
          await pipelineApi.bulkArchive()
          await fetchData(false)
        } finally {
          setBulkArchiving(false)
        }
      },
    })
  }

  const handleBulkUnarchive = () => {
    setConfirmModal({
      title: 'Restore All Archived',
      message: 'All archived pipelines will be restored back to the main view.',
      variant: 'warning',
      confirmLabel: 'Restore All',
      onConfirm: async () => {
        setBulkArchiving(true)
        try {
          await pipelineApi.bulkUnarchive()
          await fetchData(true)
        } finally {
          setBulkArchiving(false)
        }
      },
    })
  }

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedIds.size === pagedRuns.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(pagedRuns.map((r) => r.id)))
    }
  }

  const handleSelectionArchive = () => {
    if (!selectedIds.size) return
    const ids = [...selectedIds]
    setConfirmModal({
      title: 'Archive Selected',
      message: `${ids.length} pipeline run(s) will be moved to the archive. You can restore them any time.`,
      variant: 'warning',
      confirmLabel: `Archive ${ids.length} Runs`,
      onConfirm: async () => {
        setSelectionBusy(true)
        try {
          await pipelineApi.bulkArchive(ids)
          setRuns((prev) => prev.filter((r) => !selectedIds.has(r.id)))
          setSelectedIds(new Set())
        } finally {
          setSelectionBusy(false)
        }
      },
    })
  }

  const handleSelectionDelete = () => {
    if (!selectedIds.size) return
    const ids = [...selectedIds]
    setConfirmModal({
      title: 'Delete Selected',
      message: `${ids.length} pipeline run(s) will be permanently deleted from the database. This cannot be undone.`,
      variant: 'danger',
      confirmLabel: `Delete ${ids.length} Runs`,
      onConfirm: async () => {
        setSelectionBusy(true)
        try {
          const resp = await pipelineApi.bulkDelete({ run_ids: ids })
          if (resp.data.deleted > 0) {
            setRuns((prev) => prev.filter((r) => !selectedIds.has(r.id)))
            setSelectedIds(new Set())
          }
        } finally {
          setSelectionBusy(false)
        }
      },
    })
  }

  const handleSelectionUnarchive = () => {
    if (!selectedIds.size) return
    const ids = [...selectedIds]
    setConfirmModal({
      title: 'Restore Selected',
      message: `${ids.length} archived pipeline run(s) will be restored to the main view.`,
      variant: 'warning',
      confirmLabel: `Restore ${ids.length} Runs`,
      onConfirm: async () => {
        setSelectionBusy(true)
        try {
          await Promise.all(ids.map((id) => pipelineApi.unarchivePipeline(id)))
          setRuns((prev) => prev.filter((r) => !selectedIds.has(r.id)))
          setSelectedIds(new Set())
        } finally {
          setSelectionBusy(false)
        }
      },
    })
  }

  const scrollCarousel = (dir: 'left' | 'right') => {
    if (carouselRef.current) {
      carouselRef.current.scrollBy({ left: dir === 'left' ? -320 : 320, behavior: 'smooth' })
    }
  }

  const applyFilter = (key: string | null) => {
    setFilterKey((prev) => (prev === key ? null : key))
  }

  // ── Render ────────────────────────────────────────────────────────
  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-500">Active and recent pipeline runs</p>
        </div>
        <div className="flex gap-2 flex-wrap justify-end">
          <button
            onClick={() => fetchData(archiveMode)}
            className="flex items-center gap-1 rounded-lg border px-3 py-2 text-sm hover:bg-gray-50"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>
          {/* Archive mode toggle */}
          <button
            onClick={() => { setArchiveMode((m) => !m); setFilterKey(null) }}
            className={`flex items-center gap-1 rounded-lg border px-3 py-2 text-sm transition-colors ${
              archiveMode
                ? 'border-amber-400 bg-amber-50 text-amber-700 hover:bg-amber-100'
                : 'border-gray-200 text-gray-600 hover:bg-gray-50'
            }`}
          >
            <Archive className="h-3.5 w-3.5" />
            {archiveMode ? 'Exit Archive' : 'Archive'}
          </button>
          {/* Bulk archive — only in normal mode when there are completed/failed runs */}
          {!archiveMode && runs.some((r) => r.status === 'completed' || r.status === 'failed') && (
            <button
              onClick={handleBulkArchive}
              disabled={bulkArchiving}
              className="flex items-center gap-1 rounded-lg border border-amber-200 px-3 py-2 text-sm text-amber-700 hover:bg-amber-50 disabled:opacity-50"
            >
              <Archive className="h-3.5 w-3.5" />
              {bulkArchiving ? 'Archiving…' : 'Archive All'}
            </button>
          )}
          {/* Unarchive all — only in archive mode */}
          {archiveMode && runs.length > 0 && (
            <button
              onClick={handleBulkUnarchive}
              disabled={bulkArchiving}
              className="flex items-center gap-1 rounded-lg border border-green-200 px-3 py-2 text-sm text-green-700 hover:bg-green-50 disabled:opacity-50"
            >
              <ArchiveRestore className="h-3.5 w-3.5" />
              {bulkArchiving ? 'Restoring…' : 'Restore All'}
            </button>
          )}
          {/* Clean Up — normal mode only */}
          {!archiveMode && runs.some((r) => r.status === 'completed' || r.status === 'failed') && (
            <button
              onClick={handleCleanUp}
              disabled={cleaningUp}
              className="flex items-center gap-1 rounded-lg border border-red-200 px-3 py-2 text-sm text-red-600 hover:bg-red-50 disabled:opacity-50"
            >
              <Trash2 className="h-3.5 w-3.5" />
              {cleaningUp ? 'Cleaning…' : 'Clean Up'}
            </button>
          )}
          {!archiveMode && (
            <button
              onClick={() => setShowTrigger(true)}
              className="flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-2 text-sm text-white hover:bg-blue-700"
            >
              <Plus className="h-3.5 w-3.5" />
              Trigger Pipeline
            </button>
          )}
        </div>
      </div>

      {/* ── Needs Your Attention ── */}
      {needsAttention.length > 0 && !archiveMode && (
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <Bell className="h-4 w-4 text-orange-500" />
            <h2 className="font-semibold text-gray-800">
              Needs Your Attention
              <span className="ml-2 inline-flex h-5 w-5 items-center justify-center rounded-full bg-orange-500 text-xs text-white">
                {needsAttention.length}
              </span>
            </h2>
          </div>

          {needsAttention.length <= 3 ? (
            /* Grid layout for ≤3 cards */
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {needsAttention.map((run) => (
                <AttentionCard
                  key={run.id}
                  run={run}
                  project={projects.find((p) => p.id === run.project_id)}
                  isActive={filterKey === run.status}
                  onClick={() => applyFilter(run.status)}
                />
              ))}
            </div>
          ) : (
            /* Carousel for >3 cards */
            <div className="relative">
              <button
                onClick={() => scrollCarousel('left')}
                className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-3 z-10 bg-white border shadow rounded-full p-1 hover:bg-gray-50"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>

              <div
                ref={carouselRef}
                className="flex gap-3 overflow-x-auto scroll-smooth pb-2"
                style={{ scrollbarWidth: 'thin' }}
              >
                {needsAttention.map((run) => (
                  <div key={run.id} className="min-w-[300px] max-w-[300px] flex-shrink-0">
                    <AttentionCard
                      run={run}
                      project={projects.find((p) => p.id === run.project_id)}
                      isActive={filterKey === run.status}
                      onClick={() => applyFilter(run.status)}
                    />
                  </div>
                ))}
              </div>

              <button
                onClick={() => scrollCarousel('right')}
                className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-3 z-10 bg-white border shadow rounded-full p-1 hover:bg-gray-50"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          )}
        </div>
      )}

      {/* Stats */}
      {!archiveMode && (
        <div className="grid grid-cols-4 gap-4 mb-6">
          {([
            { label: 'Total Runs', value: stats.total, cls: 'text-gray-600', key: null },
            { label: 'Active', value: stats.active, cls: 'text-blue-600', key: '__active__' },
            { label: 'Completed', value: stats.completed, cls: 'text-green-600', key: 'completed' },
            { label: 'Failed', value: stats.failed, cls: 'text-red-600', key: 'failed' },
          ] as const).map(({ label, value, cls, key }) => {
            const isActive = filterKey === key
            return (
              <button
                key={label}
                onClick={() => applyFilter(key)}
                className={`rounded-lg border bg-white p-4 text-left transition-all hover:shadow-sm ${
                  isActive ? 'ring-2 ring-blue-500 border-blue-300' : 'hover:border-gray-300'
                }`}
              >
                <p className="text-sm text-gray-500">{label}</p>
                <p className={`text-2xl font-bold ${cls}`}>{value}</p>
              </button>
            )
          })}
        </div>
      )}

      {/* Trigger Modal */}
      {showTrigger && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 w-full max-w-md shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Trigger Pipeline Manually</h2>
              <button onClick={() => { setShowTrigger(false); setTriggerData(TRIGGER_EMPTY) }} className="text-gray-400 hover:text-gray-600">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Project</label>
                <select
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  value={triggerData.project_id}
                  onChange={(e) => setTriggerData({ ...triggerData, project_id: e.target.value })}
                >
                  <option value="">Select project...</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Task Number <span className="text-gray-400 font-normal">(e.g. T-42)</span>
                  </label>
                  <input
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    value={triggerData.zoho_task_number}
                    onChange={(e) => setTriggerData({ ...triggerData, zoho_task_number: e.target.value })}
                    placeholder="T-42"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Task ID <span className="text-gray-400 font-normal">(numeric)</span>
                  </label>
                  <input
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    value={triggerData.zoho_task_id}
                    onChange={(e) => setTriggerData({ ...triggerData, zoho_task_id: e.target.value })}
                    placeholder="484726000012345"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Task Title</label>
                <input
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  value={triggerData.zoho_task_title}
                  onChange={(e) => setTriggerData({ ...triggerData, zoho_task_title: e.target.value })}
                  placeholder="Add user authentication"
                />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <button
                onClick={() => { setShowTrigger(false); setTriggerData(TRIGGER_EMPTY) }}
                className="flex-1 rounded-lg border px-4 py-2 text-sm hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleTrigger}
                disabled={!triggerData.project_id || !triggerData.zoho_task_id || triggering}
                className="flex-1 rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {triggering ? 'Triggering...' : 'Trigger'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* All pipeline runs */}
      <div className="rounded-xl border bg-white overflow-hidden">
        {/* Table header with search + active filter chip */}
        <div className="px-4 py-3 border-b bg-gray-50 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="font-medium text-gray-700 text-sm shrink-0">
              {archiveMode ? (
                <span className="flex items-center gap-1.5">
                  <Archive className="h-3.5 w-3.5 text-amber-500" />
                  Archived Pipelines
                </span>
              ) : 'All Pipeline Runs'}
            </h2>
            {filterKey !== null && (
              <span className="flex items-center gap-1 rounded-full bg-blue-100 text-blue-700 px-2 py-0.5 text-xs font-medium">
                {FILTER_LABEL[filterKey] ?? filterKey}
                <button
                  onClick={() => setFilterKey(null)}
                  className="ml-0.5 rounded-full hover:bg-blue-200 p-0.5"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400 pointer-events-none" />
              <input
                type="text"
                placeholder="Search by title or project..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="rounded-lg border bg-white pl-8 pr-3 py-1.5 text-xs text-gray-700 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-300 w-52"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>
            <span className="text-xs text-gray-400 shrink-0">
              {filteredRuns.length} run{filteredRuns.length !== 1 ? 's' : ''}
            </span>
          </div>
        </div>

        {/* Selection action bar */}
        {selectedIds.size > 0 && (
          <div className="px-4 py-2 bg-blue-50 border-b flex items-center justify-between gap-3">
            <span className="text-sm font-medium text-blue-700">
              {selectedIds.size} selected
            </span>
            <div className="flex items-center gap-2">
              {!archiveMode && (
                <button
                  onClick={handleSelectionArchive}
                  disabled={selectionBusy}
                  className="flex items-center gap-1 rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-50 disabled:opacity-50"
                >
                  <Archive className="h-3.5 w-3.5" />
                  Archive Selected
                </button>
              )}
              {archiveMode && (
                <button
                  onClick={handleSelectionUnarchive}
                  disabled={selectionBusy}
                  className="flex items-center gap-1 rounded-lg border border-green-300 bg-white px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-50 disabled:opacity-50"
                >
                  <ArchiveRestore className="h-3.5 w-3.5" />
                  Restore Selected
                </button>
              )}
              <button
                onClick={handleSelectionDelete}
                disabled={selectionBusy}
                className="flex items-center gap-1 rounded-lg border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete Selected
              </button>
              <button
                onClick={() => setSelectedIds(new Set())}
                className="rounded p-1 text-gray-400 hover:text-gray-600"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}

        <table className="w-full text-sm">
          <thead className="border-b">
            <tr>
              <th className="pl-4 pr-2 py-3 w-8">
                <input
                  type="checkbox"
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  checked={pagedRuns.length > 0 && selectedIds.size === pagedRuns.length}
                  ref={(el) => {
                    if (el) el.indeterminate = selectedIds.size > 0 && selectedIds.size < pagedRuns.length
                  }}
                  onChange={toggleSelectAll}
                />
              </th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">Task</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">Project</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">Status</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">Created</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {loading ? (
              <tr>
                <td colSpan={6} className="py-12 text-center text-gray-400">Loading...</td>
              </tr>
            ) : pagedRuns.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-12 text-center text-gray-400">
                  {archiveMode ? (
                    <>No archived pipeline runs.</>
                  ) : filterKey ? (
                    <>No runs match this filter. <button onClick={() => setFilterKey(null)} className="text-blue-600 hover:underline">Clear filter</button></>
                  ) : (
                    <>No pipeline runs yet. Trigger one or call{' '}
                      <code className="bg-gray-100 px-1 rounded">GET /task-assign</code></>
                  )}
                </td>
              </tr>
            ) : (
              pagedRuns.map((run) => {
                const project = projects.find((p) => p.id === run.project_id)
                const isAttention = (ATTENTION_STAGES as readonly string[]).includes(run.status)
                const isActive = ACTIVE_STAGES.includes(run.status)
                const isFailed = run.status === 'failed'
                const mrUrl = run.merge_requests?.[0]?.mr_url
                const loadingStop = actionLoading === run.id + ':stop'
                const loadingRestart = actionLoading === run.id + ':restart'
                const isSelected = selectedIds.has(run.id)
                return (
                  <tr key={run.id} className={`hover:bg-gray-50 ${isSelected ? 'bg-blue-50/60' : isAttention ? 'bg-orange-50/40' : ''}`}>
                    <td className="pl-4 pr-2 py-3 w-8">
                      <input
                        type="checkbox"
                        className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        checked={isSelected}
                        onChange={() => toggleSelect(run.id)}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {run.zoho_task_number && (
                          <span className="inline-flex shrink-0 items-center rounded-full bg-blue-50 border border-blue-200 px-2 py-0.5 text-xs font-mono font-medium text-blue-700">
                            #{run.zoho_task_number}
                          </span>
                        )}
                        <Link
                          to={`/pipelines/${run.id}`}
                          className="font-medium hover:text-blue-600 hover:underline"
                        >
                          {run.zoho_task_title || run.zoho_task_id || '—'}
                        </Link>
                      </div>
                      {run.zoho_task_description && (
                        <div className="text-xs text-gray-400 truncate max-w-xs mt-0.5">
                          {run.zoho_task_description}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500">{project?.name || '—'}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={run.status} />
                    </td>
                    <td className="px-4 py-3 text-gray-500 whitespace-nowrap">
                      {fmtDateTime(run.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2 flex-wrap">
                        {/* PR link for completed runs */}
                        {mrUrl && (
                          <a
                            href={mrUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="flex items-center gap-1 rounded-lg border border-gray-200 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
                          >
                            <ExternalLink className="h-3 w-3" />
                            PR
                          </a>
                        )}
                        {/* Stop active pipelines */}
                        {isActive && !archiveMode && (
                          <button
                            onClick={() => handleStop(run.id)}
                            disabled={loadingStop}
                            className="flex items-center gap-1 rounded-lg border border-red-200 px-2 py-1 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50"
                          >
                            <Square className="h-3 w-3" />
                            {loadingStop ? '…' : 'Stop'}
                          </button>
                        )}
                        {/* Restart failed pipelines */}
                        {isFailed && !archiveMode && (
                          <button
                            onClick={() => handleRestart(run.id)}
                            disabled={loadingRestart}
                            className="flex items-center gap-1 rounded-lg border border-green-200 px-2 py-1 text-xs text-green-700 hover:bg-green-50 disabled:opacity-50"
                          >
                            <RotateCcw className="h-3 w-3" />
                            {loadingRestart ? '…' : 'Restart'}
                          </button>
                        )}
                        {/* Review button for gate stages */}
                        {isAttention && (
                          <Link
                            to={`/pipelines/${run.id}`}
                            className="flex items-center gap-1 rounded-lg bg-orange-600 px-2 py-1 text-xs font-medium text-white hover:bg-orange-700"
                          >
                            Review →
                          </Link>
                        )}
                        <Link
                          to={`/pipelines/${run.id}`}
                          className={`font-medium hover:underline text-xs ${isAttention ? 'text-orange-600' : 'text-blue-600'}`}
                        >
                          View →
                        </Link>
                        {!archiveMode && (
                          <button
                            onClick={() => handleArchive(run.id)}
                            disabled={actionLoading === run.id + ':archive'}
                            title="Archive pipeline"
                            className="rounded p-1 text-gray-300 hover:text-amber-500 hover:bg-amber-50 disabled:opacity-40"
                          >
                            <Archive className="h-3.5 w-3.5" />
                          </button>
                        )}
                        {archiveMode && (
                          <button
                            onClick={() => handleUnarchive(run.id)}
                            disabled={actionLoading === run.id + ':unarchive'}
                            title="Restore pipeline"
                            className="flex items-center gap-1 rounded-lg border border-green-200 px-2 py-1 text-xs text-green-700 hover:bg-green-50 disabled:opacity-40"
                          >
                            <ArchiveRestore className="h-3 w-3" />
                            {actionLoading === run.id + ':unarchive' ? '…' : 'Restore'}
                          </button>
                        )}
                        <button
                          onClick={() => handleDelete(run.id)}
                          disabled={actionLoading === run.id + ':delete'}
                          title="Delete pipeline"
                          className="rounded p-1 text-gray-300 hover:text-red-500 hover:bg-red-50 disabled:opacity-40"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>

        {/* Pagination */}
        {!loading && filteredRuns.length > 0 && (
          <div className="flex items-center justify-between px-4 py-3 border-t bg-gray-50 text-sm">
            <div className="flex items-center gap-1 text-gray-500">
              <span className="mr-1">Rows per page:</span>
              {([10, 25, 50] as const).map((n) => (
                <button
                  key={n}
                  onClick={() => setPageSize(n)}
                  className={`px-2 py-0.5 rounded text-xs font-medium ${
                    pageSize === n
                      ? 'bg-blue-100 text-blue-700'
                      : 'hover:bg-gray-200 text-gray-600'
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-3">
              <span className="text-gray-500 text-xs">
                {page * pageSize + 1}–{Math.min((page + 1) * pageSize, filteredRuns.length)} of {filteredRuns.length}
              </span>
              <div className="flex gap-1">
                <button
                  onClick={() => setPage((p) => p - 1)}
                  disabled={page === 0}
                  className="rounded border px-2 py-1 text-xs hover:bg-white disabled:opacity-40"
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={page + 1 >= totalPages}
                  className="rounded border px-2 py-1 text-xs hover:bg-white disabled:opacity-40"
                >
                  <ChevronRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Confirm Modal */}
      {confirmModal && (
        <ConfirmModal
          title={confirmModal.title}
          message={confirmModal.message}
          variant={confirmModal.variant}
          confirmLabel={confirmModal.confirmLabel}
          onConfirm={async () => {
            await confirmModal.onConfirm()
            setConfirmModal(null)
          }}
          onCancel={() => setConfirmModal(null)}
        />
      )}
    </div>
  )
}

// ── ConfirmModal ──────────────────────────────────────────────────────
function ConfirmModal({
  title, message, variant, confirmLabel, onConfirm, onCancel,
}: {
  title: string
  message: string
  variant: 'danger' | 'warning'
  confirmLabel: string
  onConfirm: () => Promise<void>
  onCancel: () => void
}) {
  const [busy, setBusy] = useState(false)
  const confirmCls = variant === 'danger'
    ? 'bg-red-600 hover:bg-red-700 text-white'
    : 'bg-amber-500 hover:bg-amber-600 text-white'
  const iconCls = variant === 'danger' ? 'text-red-500' : 'text-amber-500'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
        <div className="p-6">
          <div className="flex items-start gap-4">
            <div className={`mt-0.5 shrink-0 rounded-full p-2 ${variant === 'danger' ? 'bg-red-50' : 'bg-amber-50'}`}>
              <Trash2 className={`h-5 w-5 ${iconCls}`} />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-base font-semibold text-gray-900">{title}</h3>
              <p className="mt-1 text-sm text-gray-500 leading-relaxed">{message}</p>
            </div>
          </div>
        </div>
        <div className="px-6 pb-6 flex gap-3 justify-end">
          <button
            onClick={onCancel}
            disabled={busy}
            className="rounded-lg border px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={async () => { setBusy(true); await onConfirm() }}
            disabled={busy}
            className={`rounded-lg px-4 py-2 text-sm font-medium disabled:opacity-50 ${confirmCls}`}
          >
            {busy ? 'Please wait…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── AttentionCard sub-component ──────────────────────────────────────
function AttentionCard({
  run, project, isActive, onClick,
}: {
  run: PipelineRun
  project: Project | undefined
  isActive: boolean
  onClick: () => void
}) {
  const meta = ATTENTION_META[run.status]
  if (!meta) return null
  const Icon = meta.icon
  const mrUrl = run.merge_requests?.[0]?.mr_url

  return (
    <div
      onClick={onClick}
      className={`rounded-xl border-2 p-4 cursor-pointer transition-all select-none
        ${meta.border} ${meta.bg}
        ${isActive ? 'ring-2 ring-offset-1 ring-blue-500' : 'hover:shadow-sm'}
      `}
    >
      <div className="flex items-start gap-3">
        <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${meta.iconCls}`} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 min-w-0">
            {run.zoho_task_number && (
              <span className="shrink-0 rounded-full bg-white/70 border border-current px-1.5 py-0.5 text-xs font-mono font-medium opacity-80">
                #{run.zoho_task_number}
              </span>
            )}
            <p className="font-semibold text-gray-900 truncate text-sm">
              {run.zoho_task_title || `Run ${run.id.slice(0, 8)}`}
            </p>
          </div>
          <p className="text-xs text-gray-500 mt-0.5">
            {project?.name || 'Unknown project'} · {meta.label}
          </p>
          {run.zoho_task_description && (
            <p className="text-xs text-gray-500 mt-1 line-clamp-2">
              {run.zoho_task_description}
            </p>
          )}
        </div>
      </div>
      <div className="mt-3 flex gap-2">
        <Link
          to={`/pipelines/${run.id}`}
          onClick={(e) => e.stopPropagation()}
          className={`flex-1 flex items-center justify-center rounded-lg px-3 py-1.5 text-xs font-medium text-white ${meta.btnCls}`}
        >
          {meta.action} →
        </Link>
        {mrUrl && (
          <a
            href={mrUrl}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="flex items-center gap-1 rounded-lg border border-current px-2 py-1.5 text-xs font-medium text-gray-600 hover:bg-white/60"
          >
            <ExternalLink className="h-3 w-3" />
            PR
          </a>
        )}
      </div>
    </div>
  )
}
