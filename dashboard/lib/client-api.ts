import { notifyWorkspaceUpdated } from "@/lib/workspace-updates";
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/proxy/${path}`, {
    ...init,
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401) window.location.assign("/login");
    if (payload.redirect === "/onboarding" || payload.redirect === "/password")
      window.location.assign(payload.redirect);
    throw new Error(payload.error ?? "Request failed. Please try again.");
  }
  const result = (await response.json()) as T;
  if (init?.method && !["GET", "HEAD"].includes(init.method.toUpperCase()) && !path.startsWith("chat/") && path !== "tour") notifyWorkspaceUpdated();
  return result;
}
