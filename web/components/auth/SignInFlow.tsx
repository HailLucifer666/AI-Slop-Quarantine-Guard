"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { AnimatePresence, motion } from "framer-motion"
import { ArrowRight, Check, Chrome } from "lucide-react"

import { AUTH_ENABLED, SKIP_KEY, supabase } from "@/lib/auth"
import { cn } from "@/lib/utils"

type Step = "email" | "code" | "success"

/** Enter/exit timings from the merged motion tokens (300ms in, ~65% out). */
const EASE_ENTER: [number, number, number, number] = [0.22, 1, 0.36, 1]
const EASE_EXIT: [number, number, number, number] = [0.55, 0, 1, 0.45]

/**
 * Developer sign-in flow (email → 6-digit code → success), Command Wall tokens.
 * Auth is OPTIONAL: with Supabase configured the steps call OTP / OAuth; without
 * it, the flow advances in demo mode. "Skip for now" always works.
 */
export function SignInFlow() {
  const router = useRouter()
  const [step, setStep] = useState<Step>("email")
  const [email, setEmail] = useState("")
  const [code, setCode] = useState(["", "", "", "", "", ""])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const codeRefs = useRef<(HTMLInputElement | null)[]>([])

  const goDashboard = () => router.push("/dashboard")

  const skip = () => {
    if (typeof window !== "undefined") localStorage.setItem(SKIP_KEY, "1")
    goDashboard()
  }

  const submitEmail = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email) return
    setError(null)
    if (AUTH_ENABLED && supabase) {
      setBusy(true)
      const { error } = await supabase.auth.signInWithOtp({
        email,
        options: { shouldCreateUser: true },
      })
      setBusy(false)
      if (error) return setError(error.message)
    }
    setStep("code")
  }

  const googleSignIn = async () => {
    if (!AUTH_ENABLED || !supabase) return
    setError(null)
    setBusy(true)
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: `${window.location.origin}/dashboard` },
      })
      if (error) setError(error.message)
    } finally {
      setBusy(false)
    }
  }

  const onCodeChange = (i: number, v: string) => {
    if (v.length > 1) return
    const next = [...code]
    next[i] = v
    setCode(next)
    if (v && i < 5) codeRefs.current[i + 1]?.focus()
  }

  const onCodeKey = (i: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !code[i] && i > 0) codeRefs.current[i - 1]?.focus()
  }

  const verify = async () => {
    if (!code.every((d) => d !== "")) return
    setError(null)
    if (AUTH_ENABLED && supabase) {
      setBusy(true)
      const { error } = await supabase.auth.verifyOtp({
        email,
        token: code.join(""),
        type: "email",
      })
      setBusy(false)
      if (error) return setError(error.message)
    } else if (typeof window !== "undefined") {
      // Demo mode (no Supabase): remember so the dashboard doesn't bounce back.
      localStorage.setItem(SKIP_KEY, "1")
    }
    setStep("success")
  }

  useEffect(() => {
    if (step === "code") setTimeout(() => codeRefs.current[0]?.focus(), 400)
    if (step === "success") {
      const t = setTimeout(goDashboard, 1600)
      return () => clearTimeout(t)
    }
  }, [step]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="relative z-10 w-full max-w-sm">
      <AnimatePresence mode="wait">
        {step === "email" && (
          <motion.div
            key="email"
            initial={{ opacity: 0, x: -40 }}
            animate={{ opacity: 1, x: 0, transition: { duration: 0.3, ease: EASE_ENTER } }}
            exit={{ opacity: 0, x: -40, transition: { duration: 0.2, ease: EASE_EXIT } }}
            className="space-y-6 text-center"
          >
            <div className="space-y-1">
              <h1 className="font-display text-3xl font-bold tracking-tight text-text">
                Welcome Developer
              </h1>
              <p className="text-lg text-text-muted">Sign in to your quality gate</p>
            </div>

            <div className="space-y-4">
              <button
                onClick={googleSignIn}
                disabled={!AUTH_ENABLED || busy}
                className="wall-focus flex w-full items-center justify-center gap-2 rounded-md py-3 text-text transition-colors disabled:cursor-not-allowed disabled:opacity-40"
                style={{ background: "var(--surface)", border: "1px solid var(--line-strong)" }}
                title={AUTH_ENABLED ? "" : "Connect Supabase to enable Google sign-in"}
              >
                <Chrome className="h-[18px] w-[18px]" aria-hidden />
                <span>Sign in with Google</span>
              </button>

              <div className="flex items-center gap-4">
                <div className="h-px flex-1 bg-line" />
                <span className="text-sm text-text-faint">or</span>
                <div className="h-px flex-1 bg-line" />
              </div>

              <form onSubmit={submitEmail}>
                <div className="relative">
                  <input
                    type="email"
                    placeholder="you@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    className="wall-focus min-h-[44px] w-full rounded-md px-4 py-3 text-center text-md text-text outline-none placeholder:text-text-faint"
                    style={{ background: "var(--surface)", border: "1px solid var(--line-strong)" }}
                  />
                  <button
                    type="submit"
                    disabled={busy}
                    aria-label="Continue"
                    className="wall-focus absolute right-1.5 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-md bg-brand-gradient transition-transform hover:scale-105 disabled:opacity-50"
                    style={{ color: "var(--on-accent)" }}
                  >
                    <ArrowRight className="h-4 w-4" aria-hidden />
                  </button>
                </div>
              </form>

              {error && <p role="alert" className="text-sm text-sev-certain">{error}</p>}
            </div>

            <button
              onClick={skip}
              className="wall-focus inline-flex min-h-[44px] items-center rounded-md text-sm text-text-muted underline-offset-4 transition-colors hover:text-text hover:underline"
            >
              Skip for now (demo) →
            </button>
          </motion.div>
        )}

        {step === "code" && (
          <motion.div
            key="code"
            initial={{ opacity: 0, x: 40 }}
            animate={{ opacity: 1, x: 0, transition: { duration: 0.3, ease: EASE_ENTER } }}
            exit={{ opacity: 0, x: 40, transition: { duration: 0.2, ease: EASE_EXIT } }}
            className="space-y-6 text-center"
          >
            <div className="space-y-1">
              <h1 className="font-display text-3xl font-bold tracking-tight text-text">
                We sent you a code
              </h1>
              <p className="text-lg text-text-muted">Enter the 6-digit code sent to {email}</p>
            </div>

            <div
              className="flex items-center justify-center gap-2 rounded-md px-4 py-2"
              style={{ border: "1px solid var(--line-strong)", background: "var(--surface)" }}
            >
              {code.map((digit, i) => (
                <input
                  key={i}
                  ref={(el) => {
                    codeRefs.current[i] = el
                  }}
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={1}
                  value={digit}
                  onChange={(e) => onCodeChange(i, e.target.value)}
                  onKeyDown={(e) => onCodeKey(i, e)}
                  aria-label={`Digit ${i + 1}`}
                  className="wall-focus h-[44px] w-11 rounded-md bg-transparent text-center font-mono text-xl text-text outline-none"
                />
              ))}
            </div>

            {error && <p role="alert" className="text-sm text-sev-certain">{error}</p>}

            <div className="flex gap-3">
              <button onClick={() => setStep("email")} className="wall-cta-secondary">
                Back
              </button>
              <button
                onClick={verify}
                disabled={busy || !code.every((d) => d !== "")}
                className="wall-cta flex-1"
              >
                Continue
              </button>
            </div>
          </motion.div>
        )}

        {step === "success" && (
          <motion.div
            key="success"
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0, transition: { duration: 0.3, ease: EASE_ENTER } }}
            exit={{ opacity: 0, y: 20, transition: { duration: 0.2, ease: EASE_EXIT } }}
            className="space-y-6 text-center"
          >
            <h1 className="font-display text-3xl font-bold tracking-tight text-text">You&apos;re in!</h1>
            <p className="text-lg text-text-muted">Taking you to your dashboard…</p>
            <motion.div
              initial={{ scale: 0.7, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 0.2, duration: 0.3, ease: EASE_ENTER }}
              className={cn(
                "mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-brand-gradient",
              )}
              style={{ color: "var(--on-accent)" }}
            >
              <Check className="h-8 w-8" aria-hidden />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
