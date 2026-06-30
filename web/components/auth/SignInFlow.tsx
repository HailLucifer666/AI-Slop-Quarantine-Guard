"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { AnimatePresence, motion } from "framer-motion"
import { ArrowRight, Check } from "lucide-react"

import { Button } from "@/components/ui/button"
import { AUTH_ENABLED, SKIP_KEY, supabase } from "@/lib/auth"
import { cn } from "@/lib/utils"

type Step = "email" | "code" | "success"

/**
 * Developer sign-in flow (email → 6-digit code → success), Aurora-styled.
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
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -40 }}
            transition={{ duration: 0.35, ease: "easeOut" }}
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
                className="flex w-full items-center justify-center gap-2 rounded-full border border-border bg-surface/60 py-3 text-text backdrop-blur transition-colors hover:bg-surface-elevated disabled:cursor-not-allowed disabled:opacity-40"
                title={AUTH_ENABLED ? "" : "Connect Supabase to enable Google sign-in"}
              >
                <span className="font-display text-lg">G</span>
                <span>Sign in with Google</span>
              </button>

              <div className="flex items-center gap-4">
                <div className="h-px flex-1 bg-border" />
                <span className="text-sm text-text-faint">or</span>
                <div className="h-px flex-1 bg-border" />
              </div>

              <form onSubmit={submitEmail}>
                <div className="relative">
                  <input
                    type="email"
                    placeholder="you@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    className="w-full rounded-full border border-border bg-surface/60 px-4 py-3 text-center text-text backdrop-blur placeholder:text-text-faint focus:border-brand-indigo focus:outline-none focus:ring-2 focus:ring-brand-indigo/40"
                  />
                  <button
                    type="submit"
                    disabled={busy}
                    aria-label="Continue"
                    className="absolute right-1.5 top-1.5 flex h-9 w-9 items-center justify-center rounded-full bg-brand-gradient text-bg transition-transform hover:scale-105 disabled:opacity-50"
                  >
                    <ArrowRight className="h-4 w-4" />
                  </button>
                </div>
              </form>

              {error && <p className="text-sm text-sev-certain">{error}</p>}
            </div>

            <button
              onClick={skip}
              className="text-sm text-text-muted underline-offset-4 transition-colors hover:text-text hover:underline"
            >
              Skip for now (demo) →
            </button>
          </motion.div>
        )}

        {step === "code" && (
          <motion.div
            key="code"
            initial={{ opacity: 0, x: 40 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 40 }}
            transition={{ duration: 0.35, ease: "easeOut" }}
            className="space-y-6 text-center"
          >
            <div className="space-y-1">
              <h1 className="font-display text-3xl font-bold tracking-tight text-text">
                We sent you a code
              </h1>
              <p className="text-lg text-text-muted">Enter the 6-digit code sent to {email}</p>
            </div>

            <div className="flex items-center justify-center gap-2 rounded-full border border-border bg-surface/60 px-4 py-4 backdrop-blur">
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
                  className="w-8 bg-transparent text-center text-xl text-text focus:outline-none"
                />
              ))}
            </div>

            {error && <p className="text-sm text-sev-certain">{error}</p>}

            <div className="flex gap-3">
              <Button variant="outline" className="rounded-full" onClick={() => setStep("email")}>
                Back
              </Button>
              <Button
                className="flex-1 rounded-full"
                onClick={verify}
                disabled={busy || !code.every((d) => d !== "")}
              >
                Continue
              </Button>
            </div>
          </motion.div>
        )}

        {step === "success" && (
          <motion.div
            key="success"
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: "easeOut" }}
            className="space-y-6 text-center"
          >
            <h1 className="font-display text-3xl font-bold tracking-tight text-text">You&apos;re in!</h1>
            <p className="text-lg text-text-muted">Taking you to your dashboard…</p>
            <motion.div
              initial={{ scale: 0.7, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 0.2, duration: 0.4 }}
              className={cn(
                "mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-brand-gradient",
              )}
            >
              <Check className="h-8 w-8 text-bg" />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
