// Whether the app runs against the public demo (ADR-025). Screens read it to stop
// offering actions the demo API refuses; the API is still what enforces read-only.
import { createContext, useContext } from "react";

export const DemoContext = createContext(false);

export function useDemo(): boolean {
  return useContext(DemoContext);
}
