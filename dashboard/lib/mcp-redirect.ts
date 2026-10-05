/** Defense in depth: only navigate to the callback host the API validated. */
export function validatedMcpRedirect(value: string, host: string): string | null {
  try {
    const url = new URL(value);
    const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
    if (url.username || url.password || url.hash || url.host.toLowerCase() !== host.toLowerCase()) return null;
    if (url.protocol !== "https:" && !(url.protocol === "http:" && loopback)) return null;
    return url.href;
  } catch {
    return null;
  }
}

export function returnToMcpClient(destination: string) {
  window.location.assign(destination);
}
