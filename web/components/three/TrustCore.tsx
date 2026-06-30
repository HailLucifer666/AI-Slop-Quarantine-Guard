"use client"

import { Suspense } from "react"
import { Canvas } from "@react-three/fiber"
import { Icosahedron, OrbitControls } from "@react-three/drei"

/**
 * WebGL "trust core" — translucent aurora icosahedron + wireframe shell, slow auto-rotate.
 * Tone shifts with clean state (emerald = clean, indigo = findings). Capped DPR; reduced-motion
 * stops the spin. Imported dynamically with ssr:false (see dashboard page).
 */
export default function TrustCore({ clean = true }: { clean?: boolean }) {
  const prefersReduced =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches

  const color = clean ? "#2DE08A" : "#4A5BFF"

  return (
    <Canvas dpr={[1, 1.75]} camera={{ position: [0, 0, 4], fov: 45 }} aria-hidden>
      <ambientLight intensity={0.6} />
      <pointLight position={[5, 5, 5]} intensity={120} color="#16C8D4" />
      <pointLight position={[-5, -3, 2]} intensity={80} color={color} />
      <Suspense fallback={null}>
        {/* solid translucent core */}
        <Icosahedron args={[1.15, 1]}>
          <meshStandardMaterial
            color={color}
            emissive={color}
            emissiveIntensity={0.25}
            transparent
            opacity={0.35}
            roughness={0.2}
            metalness={0.6}
          />
        </Icosahedron>
        {/* wireframe shell */}
        <Icosahedron args={[1.45, 1]}>
          <meshBasicMaterial color="#16C8D4" wireframe transparent opacity={0.25} />
        </Icosahedron>
      </Suspense>
      <OrbitControls
        enableZoom={false}
        enablePan={false}
        autoRotate={!prefersReduced}
        autoRotateSpeed={0.8}
        enableRotate={false}
      />
    </Canvas>
  )
}
