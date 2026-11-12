// vitest/jsdom 25 does not expose matchMedia by default; polyfill it so
// useReducedMotion() can hydrate without throwing. Reduced motion is false here,
// meaning components render their animated defaults — fine for these DOM tests.
Object.defineProperty(globalThis, "matchMedia", {
  writable: true,
  configurable: true,
  value: ((media: string) => ({
    matches: false,
    media,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  })) as unknown as MediaQueryList,
})
