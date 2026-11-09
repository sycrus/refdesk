import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./generated/tokens.css";
import "./base.css";
import { applyAppearance, storedAppearance } from "./theme";

applyAppearance(storedAppearance()); // before the first paint, so a forced theme never flashes

const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root element");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
