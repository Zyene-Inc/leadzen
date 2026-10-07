"use client";

import { memo, useEffect, useRef, useState } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { workspaceLink } from "@/lib/chat";

function safeLink(value: string) {
  if (workspaceLink(value)) return value;
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password ? value : "";
  } catch { return ""; }
}

const components: Components = {
  h1: ({ children }) => <h2>{children}</h2>,
  a: ({ href, children }) => href ? <a href={href} target={href.startsWith("/") ? undefined : "_blank"} rel="noopener noreferrer">{children}</a> : <span>{children}</span>,
  // Model text cannot silently load remote images or tracking pixels.
  img: ({ alt }) => <span>{alt || "Image"}</span>,
  table: ({ children }) => <div className="chat-table-scroll" role="region" aria-label="Response table" tabIndex={0}><table>{children}</table></div>,
};

function useStreamedText(content: string, streaming: boolean) {
  const [visible, setVisible] = useState(content);
  const current = useRef(content);
  useEffect(() => {
    const motion = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const show = (value: string) => { current.current = value; setVisible(value); };
    if (!streaming || !content.startsWith(current.current) || !motion || motion.matches || document.hidden) {
      show(content);
      return;
    }
    // Smooth only newly received characters; never invent text or replay history.
    const prefix = current.current;
    const received = Array.from(content.slice(prefix.length));
    if (!received.length) return;
    let frame = 0;
    let start: number | undefined;
    // Reveal the batch over ~600 ms so the user actually perceives a
    // typewriter effect; the original 120 ms was too fast to read as typing.
    const DURATION_MS = 600;
    function reveal(at: number) {
      start ??= at;
      const fraction = Math.min(1, (at - start + 16) / DURATION_MS);
      const burst = Math.min(received.length, Math.max(2, Math.ceil(received.length * fraction)));
      show(prefix + received.slice(0, burst).join(""));
      if (fraction < 1) frame = requestAnimationFrame(reveal);
    }
    const finish = () => { cancelAnimationFrame(frame); show(content); };
    const visibility = () => { if (document.hidden) finish(); };
    const reduced = () => { if (motion.matches) finish(); };
    frame = requestAnimationFrame(reveal);
    document.addEventListener("visibilitychange", visibility);
    motion.addEventListener?.("change", reduced);
    return () => { cancelAnimationFrame(frame); document.removeEventListener("visibilitychange", visibility); motion.removeEventListener?.("change", reduced); };
  }, [content, streaming]);
  return !streaming || !content.startsWith(visible) ? content : visible;
}

export const ChatResponse = memo(function ChatResponse({ content, streaming = false }: { content: string; streaming?: boolean }) {
  const text = useStreamedText(content, streaming);
  return <div className="chat-message-text chat-markdown" aria-busy={streaming}>
    <Markdown remarkPlugins={[remarkGfm]} skipHtml urlTransform={safeLink} components={components}>{text}</Markdown>
    {streaming && <span className="stream-cursor" aria-hidden="true"> ▍</span>}
  </div>;
});
