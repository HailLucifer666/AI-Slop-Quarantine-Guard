import * as React from "react"
import { cn } from "@/lib/utils"

/**
 * Aurora badge. Same call shape the supplied snippets expect
 * (`<Badge variant="destructive">`), recolored to Aurora tokens.
 * `destructive` is kept as an alias of the severity-certain look.
 */
type Variant =
  | "default"
  | "neutral"
  | "alert"
  | "destructive"
  | "clean"
  | "scan"
  | "outline"
  | "secondary"

const VARIANTS: Record<Variant, string> = {
  default: "border-transparent bg-surface-elevated text-text",
  neutral: "border-border bg-surface text-text-muted",
  alert: "border-transparent bg-sev-certain/15 text-sev-certain",
  destructive: "border-transparent bg-sev-certain text-bg",
  clean: "border-transparent bg-sev-clean/15 text-sev-clean",
  scan: "border-transparent bg-scan/15 text-scan",
  outline: "border-border text-text",
  secondary: "border-transparent bg-surface text-text-muted",
}

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: Variant
}

function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors",
        VARIANTS[variant],
        className,
      )}
      {...props}
    />
  )
}

export { Badge }
