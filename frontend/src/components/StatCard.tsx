type StatCardProps = {
  label: string
  value: string
  delta?: string
}

export default function StatCard({ label, value, delta }: StatCardProps) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-panel px-5 py-4">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-white">{value}</div>
      {delta ? (
        <div className="mt-2 text-xs text-emerald-400">{delta}</div>
      ) : null}
    </div>
  )
}
