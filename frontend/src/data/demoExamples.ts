/**
 * Pre-baked demo request texts for the input screen.
 *
 * These are INPUTS ONLY. Each example is loaded into the existing textarea and
 * goes through the exact same pipeline as user input (Analyze → AI extraction →
 * deterministic validation → results → clarification → ready). Nothing here
 * pre-computes or hard-codes a readiness result, issues, or questions — the real
 * backend determines all of that. The titles/descriptions only hint at what an
 * example is designed to demonstrate.
 */

export interface DemoExample {
  id: string;
  title: string;
  description: string;
  text: string;
}

export const DEMO_EXAMPLES: DemoExample[] = [
  {
    id: "incomplete",
    title: "Incomplete request",
    description: "Missing key details — see what Handoff asks for.",
    text: "Please prepare the final presentation for our database project and make it look professional. Add the important parts from our project and have it ready soon.",
  },
  {
    id: "ambiguous",
    title: "Ambiguous request",
    description: "Has structure but vague language to clarify.",
    text: "Update the student portal before Friday. Use the latest design and make the dashboard easier to use. Keep the important existing features and make sure everything works properly.",
  },
  {
    id: "ready",
    title: "Ready request",
    description: "Concrete and complete — the successful path.",
    text: "Update the student portal dashboard for the Spring semester. Sara will implement the changes using the existing React frontend in the student-portal repository. Replace the current dashboard cards with the approved Spring semester design in Figma, keep the existing navigation and authentication behavior unchanged, and make the page responsive for desktop and mobile. The final output should be the updated dashboard committed to the repository. Complete it by September 30, 2026. The implementation is accepted when all existing dashboard tests pass, the approved Figma layout is matched, desktop and mobile layouts work correctly, and no existing navigation or authentication behavior is broken.",
  },
];
