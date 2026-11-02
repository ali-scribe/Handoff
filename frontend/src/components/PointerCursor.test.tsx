import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PointerCursor from "./PointerCursor";

afterEach(() => {
  document.body.classList.remove("showcase-pointer-active");
  window.getSelection()?.removeAllRanges();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  // @ts-expect-error allow clearing the stub between tests
  window.matchMedia = undefined;
});

function stubMatchMedia(reducedMotion: boolean, coarsePointer: boolean) {
  vi.stubGlobal("PointerEvent", class extends Event {});
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes("prefers-reduced-motion")
      ? reducedMotion
      : query.includes("pointer: coarse")
        ? coarsePointer
        : false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
    onchange: null,
  })) as unknown as typeof window.matchMedia;
}

function movePointer(target: EventTarget, options: { x?: number; y?: number } = {}) {
  const event = new Event("pointermove", { bubbles: true });
  Object.assign(event, {
    pointerType: "mouse",
    clientX: options.x ?? 0,
    clientY: options.y ?? 0,
  });
  act(() => target.dispatchEvent(event));
}

describe("PointerCursor", () => {
  it("uses the Showcase Pointer arrow at the real pointer position", () => {
    stubMatchMedia(false, false);
    const { container } = render(<PointerCursor />);

    expect(container.querySelector(".pointer-cursor-live")).not.toBeInTheDocument();
    movePointer(document, { x: 123, y: 234 });

    const cursor = container.querySelector(".pointer-cursor-live");
    expect(cursor).toBeInTheDocument();
    expect(cursor).toHaveStyle({
      pointerEvents: "none",
      "--showcase-pointer-cursor-scale": "0.7",
      "--cursor-x": "123px",
      "--cursor-y": "234px",
    });
    expect(cursor?.querySelector(".showcase-pointer-cursor-arrow")).toHaveAttribute(
      "viewBox",
      "0 0 24 24",
    );
    expect(cursor?.querySelectorAll(".showcase-pointer-cursor-arrow-fill")).toHaveLength(1);
    expect(document.body).toHaveClass("showcase-pointer-active");
  });

  it.each([
    ["reduced motion", true, false],
    ["coarse pointers", false, true],
  ])("keeps the native cursor for %s", (_condition, reducedMotion, coarsePointer) => {
    stubMatchMedia(reducedMotion, coarsePointer);
    const { container } = render(<PointerCursor />);
    movePointer(document, { x: 30, y: 40 });

    expect(container.querySelector(".pointer-cursor-live")).not.toBeInTheDocument();
    expect(document.body).not.toHaveClass("showcase-pointer-active");
  });

  it("restores the native I-beam over editable fields", () => {
    stubMatchMedia(false, false);
    render(
      <>
        <PointerCursor />
        <textarea aria-label="Work request" />
      </>,
    );
    movePointer(document, { x: 30, y: 40 });
    expect(document.body).toHaveClass("showcase-pointer-active");

    movePointer(screen.getByRole("textbox"), { x: 50, y: 60 });
    expect(document.querySelector(".pointer-cursor-live")).not.toBeInTheDocument();
    expect(document.body).not.toHaveClass("showcase-pointer-active");
  });

  it("does not suppress clicks or prevent text selection", () => {
    stubMatchMedia(false, false);
    const onClick = vi.fn();
    render(
      <>
        <PointerCursor />
        <p>Selectable text</p>
        <button onClick={onClick}>Action</button>
      </>,
    );
    const text = screen.getByText("Selectable text");
    movePointer(text, { x: 75, y: 80 });

    const range = document.createRange();
    range.selectNodeContents(text);
    window.getSelection()?.addRange(range);
    movePointer(text, { x: 90, y: 80 });
    expect(window.getSelection()?.toString()).toBe("Selectable text");

    const click = fireEvent.click(screen.getByRole("button"));
    expect(click).toBe(true);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("applies and clears the cursor press state", () => {
    stubMatchMedia(false, false);
    const { container } = render(<PointerCursor />);
    movePointer(document, { x: 75, y: 80 });
    const cursor = container.querySelector(".pointer-cursor-live");
    expect(cursor).toBeInTheDocument();

    fireEvent.pointerDown(document);
    expect(cursor).toHaveAttribute("data-pressed");
    fireEvent.pointerUp(document);
    expect(cursor).not.toHaveAttribute("data-pressed");
  });

  it("restores the native cursor when pointer events are unavailable", () => {
    stubMatchMedia(false, false);
    vi.stubGlobal("PointerEvent", undefined);
    const { container } = render(<PointerCursor />);
    movePointer(document, { x: 30, y: 40 });

    expect(container.querySelector(".pointer-cursor-live")).not.toBeInTheDocument();
    expect(document.body).not.toHaveClass("showcase-pointer-active");
  });

  it("keeps the native cursor when matchMedia is unavailable", () => {
    vi.stubGlobal("PointerEvent", class extends Event {});
    // @ts-expect-error simulate a browser without matchMedia
    window.matchMedia = undefined;
    const { container } = render(<PointerCursor />);
    movePointer(document, { x: 30, y: 40 });

    expect(container.querySelector(".pointer-cursor-live")).not.toBeInTheDocument();
    expect(document.body).not.toHaveClass("showcase-pointer-active");
  });

  it("restores the native cursor when reduced motion is enabled", () => {
    let reducedMotion = false;
    const listeners = new Map<string, (() => void)[]>();
    vi.stubGlobal("PointerEvent", class extends Event {});
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      get matches() {
        return query.includes("prefers-reduced-motion") && reducedMotion;
      },
      media: query,
      addEventListener: (type: string, callback: () => void) => {
        listeners.set(type, [...(listeners.get(type) ?? []), callback]);
      },
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
      onchange: null,
    })) as unknown as typeof window.matchMedia;
    const { container } = render(<PointerCursor />);
    movePointer(document, { x: 30, y: 40 });
    expect(container.querySelector(".pointer-cursor-live")).toBeInTheDocument();

    reducedMotion = true;
    act(() => listeners.get("change")?.forEach((listener) => listener()));
    expect(container.querySelector(".pointer-cursor-live")).not.toBeInTheDocument();
    expect(document.body).not.toHaveClass("showcase-pointer-active");
  });
});
