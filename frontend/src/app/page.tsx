import Topbar from "@/components/Topbar"
import StatCard from "@/components/StatCard"
import Section from "@/components/Section"
import HealthPanel from "@/components/HealthPanel"

export default function HomePage() {
  return (
    <div className="flex flex-col gap-6">
      <Topbar />
      <div className="grid gap-4 md:grid-cols-3">
        <StatCard label="Active Experiments" value="3" delta="+1 today" />
        <StatCard label="Ideas Generated" value="12" delta="+4 this week" />
        <StatCard label="Artifacts" value="28" delta="Stable" />
      </div>
      <Section title="System Health" description="实时检查后端与依赖环境。">
        <HealthPanel />
      </Section>
      <Section
        title="Mission Control"
        description="Launch experiments, monitor progress, and synthesize results across your research pipeline."
      >
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-2xl border border-slate-800 bg-slate-950 p-5">
            <div className="text-sm text-slate-400">Idea Engine</div>
            <div className="mt-2 text-lg font-semibold">Refine and expand research ideas</div>
            <div className="mt-3 text-sm text-slate-400">
              Use structured templates to turn a topic into high quality research directions.
            </div>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-950 p-5">
            <div className="text-sm text-slate-400">Experiment Lab</div>
            <div className="mt-2 text-lg font-semibold">Plan, run, and review experiments</div>
            <div className="mt-3 text-sm text-slate-400">
              Track execution status and artifacts in real time.
            </div>
          </div>
        </div>
      </Section>
      <Section title="Agent Workflow Status" description="Track each stage of the research lifecycle.">
        <div className="grid gap-4 md:grid-cols-4">
          {[
            {
              title: "Idea Generation",
              icon: "💡",
              tasks: [
                { title: "Generate Research Topic", status: "completed" },
                { title: "Literature Review", status: "in_progress" }
              ]
            },
            {
              title: "Code Execution",
              icon: "⚙️",
              tasks: [{ title: "Setup Sandbox", status: "pending" }]
            },
            {
              title: "Review & Eval",
              icon: "🧐",
              tasks: [{ title: "Feasibility Check", status: "pending" }]
            },
            {
              title: "Paper Writing",
              icon: "📝",
              tasks: [{ title: "Draft Introduction", status: "pending" }]
            }
          ].map((stage) => (
            <div key={stage.title} className="rounded-2xl border border-slate-800 bg-slate-950 p-4">
              <div className="text-sm text-slate-300">
                {stage.icon} {stage.title}
              </div>
              <div className="mt-3 space-y-2">
                {stage.tasks.map((task) => (
                  <div
                    key={task.title}
                    className={`rounded-xl border px-3 py-2 text-xs ${
                      task.status === "completed"
                        ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                        : task.status === "in_progress"
                          ? "border-amber-500/30 bg-amber-500/10 text-amber-300"
                          : "border-slate-700 bg-slate-900 text-slate-300"
                    }`}
                  >
                    {task.title}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Section>
    </div>
  )
}
