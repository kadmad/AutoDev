import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, ExternalLink, Square, RefreshCw, ChevronDown, ChevronUp, X } from 'lucide-react'
import { pipelineApi, PipelineRun, Plan, TestResult as TR, MergeRequest, DiffFile } from '../services/api'
import { fmtTime } from '../utils/time'
import PipelineStages from '../components/PipelineStages'
import StatusBadge from '../components/StatusBadge'
import LogStream from '../components/LogStream'
import PlanReview from './PlanReview'
import TestResults from './TestResults'
import PlanContent from '../components/PlanContent'

const STAGE_LABELS: Record<string, string> = {
  task_received: 'Task Received',
  planning: 'Planning',
  plan_review: 'Plan Review',
  developing: 'Developing',
  testing: 'Testing',
  creating_mr: 'Creating MR',
  pr_open: 'PR Open',
  completed: 'Completed',
}
const PLAN_STAGES = ['planning', 'plan_review']
const TEST_STAGES = ['testing']
const MR_STAGES = ['creating_mr', 'pr_open']

// Stages where the pipeline is actively processing (show Stop button)
const ACTIVE_STATUSES = ['task_received', 'planning', 'developing', 'creating_mr']
// Stages where a human must take action (gate stages)
const GATE_STATUSES = ['plan_review', 'testing']
const TERMINAL_STATUSES = ['completed', 'failed', 'closed']

export default function PipelineDetail() {
  const { runId } = useParams<{ runId: string }>()
  const [run, setRun] = useState<PipelineRun | null>(null)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [testResult, setTestResult] = useState<TR | null>(null)
  const [mr, setMR] = useState<MergeRequest | null>(null)
  const [loading, setLoading] = useState(true)
  const [stopping, setStopping] = useState(false)
  const [resuming, setResuming] = useState(false)
  const [planExpanded, setPlanExpanded] = useState(false)
  const [selectedStage, setSelectedStage] = useState<string | null>(null)
  const [descExpanded, setDescExpanded] = useState(false)
  const [diffFiles, setDiffFiles] = useState<DiffFile[]>([])
  const [diffSummary, setDiffSummary] = useState('')
  const [diffExpanded, setDiffExpanded] = useState(true)

  const fetchRun = useCallback(async () => {
    if (!runId) return
    try {
      const resp = await pipelineApi.get(runId)
      const r = resp.data
      setRun(r)
      if (r.plans?.length) setPlan(r.plans.sort((a, b) => b.version - a.version)[0])
      if (r.test_results?.length) setTestResult(r.test_results[r.test_results.length - 1])
      if (r.merge_requests?.length) setMR(r.merge_requests[r.merge_requests.length - 1])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [runId])

  useEffect(() => {
    fetchRun()
    const interval = setInterval(() => {
      // Stop polling once terminal — no more state changes expected
      if (run && TERMINAL_STATUSES.includes(run.status)) return
      fetchRun()
    }, 6000)
    return () => clearInterval(interval)
  }, [fetchRun, run?.status])

  useEffect(() => {
    if (run?.status === 'testing') {
      pipelineApi.getDiff(run.id).then(r => {
        setDiffFiles(r.data.files)
        setDiffSummary(r.data.summary)
      }).catch(() => {})
    }
  }, [run?.status, run?.id])

  const handleStop = async () => {
    if (!runId) return
    setStopping(true)
    try {
      await pipelineApi.cancel(runId)
      await fetchRun()
    } finally {
      setStopping(false)
    }
  }

  const handleResume = async () => {
    if (!runId) return
    setResuming(true)
    try {
      await pipelineApi.resume(runId)
      await fetchRun()
    } finally {
      setResuming(false)
    }
  }

  if (loading) return <div className="text-gray-400">Loading pipeline...</div>
  if (!run || !runId) return <div className="text-gray-400">Pipeline not found.</div>

  const isActive = ACTIVE_STATUSES.includes(run.status)
  const isGate = GATE_STATUSES.includes(run.status)
  const isTerminal = TERMINAL_STATUSES.includes(run.status)

  return (
    <div className="max-w-4xl">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-6">
        <div className="flex items-center gap-3">
          <Link to="/" className="text-gray-400 hover:text-gray-600">
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              {run.zoho_task_title || `Pipeline ${run.id.slice(0, 8)}`}
            </h1>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <StatusBadge status={run.status} />
              {run.zoho_task_number && (
                <span className="inline-flex items-center rounded-full bg-blue-50 border border-blue-200 px-2 py-0.5 text-xs font-mono font-medium text-blue-700">
                  #{run.zoho_task_number}
                </span>
              )}
              {run.zoho_task_id && (
                <span className="text-xs text-gray-400">ID: {run.zoho_task_id}</span>
              )}
              {run.feature_branch && (
                <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded text-gray-600">
                  {run.feature_branch}
                </code>
              )}
            </div>
            {run.zoho_task_description && (
              <div className="mt-2 max-w-2xl">
                <p className={`text-xs text-gray-500 leading-relaxed whitespace-pre-wrap ${descExpanded ? '' : 'line-clamp-2'}`}>
                  {run.zoho_task_description}
                </p>
                {run.zoho_task_description.length > 120 && (
                  <button
                    onClick={() => setDescExpanded(e => !e)}
                    className="text-xs text-indigo-500 hover:text-indigo-700 mt-0.5"
                  >
                    {descExpanded ? 'Show less' : 'Show more'}
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Control buttons */}
        <div className="flex gap-2 shrink-0">
          {(isActive || isGate) && (
            <button
              onClick={handleStop}
              disabled={stopping}
              className="flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-sm text-red-700 hover:bg-red-100 disabled:opacity-50"
            >
              <Square className="h-3.5 w-3.5 fill-current" />
              {stopping ? 'Stopping...' : 'Stop'}
            </button>
          )}
          {run.status === 'failed' && (
            <button
              onClick={handleResume}
              disabled={resuming}
              className="flex items-center gap-1.5 rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-sm text-blue-700 hover:bg-blue-100 disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${resuming ? 'animate-spin' : ''}`} />
              {resuming ? 'Restarting...' : 'Restart'}
            </button>
          )}
        </div>
      </div>

      {/* Stage tracker */}
      <div className="rounded-xl border bg-white p-5 mb-4">
        <PipelineStages
          currentStatus={run.status}
          currentStage={run.current_stage}
          onStageClick={(id) => setSelectedStage(prev => prev === id ? null : id)}
          selectedStage={selectedStage}
        />
        {selectedStage && (
          <p className="mt-2 text-xs text-indigo-500 text-center">
            Viewing history for <strong>{STAGE_LABELS[selectedStage]}</strong> — click again to dismiss
          </p>
        )}
      </div>

      {/* History panel for clicked past stage */}
      {selectedStage && (
        <div className="rounded-xl border border-indigo-200 bg-indigo-50 overflow-hidden mb-4">
          <div className="flex items-center justify-between px-5 py-3 border-b border-indigo-200">
            <span className="text-sm font-semibold text-indigo-800">
              {STAGE_LABELS[selectedStage]} — History
            </span>
            <button onClick={() => setSelectedStage(null)} className="text-indigo-400 hover:text-indigo-600">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="p-4">
            {PLAN_STAGES.includes(selectedStage) && plan ? (
              <PlanContent content={plan.content} />
            ) : PLAN_STAGES.includes(selectedStage) && !plan ? (
              <p className="text-sm text-gray-500">No plan available for this stage.</p>
            ) : TEST_STAGES.includes(selectedStage) && testResult ? (
              <TestResults runId={runId} result={testResult} onAction={fetchRun} readOnly />
            ) : TEST_STAGES.includes(selectedStage) && !testResult ? (
              <p className="text-sm text-gray-500">No test results available for this stage.</p>
            ) : MR_STAGES.includes(selectedStage) && mr ? (
              <div className="space-y-2 text-sm">
                <p><span className="text-gray-500">Title:</span> <span className="font-medium">{mr.title}</span></p>
                <p>
                  <span className="text-gray-500">Branch:</span>{' '}
                  <code className="text-xs bg-white px-1.5 py-0.5 rounded border">{mr.source_branch}</code>
                  {' → '}
                  <code className="text-xs bg-white px-1.5 py-0.5 rounded border">{mr.target_branch}</code>
                </p>
                <StatusBadge status={mr.status} />
                {mr.mr_url && (
                  <a href={mr.mr_url} target="_blank" rel="noreferrer"
                    className="flex items-center gap-1 text-blue-600 hover:underline">
                    <ExternalLink className="h-3.5 w-3.5" />
                    Open Pull Request
                  </a>
                )}
              </div>
            ) : MR_STAGES.includes(selectedStage) && !mr ? (
              <p className="text-sm text-gray-500">No merge request created yet.</p>
            ) : (
              <p className="text-sm text-gray-500">No detailed history available for this stage.</p>
            )}
          </div>
        </div>
      )}

      {/* Error */}
      {run.status === 'failed' && run.error_message && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 mb-4 text-sm text-red-700">
          <strong>Failed:</strong> {run.error_message}
        </div>
      )}

      {/* Action panels */}
      {run.status === 'plan_review' && plan && (
        <div className="mb-4">
          <PlanReview runId={runId} plan={plan} onAction={fetchRun} />
        </div>
      )}

      {/* Read-only plan for post-approval stages */}
      {!['plan_review', 'planning', 'task_received'].includes(run.status) && plan && (
        <div className="rounded-xl border bg-white overflow-hidden mb-4">
          <button
            onClick={() => setPlanExpanded(e => !e)}
            className="flex w-full items-center justify-between px-5 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            <span>Implementation Plan · v{plan.version}</span>
            {planExpanded ? <ChevronUp className="h-4 w-4 text-gray-400" /> : <ChevronDown className="h-4 w-4 text-gray-400" />}
          </button>
          {planExpanded && (
            <div className="px-5 pb-5 border-t">
              <PlanContent content={plan.content} />
            </div>
          )}
        </div>
      )}

      {/* Code Changes panel — shows uncommitted working-dir diff during testing */}
      {run.status === 'testing' && (
        <div className="rounded-xl border bg-white overflow-hidden mb-4">
          <button
            onClick={() => setDiffExpanded(e => !e)}
            className="flex w-full items-center justify-between px-5 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            <span className="flex items-center gap-2">
              <span>Code Changes</span>
              {diffSummary && <span className="text-xs text-gray-400 font-normal">{diffSummary}</span>}
            </span>
            {diffExpanded ? <ChevronUp className="h-4 w-4 text-gray-400" /> : <ChevronDown className="h-4 w-4 text-gray-400" />}
          </button>
          {diffExpanded && (
            <div className="border-t px-5 py-3">
              {diffFiles.length === 0 ? (
                <p className="text-xs text-gray-400">No changed files found.</p>
              ) : (
                <div className="space-y-1">
                  {diffFiles.map((f, i) => (
                    <div key={i} className="flex items-center justify-between text-xs font-mono">
                      <span className="text-gray-700 truncate flex-1">{f.path}</span>
                      <span className="ml-3 shrink-0">
                        {f.additions > 0 && <span className="text-green-600">+{f.additions}</span>}
                        {f.additions > 0 && f.deletions > 0 && <span className="text-gray-300 mx-1">/</span>}
                        {f.deletions > 0 && <span className="text-red-500">−{f.deletions}</span>}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Manual Testing gate — shown whenever run is in the testing stage */}
      {run.status === 'testing' && (
        <div className="mb-4">
          {testResult ? (
            <TestResults runId={runId} result={testResult} onAction={fetchRun} />
          ) : (
            <div className="rounded-xl border bg-white p-5">
              <div className="flex items-center gap-3">
                <div className="h-4 w-4 rounded-full border-2 border-blue-500 border-t-transparent animate-spin shrink-0" />
                <div>
                  <p className="font-medium text-gray-700">Setting up test scenarios…</p>
                  <p className="text-sm text-gray-500 mt-0.5">Extracting test cases from the plan, just a moment.</p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}


      {/* PR link — shown once the MR exists (creating_mr, completed, closed) */}
      {mr?.mr_url && (
        <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 mb-4 flex items-center justify-between gap-3">
          <div className="text-sm">
            <span className="font-medium text-indigo-800">Pull Request</span>
            {mr.source_branch && (
              <span className="ml-2 text-xs text-indigo-500">
                <code className="bg-white px-1.5 py-0.5 rounded border border-indigo-100">{mr.source_branch}</code>
                {mr.target_branch && <> → <code className="bg-white px-1.5 py-0.5 rounded border border-indigo-100">{mr.target_branch}</code></>}
              </span>
            )}
          </div>
          <a
            href={mr.mr_url}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 shrink-0"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Open PR
          </a>
        </div>
      )}

      {run.status === 'completed' && (
        <div className="rounded-xl border border-green-200 bg-green-50 p-4 mb-4 text-sm text-green-700 font-medium">
          Pipeline completed successfully!
        </div>
      )}

      {run.status === 'closed' && (
        <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 mb-4 text-sm text-gray-600">
          <strong>PR Closed.</strong> The pull request was closed without merging.
        </div>
      )}

      {/* Logs */}
      <div className="rounded-xl border bg-white p-5">
        <LogStream runId={runId} isActive={isActive} />
      </div>

      {/* Agent history */}
      {run.agent_runs && run.agent_runs.length > 0 && (
        <div className="rounded-xl border bg-white p-5 mt-4">
          <h3 className="font-semibold mb-3 text-sm">Agent History</h3>
          <div className="space-y-2">
            {run.agent_runs.map((a) => (
              <div key={a.id} className="flex items-center justify-between text-sm">
                <span className="font-mono text-gray-700">{a.agent_type}</span>
                <div className="flex items-center gap-3">
                  {a.started_at && (
                    <span className="text-xs text-gray-400">
                      {fmtTime(a.started_at)}
                    </span>
                  )}
                  <StatusBadge status={a.status} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
