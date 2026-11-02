import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Analytics } from "@vercel/analytics/react";
import App from "./App";
import InteractiveBackground from "./components/InteractiveBackground";
import PointerCursor from "./components/PointerCursor";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <InteractiveBackground />
    <PointerCursor />
    <App />
    <Analytics />
  </StrictMode>
);