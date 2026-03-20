import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { TestResult, TestScenario, pipelineApi } from '../services/api'
import { Plus, Pencil, Trash2, Check, X, SkipForward, ChevronDown, ChevronUp, Monitor, RefreshCw } from 'lucide-react'

interface Props {
  runId: string
  result: TestResult
  onAction: () => void
  readOnly?: boolean
}

function newScenario(type: 'playwright' | 'manual' = 'manual'): TestScenario {
  return {
    id: `s-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    name: '',
    steps: '',
    expected: '',
    status: 'pending',
    type,
  }
}

function buildFailedSummary(
  playwrightScenarios: TestScenario[],
  manualScenarios: TestScenario[],
  result?: TestResult,
): string {
  const parts: string[] = []

  const failedPlaywright = playwrightScenarios.filter((s) => s.status === 'failed')
  if (failedPlaywright.length > 0) {
    const lines = failedPlaywright.map((s, i) => {
      let text = `${i + 1}. ${s.name}`
      if (s.steps) text += `\n   Steps: ${s.steps}`
      if (s.expected) text += `\n   Expected: ${s.expected}`
      return text
    })
    parts.push(`The following automated Playwright tests FAILED and need code fixes:\n\n${lines.join('\n\n')}`)
  }

  if (result?.browser_test_status === 'failed' && result.browser_test_output) {
    parts.push(`Full automated browser test report:\n\n${result.browser_test_output}`)
  }

  const failedManual = manualScenarios.filter((s) => s.status === 'failed')
  if (failedManual.length > 0) {
    const lines = failedManual.map((s, i) => {
      let text = `${i + 1}. ${s.name}`
      if (s.steps) text += `\n   Steps: ${s.steps}`
      if (s.expected) text += `\n   Expected: ${s.expected}`
      return text
    })
    parts.push(`The following manual test cases FAILED:\n\n${lines.join('\n\n')}`)
  }

  return parts.join('\n\n---\n\n')
}

// ── Playwright scenario card ──────────────────────────────────────────────────
function PlaywrightCard({
  scenario,
  idx,
  readOnly,
  retrying,
  onEdit,
  onDelete,
  onRetry,
}: {
  scenario: TestScenario
  idx: number
  readOnly?: boolean
  retrying?: boolean
  onEdit: (s: TestScenario) => void
  onDelete: (id: string) => void
  onRetry: (id: string) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const status = retrying ? 'running' : scenario.status

  const statusCls =
    retrying
      ? 'bg-blue-100 text-blue-600 border-blue-200'
      : status === 'passed'
      ? 'bg-green-100 text-green-700 border-green-200'
      : status === 'failed'
      ? 'bg-red-100 text-red-600 border-red-200'
      : 'bg-gray-100 text-gray-500 border-gray-200'

  const cardBorder =
    retrying
      ? 'border-blue-200 bg-blue-50'
      : status === 'passed'
      ? 'border-green-200 bg-green-50'
      : status === 'failed'
      ? 'border-red-200 bg-red-50'
      : 'border-gray-200 bg-white'

  return (
    <div className={`rounded-lg border p-3.5 flex flex-col gap-2 transition-colors ${cardBorder}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-2 min-w-0 flex-1">
          <span className="text-xs text-gray-400 font-mono mt-0.5 shrink-0">{idx + 1}</span>
          <span
            className={`font-medium text-sm leading-snug ${
              retrying
                ? 'text-blue-700'
                : status === 'passed'
                ? 'text-green-800'
                : status === 'failed'
                ? 'text-red-800'
                : 'text-gray-800'
            }`}
          >
            {scenario.name}
          </span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold ${statusCls}`}>
            {retrying && <RefreshCw className="h-3 w-3 animate-spin" />}
            {retrying ? 'RUNNING…' : status === 'passed' ? 'PASSED' : status === 'failed' ? 'FAILED' : 'PENDING'}
          </span>
          {!readOnly && !retrying && (
            <>
              {(scenario.status === 'failed' || scenario.status === 'pending') && (
                <button
                  onClick={() => onRetry(scenario.id)}
                  className="rounded p-1 text-gray-300 hover:text-blue-600 hover:bg-blue-50"
                  title="Retry this test"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                </button>
              )}
              <button
                onClick={() => onEdit(scenario)}
                className="rounded p-1 text-gray-300 hover:text-blue-600 hover:bg-blue-50"
                title="Edit"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => onDelete(scenario.id)}
                className="rounded p-1 text-gray-300 hover:text-red-500 hover:bg-red-50"
                title="Delete"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </>
          )}
        </div>
      </div>

      {(scenario.steps || scenario.expected) && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 self-start"
        >
          {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          {expanded ? 'Hide details' : 'Show details'}
        </button>
      )}

      {expanded && (
        <div className="rounded bg-white border border-gray-100 p-2.5 space-y-1.5 text-xs">
          {scenario.steps && (
            <div>
              <p className="font-semibold text-gray-500 mb-0.5">Steps</p>
              <p className="text-gray-700 whitespace-pre-line">{scenario.steps}</p>
            </div>
          )}
          {scenario.expected && (
            <div>
              <p className="font-semibold text-gray-500 mb-0.5">Expected</p>
              <p className="text-gray-700 whitespace-pre-line">{scenario.expected}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Edit modal/inline ─────────────────────────────────────────────────────────
function EditModal({
  draft,
  onChange,
  onSave,
  onCancel,
}: {
  draft: Partial<TestScenario>
  onChange: (patch: Partial<TestScenario>) => void
  onSave: () => void
  onCancel: () => void
}) {
  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 space-y-2">
      <input
        autoFocus
        className="w-full rounded border px-2 py-1.5 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-blue-300"
        value={draft.name ?? ''}
        onChange={(e) => onChange({ name: e.target.value })}
        placeholder="Test case name *"
      />
      <textarea
        className="w-full rounded border px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-300"
        rows={2}
        value={draft.steps ?? ''}
        onChange={(e) => onChange({ steps: e.target.value })}
        placeholder="Steps to reproduce (optional)"
      />
      <input
        className="w-full rounded border px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-300"
        value={draft.expected ?? ''}
        onChange={(e) => onChange({ expected: e.target.value })}
        placeholder="Expected result (optional)"
      />
      <div className="flex gap-2">
        <button
          onClick={onSave}
          disabled={!draft.name?.trim()}
          className="rounded bg-green-600 px-3 py-1.5 text-xs text-white hover:bg-green-700 disabled:opacity-40"
        >
          Save
        </button>
        <button onClick={onCancel} className="rounded border px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-50">
          Cancel
        </button>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function TestResults({ runId, result, onAction, readOnly }: Props) {
  const [scenarios, setScenarios] = useState<TestScenario[]>([])
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState<Partial<TestScenario>>({})
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showReworkForm, setShowReworkForm] = useState(false)
  const [reworkFeedback, setReworkFeedback] = useState('')
  const [browserExpanded, setBrowserExpanded] = useState(false)
  const [retryingIds, setRetryingIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (result.scenarios) {
      try {
        setScenarios(JSON.parse(result.scenarios))
      } catch {
        setScenarios([])
      }
    } else {
      setScenarios([])
    }
  }, [result.scenarios])

  // Split into playwright vs manual
  const playwrightScenarios = scenarios.filter((s) => s.type === 'playwright')
  const manualScenarios = scenarios.filter((s) => s.type !== 'playwright')

  // ── Row / card actions ─────────────────────────────────────────────────────
  const markPass = (id: string) =>
    setScenarios((prev) =>
      prev.map((s) => (s.id === id ? { ...s, status: s.status === 'passed' ? 'pending' : 'passed' } : s)),
    )

  const markFail = (id: string) =>
    setScenarios((prev) =>
      prev.map((s) => (s.id === id ? { ...s, status: s.status === 'failed' ? 'pending' : 'failed' } : s)),
    )

  const startEdit = (s: TestScenario) => {
    setEditingId(s.id)
    setEditDraft({ name: s.name, steps: s.steps ?? '', expected: s.expected ?? '' })
  }

  const commitEdit = () => {
    if (!editingId) return
    setScenarios((prev) => prev.map((s) => (s.id === editingId ? { ...s, ...editDraft } : s)))
    setEditingId(null)
    setEditDraft({})
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditDraft({})
  }

  const deleteScenario = (id: string) => setScenarios((prev) => prev.filter((s) => s.id !== id))

  const addManualRow = () => {
    const s = newScenario('manual')
    setScenarios((prev) => [...prev, s])
    setEditingId(s.id)
    setEditDraft({ name: '', steps: '', expected: '' })
  }

  const retryScenario = async (id: string) => {
    setRetryingIds((prev) => new Set([...prev, id]))
    try {
      const resp = await pipelineApi.retryPlaywright(runId, [id])
      const updated: TestScenario[] = JSON.parse(resp.data.scenarios)
      setScenarios(updated)
    } catch {
      // Keep existing status on error — user can try again
    } finally {
      setRetryingIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

  const openReworkForm = () => {
    setReworkFeedback(buildFailedSummary(playwrightScenarios, manualScenarios, result))
    setShowReworkForm(true)
  }

  // ── API calls ───────────────────────────────────────────────────────────────
  const saveScenarios = async () => {
    setSaving(true)
    try {
      await pipelineApi.updateScenarios(runId, scenarios)
    } finally {
      setSaving(false)
    }
  }

  const handleApprove = async () => {
    setLoading(true)
    try {
      const final = scenarios.map((s) => (s.status === 'pending' ? { ...s, status: 'failed' as const } : s))
      await pipelineApi.approveTests(runId, final)
      onAction()
    } finally {
      setLoading(false)
    }
  }

  const handleSkip = async () => {
    setLoading(true)
    try {
      await pipelineApi.skipTests(runId)
      onAction()
    } finally {
      setLoading(false)
    }
  }

  const handleRework = async () => {
    if (!reworkFeedback.trim()) return
    setLoading(true)
    try {
      await pipelineApi.reworkTests(runId, reworkFeedback)
      onAction()
    } finally {
      setLoading(false)
    }
  }

  // ── Derived ─────────────────────────────────────────────────────────────────
  const manualPassed = manualScenarios.filter((s) => s.status === 'passed').length
  const manualFailed = manualScenarios.filter((s) => s.status === 'failed').length
  const manualTotal = manualScenarios.length

  const playwrightPassed = playwrightScenarios.filter((s) => s.status === 'passed').length
  const playwrightFailed = playwrightScenarios.filter((s) => s.status === 'failed').length

  const hasFailed = manualFailed > 0 || playwrightFailed > 0
  const allManualPassed = manualTotal > 0 && manualPassed === manualTotal
  const allPassed =
    (manualTotal === 0 || allManualPassed) &&
    (playwrightScenarios.length === 0 || playwrightFailed === 0)

  return (
    <div className="rounded-xl border bg-white p-5 space-y-5">

      {/* ── Playwright Automated Tests ── */}
      {playwrightScenarios.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Monitor className="h-4 w-4 text-indigo-500" />
              <h3 className="font-semibold text-gray-900">Playwright Automated Tests</h3>
              <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                playwrightFailed > 0
                  ? 'bg-red-100 text-red-600'
                  : playwrightPassed === playwrightScenarios.length
                  ? 'bg-green-100 text-green-700'
                  : 'bg-gray-100 text-gray-500'
              }`}>
                {playwrightPassed}/{playwrightScenarios.length} passed
              </span>
            </div>
            {/* Full report toggle */}
            {result.browser_test_output && (
              <button
                onClick={() => setBrowserExpanded((v) => !v)}
                className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600"
              >
                {browserExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                {browserExpanded ? 'Hide full report' : 'Full report'}
              </button>
            )}
          </div>

          {/* Per-scenario cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
            {playwrightScenarios.map((s, idx) =>
              editingId === s.id ? (
                <div key={s.id} className="sm:col-span-2">
                  <EditModal
                    draft={editDraft}
                    onChange={(patch) => setEditDraft((d) => ({ ...d, ...patch }))}
                    onSave={commitEdit}
                    onCancel={cancelEdit}
                  />
                </div>
              ) : (
                <PlaywrightCard
                  key={s.id}
                  scenario={s}
                  idx={idx}
                  readOnly={readOnly}
                  retrying={retryingIds.has(s.id)}
                  onEdit={startEdit}
                  onDelete={deleteScenario}
                  onRetry={retryScenario}
                />
              ),
            )}
          </div>

          {/* Full browser test report (collapsible) */}
          {browserExpanded && result.browser_test_output && (
            <div className="rounded-lg border border-gray-200 px-4 py-3 prose prose-sm max-w-none text-gray-700 bg-gray-50">
              <ReactMarkdown>{result.browser_test_output}</ReactMarkdown>
            </div>
          )}
        </div>
      )}

      {/* Legacy "Automated Browser Tests" bar — shown only when no per-scenario playwright cards */}
      {playwrightScenarios.length === 0 &&
        result.browser_test_status &&
        result.browser_test_status !== 'skipped' && (
          <div className="rounded-lg border border-gray-200 overflow-hidden">
            <button
              onClick={() => setBrowserExpanded((v) => !v)}
              className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors"
            >
              <div className="flex items-center gap-2">
                <Monitor className="h-4 w-4 text-gray-500" />
                <span className="font-medium text-gray-800 text-sm">Automated Browser Tests</span>
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                    result.browser_test_status === 'passed'
                      ? 'bg-green-100 text-green-700'
                      : result.browser_test_status === 'failed'
                      ? 'bg-red-100 text-red-600'
                      : 'bg-yellow-100 text-yellow-700'
                  }`}
                >
                  {result.browser_test_status.toUpperCase()}
                </span>
              </div>
              {browserExpanded ? (
                <ChevronUp className="h-4 w-4 text-gray-400" />
              ) : (
                <ChevronDown className="h-4 w-4 text-gray-400" />
              )}
            </button>
            {browserExpanded && result.browser_test_output && (
              <div className="px-4 py-3 prose prose-sm max-w-none text-gray-700">
                <ReactMarkdown>{result.browser_test_output}</ReactMarkdown>
              </div>
            )}
            {browserExpanded && !result.browser_test_output && (
              <div className="px-4 py-3 text-sm text-gray-400">No report output available.</div>
            )}
          </div>
        )}

      {/* ── Manual Testing ── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="font-semibold text-gray-900">Manual Testing</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              Mark each scenario as passed or failed. Add extra rows for edge cases.
            </p>
          </div>
          {manualTotal > 0 && (
            <div className="text-right shrink-0 space-y-0.5">
              <div>
                <span className="text-sm font-semibold text-green-700">{manualPassed}</span>
                <span className="text-xs text-gray-400 ml-1">passed</span>
                {manualFailed > 0 && (
                  <>
                    <span className="text-sm font-semibold text-red-600 ml-2">{manualFailed}</span>
                    <span className="text-xs text-gray-400 ml-1">failed</span>
                  </>
                )}
                <span className="text-xs text-gray-400 ml-2">/ {manualTotal}</span>
              </div>
            </div>
          )}
        </div>

        {manualTotal > 0 && (
          <div className="mb-3">
            <div className="h-2 rounded-full bg-gray-100 overflow-hidden flex">
              <div
                className="h-2 bg-green-500 transition-all"
                style={{ width: `${(manualPassed / manualTotal) * 100}%` }}
              />
              <div
                className="h-2 bg-red-400 transition-all"
                style={{ width: `${(manualFailed / manualTotal) * 100}%` }}
              />
            </div>
          </div>
        )}

        <div className="overflow-x-auto rounded-lg border border-gray-200 mb-3">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-3 py-2 text-left font-medium text-gray-600 w-6 text-xs">#</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Test Case</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600 w-24 text-xs">Status</th>
                {!readOnly && (
                  <th className="px-3 py-2 w-28 text-xs font-medium text-gray-600 text-center">Result</th>
                )}
                {!readOnly && <th className="px-3 py-2 w-16"></th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {manualScenarios.length === 0 && (
                <tr>
                  <td colSpan={readOnly ? 3 : 5} className="px-4 py-8 text-center text-gray-400 text-sm">
                    No manual test scenarios.{!readOnly && ' Click "Add Test Case" to add one.'}
                  </td>
                </tr>
              )}
              {manualScenarios.map((s, idx) =>
                editingId === s.id ? (
                  <tr key={s.id} className="bg-blue-50">
                    <td className="px-3 py-2 text-gray-400 text-xs">{idx + 1}</td>
                    <td className="px-3 py-2" colSpan={readOnly ? 2 : 1}>
                      <div className="space-y-2">
                        <input
                          autoFocus
                          className="w-full rounded border px-2 py-1.5 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-blue-300"
                          value={editDraft.name ?? ''}
                          onChange={(e) => setEditDraft((d) => ({ ...d, name: e.target.value }))}
                          placeholder="Test case name *"
                        />
                        <textarea
                          className="w-full rounded border px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-300"
                          rows={2}
                          value={editDraft.steps ?? ''}
                          onChange={(e) => setEditDraft((d) => ({ ...d, steps: e.target.value }))}
                          placeholder="Steps to reproduce (optional)"
                        />
                        <input
                          className="w-full rounded border px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-300"
                          value={editDraft.expected ?? ''}
                          onChange={(e) => setEditDraft((d) => ({ ...d, expected: e.target.value }))}
                          placeholder="Expected result (optional)"
                        />
                      </div>
                    </td>
                    <td className="px-3 py-2"></td>
                    {!readOnly && (
                      <td className="px-3 py-2" colSpan={2}>
                        <div className="flex gap-1">
                          <button
                            onClick={commitEdit}
                            disabled={!editDraft.name?.trim()}
                            className="rounded bg-green-600 p-1.5 text-white hover:bg-green-700 disabled:opacity-40"
                            title="Save"
                          >
                            <Check className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={cancelEdit}
                            className="rounded border p-1.5 text-gray-500 hover:bg-gray-50"
                            title="Cancel"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ) : (
                  <>
                    <tr
                      key={s.id}
                      className={`transition-colors ${
                        s.status === 'passed'
                          ? 'bg-green-50'
                          : s.status === 'failed'
                          ? 'bg-red-50'
                          : 'hover:bg-gray-50'
                      }`}
                    >
                      <td className="px-3 py-2.5 text-gray-400 text-xs">{idx + 1}</td>
                      <td className="px-3 py-2.5">
                        <div className="flex items-start gap-1.5 min-w-0">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-1">
                              <span
                                className={`font-medium ${
                                  s.status === 'passed'
                                    ? 'line-through text-gray-400'
                                    : s.status === 'failed'
                                    ? 'text-red-700'
                                    : 'text-gray-800'
                                }`}
                              >
                                {s.name}
                              </span>
                              {(s.steps || s.expected) && (
                                <button
                                  onClick={() => setExpandedId(expandedId === s.id ? null : s.id)}
                                  className="shrink-0 text-gray-300 hover:text-gray-500"
                                  title="Show full details"
                                >
                                  {expandedId === s.id ? (
                                    <ChevronUp className="h-3.5 w-3.5" />
                                  ) : (
                                    <ChevronDown className="h-3.5 w-3.5" />
                                  )}
                                </button>
                              )}
                            </div>
                            {s.steps && (
                              <p className="text-xs text-gray-400 mt-0.5 truncate max-w-xs" title={s.steps}>
                                {s.steps}
                              </p>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-3 py-2.5">
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                            s.status === 'passed'
                              ? 'bg-green-100 text-green-700'
                              : s.status === 'failed'
                              ? 'bg-red-100 text-red-600'
                              : 'bg-gray-100 text-gray-500'
                          }`}
                        >
                          {s.status === 'passed' ? 'Passed' : s.status === 'failed' ? 'Failed' : 'Pending'}
                        </span>
                      </td>
                      {!readOnly && (
                        <td className="px-3 py-2.5">
                          <div className="flex items-center gap-1.5 justify-center">
                            <button
                              onClick={() => markPass(s.id)}
                              title={s.status === 'passed' ? 'Undo pass' : 'Mark as passed'}
                              className={`flex items-center justify-center h-7 w-7 rounded-full border-2 transition-all ${
                                s.status === 'passed'
                                  ? 'border-green-500 bg-green-500 text-white'
                                  : 'border-gray-300 bg-white text-gray-400 hover:border-green-400 hover:text-green-500'
                              }`}
                            >
                              <Check className="h-3.5 w-3.5" strokeWidth={2.5} />
                            </button>
                            <button
                              onClick={() => markFail(s.id)}
                              title={s.status === 'failed' ? 'Undo fail' : 'Mark as failed'}
                              className={`flex items-center justify-center h-7 w-7 rounded-full border-2 transition-all ${
                                s.status === 'failed'
                                  ? 'border-red-500 bg-red-500 text-white'
                                  : 'border-gray-300 bg-white text-gray-400 hover:border-red-400 hover:text-red-500'
                              }`}
                            >
                              <X className="h-3.5 w-3.5" strokeWidth={2.5} />
                            </button>
                          </div>
                        </td>
                      )}
                      {!readOnly && (
                        <td className="px-3 py-2.5">
                          <div className="flex items-center gap-1 justify-end">
                            <button
                              onClick={() => startEdit(s)}
                              className="rounded p-1 text-gray-300 hover:text-blue-600 hover:bg-blue-50"
                              title="Edit"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </button>
                            <button
                              onClick={() => deleteScenario(s.id)}
                              className="rounded p-1 text-gray-300 hover:text-red-500 hover:bg-red-50"
                              title="Delete row"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </td>
                      )}
                    </tr>
                    {expandedId === s.id && (s.steps || s.expected) && (
                      <tr
                        key={`${s.id}-detail`}
                        className={
                          s.status === 'passed' ? 'bg-green-50' : s.status === 'failed' ? 'bg-red-50' : 'bg-gray-50'
                        }
                      >
                        <td />
                        <td colSpan={readOnly ? 2 : 4} className="px-3 pb-3 pt-0">
                          <div className="rounded-lg bg-white border border-gray-100 p-3 space-y-2 text-xs">
                            {s.steps && (
                              <div>
                                <p className="font-semibold text-gray-500 mb-0.5">Steps</p>
                                <p className="text-gray-700 whitespace-pre-line">{s.steps}</p>
                              </div>
                            )}
                            {s.expected && (
                              <div>
                                <p className="font-semibold text-gray-500 mb-0.5">Expected Result</p>
                                <p className="text-gray-700 whitespace-pre-line">{s.expected}</p>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ),
              )}
            </tbody>
          </table>
        </div>

        {!readOnly && (
          <button
            onClick={addManualRow}
            disabled={editingId !== null}
            className="mb-1 flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 disabled:opacity-40"
          >
            <Plus className="h-4 w-4" />
            Add Test Case
          </button>
        )}
      </div>

      {/* ── Rework form ── */}
      {!readOnly && showReworkForm && (
        <div className="rounded-lg bg-orange-50 border border-orange-200 p-4">
          <label className="block text-sm font-medium text-orange-800 mb-1">
            Code Change Request
            {(manualFailed > 0 || playwrightFailed > 0) && (
              <span className="ml-2 text-xs font-normal text-orange-600">
                ({playwrightFailed + manualFailed} failed test{playwrightFailed + manualFailed > 1 ? 's' : ''} pre-filled)
              </span>
            )}
          </label>
          <textarea
            className="w-full rounded-lg border px-3 py-2 text-sm font-mono"
            value={reworkFeedback}
            onChange={(e) => setReworkFeedback(e.target.value)}
            rows={6}
            placeholder="Describe what needs to be fixed..."
          />
          <div className="flex gap-2 mt-2">
            <button onClick={() => setShowReworkForm(false)} className="text-sm text-gray-500 hover:text-gray-700">
              Cancel
            </button>
            <button
              onClick={handleRework}
              disabled={!reworkFeedback.trim() || loading}
              className="rounded-lg bg-orange-600 px-4 py-1.5 text-sm text-white font-medium hover:bg-orange-700 disabled:opacity-50"
            >
              {loading ? 'Sending...' : 'Send for Rework'}
            </button>
          </div>
        </div>
      )}

      {/* ── Action buttons ── */}
      {!readOnly && (
        <div className="flex gap-2 flex-wrap items-center">
          {scenarios.length > 0 && (
            <button
              onClick={saveScenarios}
              disabled={saving}
              className="rounded-lg border px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          )}

          {!showReworkForm && (
            <button
              onClick={openReworkForm}
              className={`rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
                hasFailed
                  ? 'border-orange-400 bg-orange-50 text-orange-700 hover:bg-orange-100'
                  : 'border-gray-300 text-gray-600 hover:bg-gray-50'
              }`}
            >
              {hasFailed
                ? `Request Code Changes (${playwrightFailed + manualFailed} failed)`
                : 'Request Code Changes'}
            </button>
          )}

          <button
            onClick={handleSkip}
            disabled={loading}
            className="flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50"
          >
            <SkipForward className="h-3.5 w-3.5" />
            Skip Testing
          </button>

          <button
            onClick={handleApprove}
            disabled={loading || scenarios.length === 0 || hasFailed}
            className={`ml-auto rounded-lg px-4 py-2 text-sm text-white font-medium disabled:opacity-50 ${
              allPassed ? 'bg-green-600 hover:bg-green-700' : 'bg-blue-600 hover:bg-blue-700'
            }`}
            title={hasFailed ? 'Resolve failed test cases before creating PR' : ''}
          >
            {loading
              ? 'Processing…'
              : allPassed
              ? '✓ All Passed — Create PR'
              : hasFailed
              ? `Fix ${playwrightFailed + manualFailed} failed case${playwrightFailed + manualFailed > 1 ? 's' : ''} to proceed`
              : `Testing Done — Create PR (${manualPassed}/${manualTotal} manual passed)`}
          </button>
        </div>
      )}
    </div>
  )
}
