/**
 * Env-guarded Supabase client. Auth is OPTIONAL: if the two public env vars
 * aren't set, `supabase` is null and `AUTH_ENABLED` is false — the app then
 * runs fully open (demo mode). The moment real keys are pasted into
 * `.env.local`, OTP + Google sign-in activate with no code changes.
 *
 *   NEXT_PUBLIC_SUPABASE_URL=...
 *   NEXT_PUBLIC_SUPABASE_ANON_KEY=...
 */
import { createClient, type SupabaseClient } from "@supabase/supabase-js"

const url = process.env.NEXT_PUBLIC_SUPABASE_URL
const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

export const supabase: SupabaseClient | null = url && key ? createClient(url, key) : null
export const AUTH_ENABLED = supabase !== null

/** localStorage flag set by the "Skip for now (demo)" button. */
export const SKIP_KEY = "sqg-auth-skip"
