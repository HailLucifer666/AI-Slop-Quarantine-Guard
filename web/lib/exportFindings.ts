import type { ScanDetail } from "./types"
import { checkName, CONFIDENCE_ORDER } from "./checks"
import { shortRef } from "./format"

/**
 * Consolidate every finding in a scan into one structured, AI-ready Markdown
 * prompt. The user copies it and pastes it into their AI assistant to fix all
 * the issues at once — instead of hunting file-by-file.
 *
 * Honest by construction: each finding is tagged block-eligible (provable) vs
 * advisory so the assistant sees true priority and nothing is inflated.
 */
export function buildFixPrompt(scan: ScanDetail): string {
  const total = scan.findings.length
  const blockEligible = scan.findings.filter((f) => f.block_eligible).length
  const advisory = total - blockEligible
  const filesScanned = scan.analytics?.files_scanned ?? scan.files_scanned
  const skipped = scan.files_skipped > 0 ? ` · ${scan.files_skipped} file(s) skipped (not analyzed — some findings may be missing)` : ""

  const out: string[] = []
  out.push(`# Code-scan findings — ${shortRef(scan.ref)} (scan #${scan.id})`)
  out.push(`${total} finding${total === 1 ? "" : "s"} · ${blockEligible} block-eligible (provable) · ${advisory} advisory · ${filesScanned} files scanned${skipped}`)
  out.push("")
  out.push(
    "Fix each issue below with the smallest change that resolves it; if you can't fix one, say why. " +
      "Block-eligible items are provable facts and the highest priority; advisory items are lower-confidence — review before changing.",
  )
  out.push("")

  const ordered = [...scan.findings].sort(
    (a, b) => CONFIDENCE_ORDER.indexOf(a.confidence) - CONFIDENCE_ORDER.indexOf(b.confidence),
  )

  ordered.forEach((f, i) => {
    const tag = f.block_eligible ? `${f.confidence} · block-eligible` : `${f.confidence} · advisory`
    out.push(`### ${i + 1}. [${tag}] ${f.rule_id} — ${checkName(f.rule_id)}`)
    const loc =
      f.line_end && f.line_end !== f.line_start
        ? `${f.file_path}:${f.line_start}-${f.line_end}`
        : `${f.file_path}:${f.line_start}`
    out.push(`- File: \`${loc}\``)
    out.push(`- Problem: ${f.message}`)
    const snippet = f.evidence?.snippet?.trim()
    if (snippet) {
      out.push("- Code:")
      out.push("```")
      out.push(snippet)
      out.push("```")
    }
    if (f.fix_suggestion) out.push(`- Suggested fix: ${f.fix_suggestion}`)
    out.push("")
  })

  return out.join("\n")
}
