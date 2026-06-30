"use client"

/** Top chrome — just the reference's hairline scanline + a faint live indicator. */
export function WallChrome({ live }: { live: boolean }) {
  return (
    <header className="relative shrink-0">
      <div className="wall-hairline" />
      <div
        className="pointer-events-none absolute right-3 top-2 flex items-center gap-1.5 text-[10px] uppercase tracking-wide"
        style={{ color: "var(--wall-faint)" }}
      >
        <span
          className={live ? "h-1.5 w-1.5 animate-pulse rounded-full" : "h-1.5 w-1.5 rounded-full"}
          style={{ background: live ? "var(--wall-green)" : "var(--wall-faint)" }}
          aria-hidden
        />
        {live ? "Live" : "Offline"}
      </div>
    </header>
  )
}
