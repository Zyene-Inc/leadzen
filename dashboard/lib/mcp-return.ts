/** Preserve only the MCP consent path through sign-in; never an arbitrary redirect. */
export function safeMcpReturnPath(value: string | null | undefined): string | null {
  if (!value || value.length > 256) return null;
  try {
    const url = new URL(value, "https://leadzen.invalid");
    if (url.origin !== "https://leadzen.invalid" || !value.startsWith("/mcp/connect?") || url.pathname !== "/mcp/connect" || url.hash) return null;
    const request = url.searchParams.get("request");
    if (!request || !/^[a-zA-Z0-9_-]{20,100}$|^[a-f0-9-]{36}$/.test(request) || [...url.searchParams.keys()].some(key => key !== "request") || url.searchParams.getAll("request").length !== 1) return null;
    return `/mcp/connect?request=${encodeURIComponent(request)}`;
  } catch {
    return null;
  }
}
