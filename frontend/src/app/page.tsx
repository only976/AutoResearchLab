import Link from "next/link"
import Section from "@/components/Section"
import HealthPanel from "@/components/HealthPanel"
import { Lightbulb, FlaskConical, FileText } from "lucide-react"

export default function HomePage() {
  return (
    <div className="flex flex-col gap-6">
      <Section title="System Health" description="检查后端与依赖环境">
        <HealthPanel />
      </Section>
      <Section title="Quick Links" description="快速进入各功能模块">
        <div className="grid gap-4 md:grid-cols-3">
          <Link href="/ideas" className="rounded-2xl border border-slate-800 bg-slate-950 p-5 hover:border-slate-600 transition-colors">
            <Lightbulb className="h-6 w-6 text-slate-400 mb-2" />
            <div className="font-semibold">Ideas</div>
            <div className="text-sm text-slate-400">生成与细化研究选题</div>
          </Link>
          <Link href="/experiments" className="rounded-2xl border border-slate-800 bg-slate-950 p-5 hover:border-slate-600 transition-colors">
            <FlaskConical className="h-6 w-6 text-slate-400 mb-2" />
            <div className="font-semibold">Experiments</div>
            <div className="text-sm text-slate-400">MAARS 实验规划与执行</div>
          </Link>
          <Link href="/paper" className="rounded-2xl border border-slate-800 bg-slate-950 p-5 hover:border-slate-600 transition-colors">
            <FileText className="h-6 w-6 text-slate-400 mb-2" />
            <div className="font-semibold">Paper</div>
            <div className="text-sm text-slate-400">论文草稿撰写</div>
          </Link>
        </div>
      </Section>
    </div>
  )
}
