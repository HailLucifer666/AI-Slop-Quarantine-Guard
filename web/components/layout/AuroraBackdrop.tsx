/**
 * Ambient aurora glow behind the whole app — low-opacity radial blobs in the
 * brand ramp, slowly drifting. Pure CSS (no WebGL); fixed, non-interactive,
 * behind everything. Reduced-motion freezes the drift (handled in globals.css).
 */
export function AuroraBackdrop() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-bg"
    >
      <div
        className="absolute -left-[10%] -top-[15%] h-[55vh] w-[55vh] rounded-full blur-[120px] animate-aurora-drift"
        style={{ background: "radial-gradient(circle, rgba(74,91,255,0.22), transparent 70%)" }}
      />
      <div
        className="absolute right-[-5%] top-[10%] h-[50vh] w-[50vh] rounded-full blur-[120px] animate-aurora-drift"
        style={{
          background: "radial-gradient(circle, rgba(22,200,212,0.16), transparent 70%)",
          animationDelay: "-8s",
        }}
      />
      <div
        className="absolute bottom-[-20%] left-[30%] h-[55vh] w-[55vh] rounded-full blur-[140px] animate-aurora-drift"
        style={{
          background: "radial-gradient(circle, rgba(45,224,138,0.14), transparent 70%)",
          animationDelay: "-16s",
        }}
      />
      {/* subtle vignette so content stays legible over the glow */}
      <div
        className="absolute inset-0"
        style={{ background: "radial-gradient(ellipse at center, transparent 40%, rgba(6,8,10,0.7) 100%)" }}
      />
    </div>
  )
}
