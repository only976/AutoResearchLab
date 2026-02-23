import { ReactNode } from "react"

type SectionProps = {
  title: string
  description?: string
  children: ReactNode
}

export default function Section({ title, description, children }: SectionProps) {
  return (
    <section className="rounded-3xl border border-slate-800 bg-panel p-6">
      <div className="mb-6">
        <div className="text-lg font-semibold text-white">{title}</div>
        {description ? (
          <div className="text-sm text-slate-400">{description}</div>
        ) : null}
      </div>
      {children}
    </section>
  )
}
