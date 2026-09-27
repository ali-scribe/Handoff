import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import Header from "./Header";

const STORAGE_KEY = "handoff-theme";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

describe("Header theme toggle", () => {
  it("renders the toggle with an accessible label", () => {
    render(<Header />);
    // No stored preference and no matchMedia in jsdom -> defaults to light,
    // so the toggle offers switching to dark.
    expect(
      screen.getByRole("button", { name: /switch to dark mode/i }),
    ).toBeInTheDocument();
  });

  it("applies the light theme to the document by default", () => {
    render(<Header />);
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("toggles between light and dark, updating label and document + storage", () => {
    render(<Header />);
    const toggle = screen.getByRole("button", { name: /switch to dark mode/i });

    fireEvent.click(toggle);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("dark");
    // Label now offers switching back to light.
    expect(
      screen.getByRole("button", { name: /switch to light mode/i }),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /switch to light mode/i }),
    );
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("light");
  });

  it("respects a stored dark preference on mount", () => {
    localStorage.setItem(STORAGE_KEY, "dark");
    render(<Header />);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(
      screen.getByRole("button", { name: /switch to light mode/i }),
    ).toBeInTheDocument();
  });

  it("still renders the brand title", () => {
    render(<Header />);
    expect(
      screen.getByRole("heading", { name: "Handoff" }),
    ).toBeInTheDocument();
  });
});
