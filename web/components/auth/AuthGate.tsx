"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { AUTH_ENABLED, SKIP_KEY, supabase } from "@/lib/auth"

/**
 * Client gate for the authenticated app shell. Order of checks:
 *  1. "Skip for demo" flag in localStorage → allow.
 *  2. Supabase configured → require a live session, else redirect to /login.
 *  3. Supabase NOT configured → allow (open demo build).
 * Renders nothing until the check resolves, to avoid a flash of gated content.
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const [ok, setOk] = useState(false)

  useEffect(() => {
    let active = true

    const allow = () => active && setOk(true)
    const deny = () => active && router.replace("/login")

    if (typeof window !== "undefined" && localStorage.getItem(SKIP_KEY) === "1") {
      allow()
      return
    }
    // No Supabase configured → open demo build: allow straight through. The boot
    // splash on "/" is the entry experience; there is no password/OTP step.
    if (!AUTH_ENABLED || !supabase) {
      allow()
      return
    }
    // Subscribe BEFORE getSession so an OAuth-redirect SIGNED_IN isn't lost to a
    // premature deny(). The listener also fires the current session immediately
    // (INITIAL_SESSION) and on every later change — including SIGNED_OUT / expiry,
    // which must boot the user back to /login.
    let resolved = false
    const { data: sub } = supabase.auth.onAuthStateChange((_e, session) => {
      resolved = true
      if (session) allow()
      else deny()
    })
    supabase.auth
      .getSession()
      .then(({ data }) => {
        if (resolved) return // listener already settled it
        if (data.session) allow()
        else deny()
      })
      .catch(deny)
    return () => {
      active = false
      sub.subscription.unsubscribe()
    }
  }, [router])

  if (!ok) return null
  return <>{children}</>
}
