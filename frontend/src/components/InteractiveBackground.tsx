import { useEffect, useRef } from "react";

/**
 * A subtle, interactive enhancement of the page's dot-pattern background.
 *
 * Renders a single fixed, full-viewport, non-interactive layer that paints the
 * same dot grid in a slightly stronger indigo/lavender tint, revealed only near
 * the pointer through a soft radial mask. As the pointer moves, dots near it
 * become slightly brighter/tinted and shift by ≤2px; everything eases back to
 * rest when the pointer is idle or leaves.
 *
 * Performance: pointer data is written to CSS custom properties via a ref inside
 * a single requestAnimationFrame loop — NEVER through React state — so the
 * React tree does not re-render on pointer movement. Listeners are passive (so
 * scrolling/typing/clicks are never blocked) and cleaned up on unmount.
 *
 * Accessibility: the whole interaction is disabled under
 * `prefers-reduced-motion: reduce`; the layer is decorative (aria-hidden,
 * pointer-events:none) and never required to use the app.
 */
function InteractiveBackground() {
  const layerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const layer = layerRef.current;
    if (!layer) return;

    // Respect reduced-motion: no listeners, no animation loop at all.
    const reduce =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;

    // Target values (updated on pointer events) and current values (eased each
    // frame). Kept in plain refs/locals — no allocations per event, no React
    // state.
    let targetX = window.innerWidth / 2;
    let targetY = window.innerHeight / 2;
    let curX = targetX;
    let curY = targetY;
    let targetStrength = 0;
    let curStrength = 0;
    let lastActivity = 0;
    let rafId = 0;

    const setActivity = (x: number, y: number, strength: number) => {
      targetX = x;
      targetY = y;
      targetStrength = strength;
      lastActivity = performance.now();
    };

    const onPointerMove = (e: PointerEvent) => {
      // Touch: brief localized response (decays quickly, below) so continuous
      // dragging never fights with scrolling. Mouse/pen: sustained follow.
      setActivity(e.clientX, e.clientY, 1);
    };
    const onPointerDown = (e: PointerEvent) => {
      setActivity(e.clientX, e.clientY, 1);
    };
    const onPointerLeave = () => {
      targetStrength = 0;
    };

    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("pointerdown", onPointerDown, { passive: true });
    window.addEventListener("pointerout", onPointerLeave, { passive: true });

    const tick = () => {
      const now = performance.now();
      // Idle decay: if no activity for a moment, ease the influence away. This
      // also gives touch a "brief localized response" rather than a sticky one.
      if (now - lastActivity > 320) {
        targetStrength = 0;
      }

      // Smooth interpolation (frame-rate-independent-ish easing factors).
      curX += (targetX - curX) * 0.18;
      curY += (targetY - curY) * 0.18;
      curStrength += (targetStrength - curStrength) * 0.09;

      // Write high-frequency values as CSS variables on the layer only.
      layer.style.setProperty("--px", curX.toFixed(1) + "px");
      layer.style.setProperty("--py", curY.toFixed(1) + "px");
      layer.style.setProperty("--interact", curStrength.toFixed(3));

      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("pointerout", onPointerLeave);
    };
  }, []);

  return <div ref={layerRef} className="interactive-bg" aria-hidden="true" />;
}

export default InteractiveBackground;
