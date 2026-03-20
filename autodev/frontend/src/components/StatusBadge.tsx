const STATUS_STYLES: Record<string, string> = {
  task_received: 'bg-gray-100 text-gray-700',
  planning: 'bg-yellow-100 text-yellow-700',
  plan_review: 'bg-orange-100 text-orange-700',
  developing: 'bg-blue-100 text-blue-700',
  testing: 'bg-orange-100 text-orange-700',
  creating_mr: 'bg-blue-100 text-blue-700',
  mr_open: 'bg-indigo-100 text-indigo-700',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
  running: 'bg-blue-100 text-blue-700',
  pending: 'bg-gray-100 text-gray-500',
  open: 'bg-indigo-100 text-indigo-700',
  merged: 'bg-green-100 text-green-700',
  closed: 'bg-red-100 text-red-700',
}

export default function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] || 'bg-gray-100 text-gray-700'
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}
