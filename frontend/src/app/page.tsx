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
          <Link href="/ideas" className="rounded-md border border-border bg-card p-5 hover:border-primary/50 transition-colors">
            <Lightbulb className="h-6 w-6 text-muted-foreground mb-2" />
            <div className="font-semibold text-foreground">Ideas</div>
            <div className="text-sm text-muted-foreground">生成与细化研究选题</div>
          </Link>
          <Link href="/experiments" className="rounded-md border border-border bg-card p-5 hover:border-primary/50 transition-colors">
            <FlaskConical className="h-6 w-6 text-muted-foreground mb-2" />
            <div className="font-semibold text-foreground">Experiments</div>
            <div className="text-sm text-muted-foreground">MAARS 实验规划与执行</div>
          </Link>
          <Link href="/paper" className="rounded-md border border-border bg-card p-5 hover:border-primary/50 transition-colors">
            <FileText className="h-6 w-6 text-muted-foreground mb-2" />
            <div className="font-semibold text-foreground">Paper</div>
            <div className="text-sm text-muted-foreground">论文草稿撰写</div>
          </Link>
        </div>
      </Section>
    </div>
  )
}
