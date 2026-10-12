// Scaffold only (issue #41). Page styles come from the design tokens (#42, base.css);
// never hardcode colours. Screens S1 to S3 arrive in #46.
import { useEffect, useState } from "react";

type ApiState = { kind: "checking" } | { kind: "up" } | { kind: "down"; reason: string };

export function App() {
  const [api, setApi] = useState<ApiState>({ kind: "checking" });

  useEffect(() => {
    fetch("/healthz")
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const body: { status: string } = await response.json();
        if (body.status !== "ok") throw new Error(`status ${body.status}`);
        setApi({ kind: "up" });
      })
      .catch((error: unknown) => setApi({ kind: "down", reason: String(error) }));
  }, []);

  return (
    <main>
      <h1>refdesk</h1>
      <p role="status">
        {api.kind === "checking" && "Checking the API…"}
        {api.kind === "up" && "API reachable."}
        {api.kind === "down" && `API not reachable: ${api.reason}`}
      </p>
    </main>
  );
}
