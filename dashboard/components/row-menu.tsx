"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { Icon } from "@/components/icon";

/** Secondary row actions behind one button; closes on Escape, outside click or choice. */
export function RowMenu({ label, children }: { label: string; children: ReactNode }) {
  const menu = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    function close(event: Event) {
      const details = menu.current;
      if (!details?.open) return;
      if (event instanceof KeyboardEvent) {
        if (event.key !== "Escape") return;
        details.open = false;
        details.querySelector("summary")?.focus();
        return;
      }
      if (!details.contains(event.target as Node)) details.open = false;
    }
    function dismiss() { if (menu.current) menu.current.open = false; }
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", close);
    window.addEventListener("scroll", dismiss, true);
    window.addEventListener("resize", dismiss);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", close);
      window.removeEventListener("scroll", dismiss, true);
      window.removeEventListener("resize", dismiss);
    };
  }, []);
  // Fixed placement keeps the list visible inside horizontally scrolling tables.
  function place() {
    const details = menu.current;
    const list = details?.querySelector<HTMLElement>(".row-menu-list");
    if (!details?.open || !list) return;
    const anchor = details.querySelector("summary")!.getBoundingClientRect();
    const below = window.innerHeight - anchor.bottom > list.offsetHeight + 12;
    const top = below ? anchor.bottom + 4 : Math.max(8, anchor.top - list.offsetHeight - 4);
    const left = Math.max(8, anchor.right - list.offsetWidth);
    list.style.top = `${top}px`;
    list.style.left = `${left}px`;
    // A transformed ancestor (such as an arrival animation) offsets fixed elements; correct for it.
    const actual = list.getBoundingClientRect();
    list.style.top = `${2 * top - actual.top}px`;
    list.style.left = `${2 * left - actual.left}px`;
  }
  return (
    <details className="row-menu" ref={menu} onToggle={place} onClick={(event) => {
      if ((event.target as HTMLElement).closest(".row-menu-list button")) menu.current!.open = false;
    }}>
      <summary className="button ghost" aria-label={label} title={label}><Icon name="more" /></summary>
      <div className="row-menu-list">{children}</div>
    </details>
  );
}
