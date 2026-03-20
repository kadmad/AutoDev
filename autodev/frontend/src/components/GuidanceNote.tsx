import { Info } from 'lucide-react'

interface Props {
  title: string
  children: React.ReactNode
}

export default function GuidanceNote({ title, children }: Props) {
  return (
    <div className="flex gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">
      <Info className="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <p className="font-semibold">{title}</p>
        <div className="mt-1 space-y-1">{children}</div>
      </div>
    </div>
  )
}
