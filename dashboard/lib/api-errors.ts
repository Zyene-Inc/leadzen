/** Network failures, rate limits and server errors may clear on retry; 4xx denials do not. */
export const transientError = (caught: unknown) =>
  caught instanceof TypeError || (caught instanceof Error && "status" in caught && typeof caught.status === "number" && (caught.status === 429 || caught.status >= 500));
