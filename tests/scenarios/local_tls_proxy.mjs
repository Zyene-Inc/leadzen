// Loopback-only test proxy for the production frontend's HTTPS backend guard.
// Pass a disposable certificate/key; trust the certificate in that Node process
// using NODE_EXTRA_CA_CERTS. Never disable TLS validation or install a system CA.
import { readFileSync } from "node:fs";
import http from "node:http";
import https from "node:https";

const [certificatePath, keyPath] = process.argv.slice(2);
if (!certificatePath || !keyPath) {
  throw new Error("Usage: node local_tls_proxy.mjs CERTIFICATE_PATH KEY_PATH");
}

const server = https.createServer(
  { cert: readFileSync(certificatePath), key: readFileSync(keyPath) },
  (request, response) => {
    const upstream = http.request(
      { hostname: "127.0.0.1", port: 8000, path: request.url, method: request.method,
        headers: { ...request.headers, host: "127.0.0.1:8000" }, timeout: 30000 },
      (result) => {
        response.writeHead(result.statusCode ?? 502, result.headers);
        result.pipe(response);
      },
    );
    upstream.on("timeout", () => upstream.destroy(new Error("Preview API timeout")));
    upstream.on("error", () => {
      if (!response.headersSent) response.writeHead(502, { "Content-Type": "text/plain" });
      response.end("Local preview API is unavailable.");
    });
    request.on("aborted", () => upstream.destroy());
    response.on("close", () => upstream.destroy());
    request.pipe(upstream);
  },
);

server.listen(8443, "127.0.0.1", () => {
  console.log("LeadZen local backend TLS proxy: https://127.0.0.1:8443");
});
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
