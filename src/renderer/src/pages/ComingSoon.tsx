export function ComingSoon({ title, phase }: { title: string; phase: number }) {
  return (
    <div className="empty-view">
      <h1>{title}</h1>
      <p className="muted">This module is built in Phase {phase}. The plan is in docs/ARCHITECTURE.md.</p>
    </div>
  )
}
