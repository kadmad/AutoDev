import { Check, Clock, AlertCircle, Pause } from 'lucide-react'

const STAGES = [
  { id: 'task_received', label: 'Task Received' },
  { id: 'planning', label: 'Planning' },
  { id: 'plan_review', label: 'Plan Review', gate: true },
  { id: 'developing', label: 'Developing' },
  { id: 'testing', label: 'Testing', gate: true },
  { id: 'creating_mr', label: 'Creating MR' },
  { id: 'pr_open', label: 'PR Open', gate: true },
  { id: 'completed', label: 'Completed' },
]

const STAGE_ORDER = STAGES.map((s) => s.id)

interface Props {
  currentStatus: string   // run.status — used for failed/completed detection
  currentStage?: string   // run.current_stage — used for stage position (falls back to currentStatus)
  onStageClick?: (id: string) => void
  selectedStage?: string | null
}

export default function PipelineStages({ currentStatus, currentStage, onStageClick, selectedStage }: Props) {
  const stageId = currentStage ?? currentStatus
  const currentIndex = STAGE_ORDER.indexOf(stageId)
  const isFailed = currentStatus === 'failed' || currentStatus === 'closed'
  const isAllDone = currentStatus === 'completed'

  return (
    <div className="flex items-center gap-1 overflow-x-auto py-2">
      {STAGES.map((stage, i) => {
        const stageIndex = STAGE_ORDER.indexOf(stage.id)
        const isDone = isAllDone || (currentIndex > stageIndex)
        const isCurrent = !isAllDone && stageId === stage.id
        const isFuture = !isAllDone && !isFailed && stageIndex > currentIndex
        const isSelected = selectedStage === stage.id

        const circle = (
          <div
            className={`flex h-8 w-8 items-center justify-center rounded-full border-2 transition-all ${
              isSelected
                ? 'border-indigo-500 bg-indigo-100 ring-2 ring-indigo-300'
                : isFailed && isCurrent
                ? 'border-red-500 bg-red-100'
                : isDone
                ? 'border-green-500 bg-green-500'
                : isCurrent
                ? stage.gate
                  ? 'border-orange-500 bg-orange-100'
                  : 'border-blue-500 bg-blue-100'
                : 'border-gray-300 bg-white'
            }`}
          >
            {isFailed && isCurrent ? (
              <AlertCircle className="h-4 w-4 text-red-500" />
            ) : isDone ? (
              <Check className={`h-4 w-4 ${isSelected ? 'text-indigo-600' : 'text-white'}`} />
            ) : isCurrent ? (
              stage.gate ? (
                <Pause className="h-4 w-4 text-orange-500" />
              ) : (
                <Clock className="h-4 w-4 text-blue-500 animate-spin" />
              )
            ) : (
              <span className="text-xs text-gray-400">{i + 1}</span>
            )}
          </div>
        )

        return (
          <div key={stage.id} className="flex items-center gap-1">
            <div
              className={`flex flex-col items-center min-w-[80px] ${
                isFuture ? 'opacity-40' : ''
              }`}
            >
              {(isDone || isCurrent) && onStageClick ? (
                <button
                  onClick={() => onStageClick(stage.id)}
                  className="focus:outline-none"
                  title={`View ${stage.label} details`}
                >
                  {circle}
                </button>
              ) : (
                circle
              )}
              <span className={`mt-1 text-center text-xs leading-tight ${isSelected ? 'text-indigo-600 font-medium' : ''}`}>
                {stage.label}
              </span>
            </div>
            {i < STAGES.length - 1 && (
              <div
                className={`h-0.5 w-4 flex-shrink-0 ${
                  isDone ? 'bg-green-500' : 'bg-gray-200'
                }`}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
