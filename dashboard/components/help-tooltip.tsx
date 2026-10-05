"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Icon } from "@/components/icon";

/** Secondary guidance only: costs, errors and approval terms stay in the flow. */
export function HelpTooltip({ label, children }: { label: string; children: ReactNode }) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const bubble = useRef<HTMLSpanElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pinned = useRef(false);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ left: 0, top: 0 });

  function cancelClose() {
    if (timer.current) clearTimeout(timer.current);
  }
  function close() {
    cancelClose();
    pinned.current = false;
    setOpen(false);
  }
  function leave() {
    cancelClose();
    if (!pinned.current && document.activeElement !== trigger.current) {
      timer.current = setTimeout(() => setOpen(false), 120);
    }
  }

  useLayoutEffect(() => {
    if (!open || !trigger.current || !bubble.current) return;
    const anchor = trigger.current.getBoundingClientRect();
    const box = bubble.current.getBoundingClientRect();
    setPosition({
      left: Math.max(12, Math.min(anchor.left, window.innerWidth - box.width - 12)),
      top: Math.max(12, anchor.bottom + box.height + 8 <= window.innerHeight
        ? anchor.bottom + 6 : anchor.top - box.height - 6),
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function dismiss() {
      pinned.current = false;
      setOpen(false);
    }
    function outside(event: PointerEvent) {
      if (event.target instanceof Node && !trigger.current?.contains(event.target) && !bubble.current?.contains(event.target)) dismiss();
    }
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        // Dismiss this help without also cancelling the containing editor/dialog.
        event.stopPropagation();
        dismiss();
      }
    }
    function scroll(event: Event) {
      if (event.target instanceof Node && bubble.current?.contains(event.target)) return;
      dismiss();
    }
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape, true);
    document.addEventListener("scroll", scroll, true);
    window.addEventListener("resize", dismiss);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape, true);
      document.removeEventListener("scroll", scroll, true);
      window.removeEventListener("resize", dismiss);
    };
  }, [open]);

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  return (
    <>
      <button
        ref={trigger}
        type="button"
        className="help-trigger"
        aria-label={`Help: ${label}`}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onMouseEnter={() => { cancelClose(); setOpen(true); }}
        onMouseLeave={leave}
        onFocus={() => { cancelClose(); setOpen(true); }}
        onBlur={close}
        onClick={() => { pinned.current = !pinned.current; setOpen(pinned.current); }}
      >
        <Icon name="help" />
      </button>
      {open && createPortal(
        <span
          ref={bubble}
          id={id}
          role="tooltip"
          className="help-tooltip"
          style={position}
          onMouseEnter={cancelClose}
          onMouseLeave={leave}
        >
          <strong>{label}</strong>
          {children}
        </span>, document.body,
      )}
    </>
  );
}

export function HelpText({ label, children }: { label: string; children: ReactNode }) {
  return <div className="help-text"><span>{label}</span><HelpTooltip label={label}>{children}</HelpTooltip></div>;
}
