import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../generated/tokens.css";
import "../base.css";
import { DesignLibrary } from "./DesignLibrary";

const root = document.getElementById("root");
if (!root) throw new Error("design/index.html has no #root element");

createRoot(root).render(
  <StrictMode>
    <DesignLibrary />
  </StrictMode>,
);
