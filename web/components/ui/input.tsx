import * as React from "react"
import { cn } from "@/lib/utils"

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "min-h-[44px] w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text",
        "placeholder:text-text-faint focus-visible:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-indigo",
        className,
      )}
      {...props}
    />
  ),
)
Input.displayName = "Input"
