import * as React from "react"
import { cn } from "@/lib/utils"

type Variant = "primary" | "outline" | "ghost"

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand-gradient text-bg font-semibold shadow-glow hover:opacity-95",
  outline: "border border-border-strong bg-surface text-text hover:bg-surface-elevated",
  ghost: "text-text-muted hover:bg-surface hover:text-text",
}

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex min-h-[44px] items-center justify-center gap-2 rounded-md px-4 py-2 text-sm transition-all",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-indigo disabled:pointer-events-none disabled:opacity-50",
        VARIANTS[variant],
        className,
      )}
      {...props}
    />
  ),
)
Button.displayName = "Button"
