// Test-only gateway. It exposes a disposable fixture and one loopback Next server.
// Never point it at customer data or install its certificate in a system trust store.
import http from "node:http";
import https from "node:https";
import { readFileSync } from "node:fs";

const port = Number(process.env.LEADZEN_E2E_GATEWAY_PORT || "3150");
const dashboardPort = Number(process.env.LEADZEN_E2E_DASHBOARD_PORT || "3151");
const backendPort = Number(process.env.LEADZEN_E2E_BACKEND_PORT || "8150");
if (![port, dashboardPort, backendPort].every((value) => Number.isInteger(value) && value >= 1024 && value <= 65535 && ![8000, 3001].includes(value))) {
  throw new Error("Separate, nonprivileged fixture ports are required");
}
if (!process.env.LEADZEN_E2E_ORIGIN_FILE || !process.env.LEADZEN_E2E_CA_FILE) throw new Error("Private fixture origin and CA files are required");
const backendAgent = new https.Agent({ ca: readFileSync(process.env.LEADZEN_E2E_CA_FILE), rejectUnauthorized: true });
const server = http.createServer((request, response) => {
  let origin;
  try {
    origin = new URL(readFileSync(process.env.LEADZEN_E2E_ORIGIN_FILE, "utf8").trim());
    if (origin.protocol !== "https:" || origin.username || origin.password || origin.pathname !== "/" || origin.search || origin.hash) throw new Error();
  } catch {
    response.writeHead(503, { "Cache-Control": "private, no-store" }).end("Fixture origin is not ready");
    return;
  }
  const status = request.url === "/__e2e/status";
  if (status && request.method !== "GET") { response.writeHead(405).end(); return; }
  const headers = { ...request.headers, host: status ? "127.0.0.1" : origin.host, "x-forwarded-host": origin.host, "x-forwarded-proto": "https" };
  delete headers["forwarded"];
  const upstream = (status ? https : http).request({ hostname: "127.0.0.1", port: status ? backendPort : dashboardPort, path: request.url, method: request.method, headers, ...(status ? { agent: backendAgent } : {}) }, (incoming) => {
    // Cloudflare's default email obfuscation rewrites hydration HTML and injects
    // an unnonced script. Preserve the candidate bytes and its original CSP.
    incoming.headers["cache-control"] = `${incoming.headers["cache-control"] || "private, no-store"}, no-transform`;
    response.writeHead(incoming.statusCode || 502, incoming.headers);
    incoming.pipe(response);
  });
  upstream.setTimeout(80_000, () => upstream.destroy(new Error("Fixture upstream timeout")));
  upstream.on("error", () => { if (!response.headersSent) response.writeHead(502, { "Cache-Control": "private, no-store" }); response.end("Fixture upstream unavailable"); });
  request.on("aborted", () => upstream.destroy());
  response.on("close", () => { if (!response.writableEnded) upstream.destroy(); });
  request.pipe(upstream);
});
server.listen(port, "127.0.0.1", () => console.log("Disposable browser gateway ready on loopback"));
