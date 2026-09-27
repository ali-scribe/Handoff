import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import InteractiveBackground from "./components/InteractiveBackground";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <InteractiveBackground />
    <App />
  </StrictMode>
);
