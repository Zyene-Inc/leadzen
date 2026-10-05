import "server-only";

export class RequestBodyError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

/** Bound bytes while reading, including chunked bodies without Content-Length. */
export async function readRequestBody(request: Request, limit: number): Promise<string> {
  const declared = request.headers.get("content-length");
  if (declared && /^\d+$/.test(declared) && Number(declared) > limit) throw new RequestBodyError("Request too large", 413);
  if (!request.body) return "";
  const reader = request.body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let bytes = 0;
  let body = "";
  let finished = false;
  let timeout: ReturnType<typeof setTimeout> | undefined;
  const deadline = new Promise<never>((_, reject) => {
    timeout = setTimeout(() => reject(new RequestBodyError("Request body timed out", 408)), 15000);
  });
  try {
    while (true) {
      const { done, value } = await Promise.race([reader.read(), deadline]);
      if (done) { finished = true; return body + decoder.decode(); }
      bytes += value.byteLength;
      if (bytes > limit) throw new RequestBodyError("Request too large", 413);
      body += decoder.decode(value, { stream: true });
    }
  } catch (error) {
    if (error instanceof RequestBodyError) throw error;
    throw new RequestBodyError("Invalid request body", 400);
  } finally {
    clearTimeout(timeout);
    if (!finished) void reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
