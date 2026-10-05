import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import type { ReactNode } from "react";
vi.mock("next/link", () => ({ default: ({ children, ...props }: { children: ReactNode; href: string }) => <a {...props}>{children}</a> }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/components/sidebar", () => ({ Sidebar: () => <aside>Navigation</aside> }));
vi.mock("@/lib/client-api", () => ({ api: vi.fn() }));
vi.mock("@/lib/workspace-context", () => ({ useWorkspaceContext: () => {}, recordWorkspaceContext: vi.fn(async () => {}), flushWorkspaceContext: vi.fn(async () => {}) }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
