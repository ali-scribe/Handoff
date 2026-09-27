import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import InteractiveBackground from "./InteractiveBackground";

afterEach(() => {
  vi.restoreAllMocks();
  // @ts-expect-error allow clearing the stub between tests
  window.matchMedia = undefined;
});

/** Stub matchMedia to control the reduced-motion branch. */
function stubMatchMedia(reduce: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes("reduce") ? reduce : false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
    onchange: null,
  })) as unknown as typeof window.matchMedia;
}

describe("InteractiveBackground", () => {
  it("renders a decorative, aria-hidden layer", () => {
    stubMatchMedia(false);
    const { container } = render(<InteractiveBackground />);
    const layer = container.querySelector(".interactive-bg");
    expect(layer).not.toBeNull();
    expect(layer).toHaveAttribute("aria-hidden", "true");
  });

  it("registers passive pointer listeners and cleans them up on unmount", () => {
    stubMatchMedia(false);
    const rafSpy = vi
      .spyOn(window, "requestAnimationFrame")
      .mockReturnValue(1 as unknown as number);
    const cancelSpy = vi
      .spyOn(window, "cancelAnimationFrame")
      .mockImplementation(() => {});
    const addSpy = vi.spyOn(window, "addEventListener");
    const removeSpy = vi.spyOn(window, "removeEventListener");

    const { unmount } = render(<InteractiveBackground />);
    expect(addSpy).toHaveBeenCalledWith(
      "pointermove",
      expect.any(Function),
      expect.objectContaining({ passive: true }),
    );

    unmount();
    expect(removeSpy).toHaveBeenCalledWith("pointermove", expect.any(Function));
    expect(cancelSpy).toHaveBeenCalled();
    rafSpy.mockRestore();
  });

  it("does not attach listeners when reduced motion is preferred", () => {
    stubMatchMedia(true);
    const addSpy = vi.spyOn(window, "addEventListener");
    render(<InteractiveBackground />);
    const pointerCalls = addSpy.mock.calls.filter((c) =>
      String(c[0]).startsWith("pointer"),
    );
    expect(pointerCalls).toHaveLength(0);
  });
});
