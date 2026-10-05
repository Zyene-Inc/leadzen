"use client";

import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { usePathname, useRouter } from "next/navigation";
import type { Account } from "@/lib/auth";
import { api } from "@/lib/client-api";
import { productTourSteps } from "@/lib/product-tour-steps";
import { placeTooltip, settleTourTarget, tourPortalRoot, visibleTourElement, waitForTourCondition, waitForTourElement, type TourRect, type TourViewport } from "@/lib/product-tour-dom";
import { readPendingTour, storeTour, tourIsActive, type ProductTourState, type TourAction } from "@/lib/product-tour-state";

type Session = { userId: number; tour: ProductTourState };
type TourContext = { register: (user: Account) => void; start: (user: Account) => Promise<void> };
const Context = createContext<TourContext | null>(null);
export const useProductTour = () => useContext(Context);
const emptyView = { target: null as HTMLElement | null, alreadyDone: false, waiting: true, unavailable: "" };
type TourUi = { saveError: string; busy: boolean; retry: number; view: typeof emptyView; acting: boolean };
function tourUiReducer(state: TourUi, update: Partial<TourUi> | "retry"): TourUi {
  return update === "retry" ? { ...state, retry: state.retry + 1 } : { ...state, ...update };
}

function viewport(): TourViewport {
  const view = window.visualViewport;
  return { width: view?.width ?? window.innerWidth, height: view?.height ?? window.innerHeight, left: view?.offsetLeft ?? 0, top: view?.offsetTop ?? 0 };
}

function Spotlight({ target, placement, children }: { target: HTMLElement; placement?: "right" | "bottom" | "top"; children: ReactNode }) {
  const panel = useRef<HTMLDivElement>(null);
  const [geometry, setGeometry] = useState<{ rect: TourRect; view: TourViewport; left: number; top: number } | null>(null);
  useLayoutEffect(() => {
    let frame = 0;
    function measure() {
      frame = 0;
      if (!target.isConnected || !panel.current) return;
      const rect = target.getBoundingClientRect();
      const view = viewport();
      const box = panel.current.getBoundingClientRect();
      const position = placeTooltip(rect, box, view, placement);
      setGeometry({ rect: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height }, view, left: position.left, top: position.top });
    }
    function update() { if (!frame) frame = requestAnimationFrame(measure); }
    measure();
    const observer = new ResizeObserver(update);
    observer.observe(target);
    if (panel.current) observer.observe(panel.current);
    observer.observe(document.body);
    window.addEventListener("resize", update);
    document.addEventListener("scroll", update, true);
    window.visualViewport?.addEventListener("resize", update);
    window.visualViewport?.addEventListener("scroll", update);
    return () => {
      cancelAnimationFrame(frame); observer.disconnect();
      window.removeEventListener("resize", update);
      document.removeEventListener("scroll", update, true);
      window.visualViewport?.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("scroll", update);
    };
  }, [target, placement]);

  if (typeof window === "undefined" || typeof document === "undefined") return null;

  const rect = geometry?.rect;
  const view = geometry?.view;
  const left = rect ? Math.max(0, rect.left - 6) : 0;
  const top = rect ? Math.max(0, rect.top - 6) : 0;
  const right = rect ? Math.min(window.innerWidth, rect.right + 6) : 0;
  const bottom = rect ? Math.min(window.innerHeight, rect.bottom + 6) : 0;
  const width = Math.max(0, right - left), height = Math.max(0, bottom - top);
  const radius = Math.min(12, width / 2, height / 2);
  const hole = `M${left + radius},${top} H${right - radius} Q${right},${top} ${right},${top + radius} V${bottom - radius} Q${right},${bottom} ${right - radius},${bottom} H${left + radius} Q${left},${bottom} ${left},${bottom - radius} V${top + radius} Q${left},${top} ${left + radius},${top} Z`;
  return createPortal(<div className="product-tour-layer">
    {geometry && width > 0 && height > 0 && <>
      <svg className="product-tour-shade" width="100%" height="100%" aria-hidden="true"><path fillRule="evenodd" d={`M0,0 H${window.innerWidth} V${window.innerHeight} H0 Z ${hole}`} /></svg>
      <div className="product-tour-highlight" aria-hidden="true" style={{ left, top, width, height }} />
    </>}
    <div ref={panel} className="product-tour-popover" style={{ left: geometry?.left ?? 12, top: geometry?.top ?? 12, visibility: geometry ? "visible" : "hidden", maxHeight: Math.max(0, (view?.height ?? window.innerHeight) - 24), maxWidth: Math.max(0, (view?.width ?? window.innerWidth) - 24) }}>
      {children}
    </div>
  </div>, tourPortalRoot(target) ?? document.body);
}

/** Lives above route pages; route remounts never reset the employee's tour. */
export function ProductTourProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [session, setSession] = useState<Session | null>(null);
  const sessionRef = useRef<Session | null>(null);
  const writes = useRef<Promise<unknown> | null>(null);
  const revision = useRef(0);
  const [{ saveError, busy, retry, view, acting }, updateUi] = useReducer(tourUiReducer, { saveError: "", busy: false, retry: 0, view: emptyView, acting: false });
  const { setSaveError, setBusy, setView, setActing, setRetry } = useMemo(() => ({
    setSaveError: (saveError: string) => updateUi({ saveError }),
    setBusy: (busy: boolean) => updateUi({ busy }),
    setView: (view: typeof emptyView) => updateUi({ view }),
    setActing: (acting: boolean) => updateUi({ acting }),
    setRetry: () => updateUi("retry"),
  }), []);
  const actingRef = useRef(false);
  const previousFocus = useRef<HTMLElement | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const pendingAction = useRef<TourAction>("progress");
  const controllerRef = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const fetchController = useRef<AbortController | null>(null);
  const recovery = useRef<Promise<void> | null>(null);
  const [portalRoot, setPortalRoot] = useState<HTMLElement | null>(null);
  useEffect(() => {
    mounted.current = true;
    setPortalRoot(document.body);
    return () => { mounted.current = false; controllerRef.current?.abort(); fetchController.current?.abort(); };
  }, []);

  const assign = useCallback((value: Session) => { sessionRef.current = value; setSession(value); }, []);
  const persist = useCallback(async (value: Session, action: TourAction) => {
    const version = ++revision.current;
    pendingAction.current = action;
    storeTour(value.userId, { tour: value.tour, pending: true, action });
    const operation = (writes.current ?? Promise.resolve()).catch(() => {}).then(() => {
      // Resolve the actor at dispatch too: queued writes must never cross logins.
      if (!mounted.current || sessionRef.current?.userId !== value.userId) throw new DOMException("Tour account changed", "AbortError");
      const controller = new AbortController(); fetchController.current = controller;
      return api<{ tour: ProductTourState }>("tour", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, currentStep: value.tour.currentStep }), signal: controller.signal,
      });
    });
    writes.current = operation;
    try {
      const result = await operation;
      if (mounted.current && revision.current === version && sessionRef.current?.userId === value.userId) {
        storeTour(value.userId, { tour: result.tour, pending: false, action }); setSaveError("");
      }
    } catch (caught) {
      // Another tab/device may have finished. A rejected old progress save must
      // never leave a completed/skipped account in an active local spotlight.
      if (action === "progress" && mounted.current && revision.current === version && sessionRef.current?.userId === value.userId) {
        try {
          const canonical = await api<{ tour: ProductTourState }>("tour");
          if (mounted.current && revision.current === version && sessionRef.current?.userId === value.userId && !tourIsActive(canonical.tour)) {
            assign({ userId: value.userId, tour: canonical.tour }); storeTour(value.userId, { tour: canonical.tour, pending: false, action }); setSaveError(""); return;
          }
        } catch { /* Preserve local recovery when the account is offline. */ }
      }
      if (mounted.current && revision.current === version && sessionRef.current?.userId === value.userId && !(caught instanceof DOMException && caught.name === "AbortError")) setSaveError(caught instanceof Error ? caught.message : "Tour progress could not be saved.");
      throw caught;
    }
  }, [assign, setSaveError]);

  const register = useCallback((user: Account) => {
    if (sessionRef.current?.userId === user.id) return;
    controllerRef.current?.abort(); fetchController.current?.abort(); previousFocus.current = null;
    let pending = readPendingTour(user.id);
    const accountTour = user.tour ?? { tourStarted: Boolean(user.tour_started), currentStep: "welcome", tourCompleted: user.tour_completed, tourSkipped: Boolean(user.tour_skipped) };
    if (pending?.action === "progress" && !tourIsActive(accountTour)) {
      storeTour(user.id, { tour: accountTour, pending: false, action: "progress" }); pending = null;
    }
    const tour = pending?.tour ?? accountTour;
    const value = { userId: user.id, tour };
    revision.current++; setSaveError(""); assign(value);
    const recovered = pending ? persist(value, pending.action).finally(() => { if (recovery.current === recovered) recovery.current = null; }) : null;
    recovery.current = recovered;
    void recovery.current?.catch(() => {});
  }, [assign, persist, setSaveError]);

  const ensureStartSaved = useCallback(async () => {
    const current = sessionRef.current;
    if (!current || readPendingTour(current.userId)?.action !== "start") return;
    if (!recovery.current) {
      const operation = persist(current, "start").finally(() => { if (recovery.current === operation) recovery.current = null; });
      recovery.current = operation;
    }
    await recovery.current;
  }, [persist]);

  const start = useCallback(async (user: Account) => {
    register(user);
    const value = sessionRef.current!;
    if (tourIsActive(value.tour)) {
      await ensureStartSaved();
      const current = sessionRef.current;
      if (!mounted.current || current?.userId !== user.id || !tourIsActive(current.tour)) return;
      setRetry(); router.replace(productTourSteps.find((step) => step.id === current.tour.currentStep)?.route ?? "/"); return;
    }
    const next = { userId: user.id, tour: { tourStarted: true, currentStep: productTourSteps[0].id, tourCompleted: false, tourSkipped: false } };
    // The account guard must see started before navigation to the real workspace.
    await persist(next, "start");
    if (!mounted.current || sessionRef.current?.userId !== user.id) return;
    assign(next); router.replace("/");
  }, [assign, persist, register, router, ensureStartSaved, setRetry]);

  const active = Boolean(session && tourIsActive(session.tour));
  const index = Math.max(0, productTourSteps.findIndex((step) => step.id === session?.tour.currentStep));
  const step = productTourSteps[index];
  const publicPage = !pathname || /^\/(login|password|onboarding|admin|invite|mcp)(\/|$)/.test(pathname);
  const paused = active && !publicPage && pathname !== step.route && pathname !== "/tour" && !(acting && pathname === step.action?.route);

  const move = useCallback(async (nextIndex: number) => {
    const current = sessionRef.current;
    if (!current || !tourIsActive(current.tour) || nextIndex < 0 || nextIndex >= productTourSteps.length) return;
    // Never render the next step's copy over the previous step's live target.
    setView(emptyView); setBusy(true);
    const next = { ...current, tour: { ...current.tour, currentStep: productTourSteps[nextIndex].id } };
    assign(next);
    const destination = productTourSteps[nextIndex].route;
    if (window.location.pathname !== destination) router.push(destination);
    try { await persist(next, "progress"); } catch { /* Locally saved progress remains available and can be retried. */ }
    finally { if (sessionRef.current?.tour.currentStep === next.tour.currentStep) setBusy(false); }
  }, [assign, persist, router, setView, setBusy]);

  const end = useCallback((action: "complete" | "skip") => {
    const current = sessionRef.current;
    if (!current) return;
    controllerRef.current?.abort();
    const next = { ...current, tour: { ...current.tour, tourCompleted: action === "complete", tourSkipped: action === "skip" } };
    assign(next); setView(emptyView); actingRef.current = false; setActing(false);
    const returnFocus = previousFocus.current?.isConnected ? previousFocus.current : view.target;
    if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true });
    void persist(next, action).catch(() => {});
    // Finish leaves the employee at the real Settings restart control.
  }, [assign, persist, view.target, setView, setActing]);

  useEffect(() => {
    if (!active || publicPage) return;
    const controller = new AbortController(); controllerRef.current?.abort(); controllerRef.current = controller;
    setView(emptyView); actingRef.current = false; setActing(false);
    if (!previousFocus.current?.isConnected) previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    async function prepare() {
      await ensureStartSaved();
      if (controller.signal.aborted) return;
      await waitForTourCondition({ route: step.route }, controller.signal);
      let target = visibleTourElement(step.target);
      const alreadyDone = Boolean(!target && step.action?.success && visibleTourElement(step.action.success));
      if (!target && alreadyDone) target = visibleTourElement(step.action!.success!);
      if (!target && step.prepare && !visibleTourElement(step.prepare.visible)) {
        const opener = await waitForTourElement(step.prepare.open, controller.signal);
        opener.click();
        await waitForTourElement(step.prepare.visible, controller.signal);
      }
      if (!target && step.target.includes('data-tour="nav-')) {
        const toggle = visibleTourElement('[data-tour="nav-toggle"]');
        if (toggle?.getAttribute("aria-expanded") === "false") toggle.click();
      }
      target ??= await waitForTourElement(step.target, controller.signal);
      target.scrollIntoView({ behavior: reducedMotion ? "instant" : "smooth", block: "center", inline: "nearest" });
      await settleTourTarget(target, controller.signal, reducedMotion);
      if (!controller.signal.aborted) {
        if (!target.isConnected || !visibleTourElement(alreadyDone ? step.action!.success! : step.target)) throw new Error("This control has closed. Retry this step or skip the tour.");
        setView({ target, alreadyDone, waiting: false, unavailable: "" });
      }
    }
    void prepare().catch((caught) => {
      if (!controller.signal.aborted) setView({ target: null, alreadyDone: false, waiting: false, unavailable: caught instanceof Error ? caught.message : "This control is not available." });
    });
    return () => controller.abort();
    // Navigation is driven only by a step change or an explicit Retry/Resume.
    // An unrelated user navigation pauses the tour instead of pulling them back.
  }, [active, publicPage, step, retry, session?.userId, ensureStartSaved, setView, setActing]);

  const wasPaused = useRef(false);
  useEffect(() => {
    if (active && wasPaused.current && !paused && pathname === step.route && view.target && !view.target.isConnected) setRetry();
    wasPaused.current = paused;
  }, [active, paused, pathname, step.route, view.target, setRetry]);

  useEffect(() => {
    if (!active || !view.target || paused) return;
    const target = view.target;
    const controller = controllerRef.current;
    if (!controller) return;
    function clicked(event: MouseEvent) {
      if (!step.action || actingRef.current || !(event.target instanceof Node) || !target.contains(event.target)) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
      actingRef.current = true; setActing(true);
      void waitForTourCondition(step.action, controller!.signal).then(() => {
        if (!controller!.signal.aborted) void move(index + 1);
      }).catch((caught) => {
        if (!controller!.signal.aborted) {
          actingRef.current = false; setActing(false);
          setView({ target: null, alreadyDone: false, waiting: false, unavailable: caught instanceof Error ? caught.message : "The action did not finish. Try again." });
        }
      });
    }
    document.addEventListener("click", clicked, true);
    function checkTarget() {
      const visible = visibleTourElement(step.target) === target || Boolean(step.action?.success && visibleTourElement(step.action.success) === target);
      if ((!target.isConnected || !visible) && !actingRef.current) setView({ target: null, alreadyDone: false, waiting: false, unavailable: "This control has closed. Retry this step or skip the tour." });
    }
    const observer = new MutationObserver(checkTarget);
    observer.observe(document.body, { childList: true, subtree: true, attributes: true });
    checkTarget();
    window.addEventListener("resize", checkTarget);
    return () => { document.removeEventListener("click", clicked, true); window.removeEventListener("resize", checkTarget); observer.disconnect(); };
  }, [active, view.target, paused, step, index, move, setActing, setView]);

  useEffect(() => {
    if (!active || publicPage) return;
    function keyboard(event: KeyboardEvent) {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); end("skip"); }
      if (!dialog.current?.contains(event.target as Node)) return;
      if (event.key === "ArrowLeft" && index > 0 && !busy) { event.preventDefault(); void move(index - 1); }
      if (event.key === "ArrowRight" && !busy && (!step.action || view.alreadyDone) && index < productTourSteps.length - 1) { event.preventDefault(); void move(index + 1); }
    }
    document.addEventListener("keydown", keyboard, true);
    return () => document.removeEventListener("keydown", keyboard, true);
  }, [active, publicPage, end, index, busy, move, step.action, view.alreadyDone]);

  useEffect(() => {
    if (view.target && !paused) dialog.current?.focus({ preventScroll: true });
  }, [view.target, paused]);

  const context = useMemo(() => ({ register, start }), [register, start]);
  const panel = <dialog open ref={dialog} className="product-tour-dialog" aria-modal="false" aria-labelledby="product-tour-title" aria-describedby="product-tour-step product-tour-body" tabIndex={-1}>
    <div className="product-tour-meta"><span id="product-tour-step" aria-label={`Step ${index + 1} of ${productTourSteps.length}`}>{index + 1} of {productTourSteps.length}</span><button type="button" className="button ghost" onClick={() => end("skip")} aria-label="Skip tour">Skip tour</button></div>
    <h2 id="product-tour-title">{step.title}</h2>
    <p id="product-tour-body">{step.body}</p>
    {step.action && !view.alreadyDone && <div className="product-tour-instruction"><strong>{acting ? "Waiting for the page…" : step.action.label}</strong><button type="button" className="button ghost" disabled={acting || busy} onClick={() => {
      view.target?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "center" });
      view.target?.focus({ preventScroll: true });
    }}>Go to control</button></div>}
    {view.alreadyDone && <p className="product-tour-note">Already open. Continue when you’re ready.</p>}
    {saveError && <p className="error" role="status">Progress saved on this browser. Account sync needs a retry.</p>}
    <div className="product-tour-actions"><button type="button" className="button" disabled={index === 0 || busy} onClick={() => void move(index - 1)}>Back</button>{index === productTourSteps.length - 1 ? <button type="button" className="button primary" disabled={busy} onClick={() => end("complete")}>Finish</button> : <button type="button" className="button primary" disabled={busy || Boolean(step.action && !view.alreadyDone)} onClick={() => void move(index + 1)}>Next</button>}</div>
  </dialog>;

  return <Context.Provider value={context}>{children}
    {active && !publicPage && !paused && view.target && <Spotlight target={view.target} placement={step.placement}>{panel}</Spotlight>}
    {active && !publicPage && portalRoot && (paused || !view.target) && createPortal(<section className="product-tour-recovery" aria-label="Product tour" aria-live="polite">
      <strong>{paused ? "Tour paused" : view.unavailable ? "This step isn’t ready" : "Opening your next tour step…"}</strong>
      {(paused || view.unavailable) && <p>{paused ? "Explore freely, then return when you’re ready." : view.unavailable}</p>}
      <div className="product-tour-actions">{index > 0 && <button type="button" className="button" disabled={busy} onClick={() => void move(index - 1)}>Back</button>}{(paused || view.unavailable) && <button type="button" className="button" onClick={() => { if (window.location.pathname !== step.route) router.push(step.route); setRetry(); }}>{paused ? "Resume tour" : "Retry step"}</button>}<button type="button" className="button ghost" onClick={() => end("skip")}>Skip tour</button></div>
    </section>, tourPortalRoot() ?? portalRoot)}
    {saveError && !active && !publicPage && <div className="product-tour-sync-error" role="status">Tour closed. Your account could not be updated. <button className="button" type="button" onClick={() => { const current = sessionRef.current; if (current) void persist(current, pendingAction.current).catch(() => {}); }}>Retry save</button><button className="button ghost" type="button" onClick={() => setSaveError("")}>Dismiss</button></div>}
  </Context.Provider>;
}
