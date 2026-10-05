export type TourRect = { left: number; top: number; right: number; bottom: number; width: number; height: number };
export type TourPlacement = "right" | "bottom" | "top" | "left";
export type TourViewport = { width: number; height: number; left?: number; top?: number };

/** Native modal dialogs make the rest of body inert; keep their guide inside. */
export function tourPortalRoot(target?: HTMLElement | null): HTMLElement | null {
  if (typeof document === "undefined") return null;
  const containingDialog = target?.closest<HTMLDialogElement>("dialog[open]");
  if (containingDialog) return containingDialog;
  try { return document.querySelector<HTMLDialogElement>("dialog:modal") ?? document.body; }
  catch { return document.body; }
}

/** Place within the visible viewport, including the mobile keyboard viewport. */
export function placeTooltip(anchor: TourRect, box: { width: number; height: number }, viewport: TourViewport, preferred: TourPlacement = "bottom") {
  const margin = 12, gap = 14;
  const x = viewport.left ?? 0, y = viewport.top ?? 0;
  const width = Math.min(box.width, Math.max(0, viewport.width - margin * 2));
  const height = Math.min(box.height, Math.max(0, viewport.height - margin * 2));
  const spaces = { bottom: y + viewport.height - anchor.bottom, top: anchor.top - y, right: x + viewport.width - anchor.right, left: anchor.left - x };
  const fits = (side: TourPlacement) => spaces[side] >= (side === "left" || side === "right" ? width : height) + gap + margin;
  const ordered: TourPlacement[] = [preferred, "bottom", "top", "right", "left"];
  const side = ordered.find(fits) ?? [...ordered].sort((a, b) => spaces[b] - spaces[a])[0];
  let left = anchor.left + (anchor.width - width) / 2;
  let top = side === "top" ? anchor.top - height - gap : anchor.bottom + gap;
  if (side === "right" || side === "left") {
    left = side === "right" ? anchor.right + gap : anchor.left - width - gap;
    top = anchor.top + (anchor.height - height) / 2;
  }
  return { left: Math.max(x + margin, Math.min(left, x + viewport.width - width - margin)), top: Math.max(y + margin, Math.min(top, y + viewport.height - height - margin)), side };
}

export function visibleTourElement(selector: string): HTMLElement | null {
  const elements = document.querySelectorAll<HTMLElement>(selector);
  for (const element of elements) {
    const style = window.getComputedStyle(element);
    if (!element.isConnected || element.hidden || style.display === "none" || style.visibility === "hidden" || !element.getClientRects().length) continue;
    if (element.closest('[inert], [aria-hidden="true"], [aria-busy="true"]')) continue;
    if (element.matches(":disabled")) continue;
    return element;
  }
  return null;
}

/** DOM-driven readiness. The timer is a safety bound, never a progression clock. */
function waitFor<T>(read: () => T | null, signal: AbortSignal, timeout: number): Promise<T> {
  return new Promise((resolve, reject) => {
    let settled = false;
    let observer: MutationObserver | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const cleanup = () => {
      observer?.disconnect(); clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      window.removeEventListener("resize", check);
      window.removeEventListener("popstate", check);
      document.removeEventListener("transitionend", check, true);
    };
    function abort() { if (settled) return; settled = true; cleanup(); reject(new DOMException("Tour wait cancelled", "AbortError")); }
    function check() {
      if (settled) return;
      const value = read();
      if (value !== null) { settled = true; cleanup(); resolve(value); }
    }
    if (signal.aborted) { abort(); return; }
    observer = new MutationObserver(check);
    observer.observe(document.body, { childList: true, subtree: true, attributes: true });
    signal.addEventListener("abort", abort, { once: true });
    window.addEventListener("resize", check);
    window.addEventListener("popstate", check);
    document.addEventListener("transitionend", check, true);
    timer = setTimeout(() => { if (settled) return; settled = true; cleanup(); reject(new Error("This part of the page is not available yet.")); }, timeout);
    check();
  });
}

export function waitForTourElement(selector: string, signal: AbortSignal, timeout = 10000) {
  return waitFor(() => visibleTourElement(selector), signal, timeout);
}

export function waitForTourCondition(condition: { success?: string; absent?: string; route?: string }, signal: AbortSignal, timeout = 10000) {
  return waitFor(() => {
    if (condition.route && window.location.pathname !== condition.route) return null;
    if (condition.success && !visibleTourElement(condition.success)) return null;
    if (condition.absent && visibleTourElement(condition.absent)) return null;
    return true;
  }, signal, timeout).then(() => {});
}

/** After scrolling/rendering, wait for geometry to settle, then a short reading beat. */
export function settleTourTarget(element: HTMLElement, signal: AbortSignal, reducedMotion: boolean): Promise<void> {
  return new Promise((resolve, reject) => {
    let frame = 0, beat: ReturnType<typeof setTimeout> | undefined;
    let previous = "", stable = 0, frames = 0;
    const cleanup = () => { cancelAnimationFrame(frame); clearTimeout(beat); signal.removeEventListener("abort", abort); };
    function abort() { cleanup(); reject(new DOMException("Tour wait cancelled", "AbortError")); }
    function tick() {
      if (signal.aborted || !element.isConnected) { abort(); return; }
      const rect = element.getBoundingClientRect();
      const position = `${Math.round(rect.left)},${Math.round(rect.top)},${Math.round(rect.width)},${Math.round(rect.height)}`;
      stable = position === previous ? stable + 1 : 0;
      previous = position; frames++;
      if (stable >= 3 || frames >= 90) {
        beat = setTimeout(() => {
          if (!element.isConnected) { abort(); return; }
          cleanup(); resolve();
        }, reducedMotion ? 0 : 350);
      } else frame = requestAnimationFrame(tick);
    }
    if (signal.aborted) { abort(); return; }
    signal.addEventListener("abort", abort, { once: true });
    frame = requestAnimationFrame(tick);
  });
}
