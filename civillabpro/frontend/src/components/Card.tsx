import type { ReactNode } from "react";

export function Card({ title, action, children, className = "" }: { title?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-md border border-[var(--clp-border)] bg-[var(--clp-panel)] ${className}`}>
      {title && (
        <header className="flex items-center h-9 px-3 border-b border-[var(--clp-border)]">
          <h2 className="m-0 text-[12.5px] font-semibold">{title}</h2>
          <div className="ml-auto flex items-center gap-1">{action}</div>
        </header>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end gap-3 mb-4">
      <div className="min-w-0">
        <h1 className="m-0 text-lg font-semibold tracking-tight truncate">{title}</h1>
        {subtitle && <p className="m-0 mt-0.5 text-[var(--clp-ink-2)]">{subtitle}</p>}
      </div>
      <div className="ml-auto flex items-center gap-2">{children}</div>
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="px-6 py-10 text-center">
      <div className="font-semibold">{title}</div>
      <div className="mt-1 text-[var(--clp-ink-2)] flex flex-col items-center gap-3">{children}</div>
    </div>
  );
}
