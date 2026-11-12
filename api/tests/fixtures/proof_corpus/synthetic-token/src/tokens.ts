// Positive fixture: a token whose value self-identifies as fake.
//
// Scan #20 (openai/codex-security, 2026-11-12) fired CERTAIN / block-eligible on a
// literal github_pat_SYNTHETIC_... fixture token. The value-internal marker check
// must surface this as an advisory and never as a block.

export const demoToken = "github_pat_SYNTHETIC_GITHUB_PAT_123";
