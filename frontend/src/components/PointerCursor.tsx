import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";

import "./reactdrops/showcase-pointer/showcase-pointer.css";

const ACTIVE_CLASS = "showcase-pointer-active";
const EDITABLE_TARGET =
  'textarea, input:not([type]), input[type="text"], input[type="search"], input[type="email"], input[type="url"], input[type="tel"], input[type="password"], input[type="number"], [contenteditable="true"], [contenteditable=""]';

type PointerPosition = { x: number; y: number };

function supportsCustomCursor() {
  if (
    typeof window === "undefined" ||
    typeof window.matchMedia !== "function" ||
    typeof window.PointerEvent === "undefined"
  ) {
    return false;
  }
  return (
    !window.matchMedia("(prefers-reduced-motion: reduce)").matches &&
    !window.matchMedia("(pointer: coarse)").matches
  );
}

function PointerCursor() {
  const [enabled, setEnabled] = useState(supportsCustomCursor);
  const [active, setActive] = useState(false);
  const cursorRef = useRef<HTMLDivElement>(null);
  const positionRef = useRef<PointerPosition>({ x: 0, y: 0 });

  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      setEnabled(false);
      return;
    }

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const coarsePointer = window.matchMedia("(pointer: coarse)");
    const update = () => {
      const supported =
        typeof window.PointerEvent !== "undefined" &&
        !reducedMotion.matches &&
        !coarsePointer.matches;
      setEnabled(supported);
      if (!supported) {
        setActive(false);
        document.body.classList.remove(ACTIVE_CLASS);
      }
    };

    update();
    reducedMotion.addEventListener("change", update);
    coarsePointer.addEventListener("change", update);
    return () => {
      reducedMotion.removeEventListener("change", update);
      coarsePointer.removeEventListener("change", update);
      document.body.classList.remove(ACTIVE_CLASS);
    };
  }, []);

  useLayoutEffect(() => {
    if (!active || !enabled) {
      document.body.classList.remove(ACTIVE_CLASS);
      return;
    }

    const cursor = cursorRef.current;
    if (!cursor) return;
    cursor.style.setProperty("--cursor-x", `${positionRef.current.x}px`);
    cursor.style.setProperty("--cursor-y", `${positionRef.current.y}px`);
    document.body.classList.add(ACTIVE_CLASS);
  }, [active, enabled]);

  useEffect(() => {
    if (!enabled) return;

    const deactivate = () => {
      document.body.classList.remove(ACTIVE_CLASS);
      setActive(false);
    };
    const move = (event: PointerEvent) => {
      const target = event.target;
      if (
        event.pointerType !== "mouse" ||
        (target instanceof Element && target.closest(EDITABLE_TARGET))
      ) {
        deactivate();
        return;
      }

      positionRef.current = { x: event.clientX, y: event.clientY };
      const cursor = cursorRef.current;
      if (cursor) {
        cursor.style.setProperty("--cursor-x", `${event.clientX}px`);
        cursor.style.setProperty("--cursor-y", `${event.clientY}px`);
      }
      setActive(true);
    };
    const press = () => cursorRef.current?.setAttribute("data-pressed", "");
    const release = () => cursorRef.current?.removeAttribute("data-pressed");

    document.addEventListener("pointermove", move);
    document.addEventListener("pointerdown", press);
    document.addEventListener("pointerup", release);
    document.addEventListener("pointercancel", release);
    window.addEventListener("blur", deactivate);
    return () => {
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerdown", press);
      document.removeEventListener("pointerup", release);
      document.removeEventListener("pointercancel", release);
      window.removeEventListener("blur", deactivate);
    };
  }, [enabled]);

  if (!active || !enabled) return null;

  return (
    <div
      ref={cursorRef}
      className="showcase-pointer-cursor pointer-cursor-live"
      aria-hidden="true"
      style={
        {
          pointerEvents: "none",
          "--showcase-pointer-cursor-color": "var(--color-accent)",
          "--showcase-pointer-cursor-scale": 0.7,
        } as CSSProperties
      }
    >
      <div className="showcase-pointer-cursor-body">
        <svg
          className="showcase-pointer-cursor-arrow"
          viewBox="0 0 24 24"
          width="28"
          height="28"
        >
          <path
            className="showcase-pointer-cursor-arrow-edge"
            d="M4.2 3.3 20.1 9.6 13.3 12.3 10.6 19.2Z"
          />
          <path
            className="showcase-pointer-cursor-arrow-fill"
            d="M4.2 3.3 20.1 9.6 13.3 12.3 10.6 19.2Z"
          />
        </svg>
      </div>
    </div>
  );
}

export default PointerCursor;
