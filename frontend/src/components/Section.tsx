import { ReactNode } from "react"

type SectionProps = {
  title: string
  description?: string
  children: ReactNode
}

export default function Section({ title, description, children }: SectionProps) {
  return (
    <section className="rounded-none border border-border bg-card p-6">
      <div className="mb-6">
        <div className="text-lg font-semibold text-foreground">{title}</div>
        {description ? (
          <div className="text-sm text-muted-foreground">{description}</div>
        ) : null}
      </div>
      {children}
    </section>
  )
}
