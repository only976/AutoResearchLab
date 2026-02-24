export default function Topbar() {
  return (
    <div className="flex items-center justify-between rounded-2xl border border-slate-800 bg-panel px-6 py-4">
      <div>
        <div className="text-sm text-slate-400">Welcome back</div>
        <div className="text-lg font-semibold text-white">Research Control Center</div>
      </div>
      <div className="flex items-center gap-2 rounded-full border border-slate-700 bg-slate-950 px-4 py-2 text-xs text-slate-300">
        <span className="h-2 w-2 rounded-full bg-emerald-400" />
        System Online
      </div>
    </div>
  )
}
