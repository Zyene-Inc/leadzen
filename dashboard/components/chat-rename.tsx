"use client";
import { useEffect, useRef } from "react";

export function ChatRename({ title, busy, change, save, close }: {
  title: string; busy: boolean; change: (title: string) => void; save: (title: string) => Promise<boolean>; close: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { input.current?.focus(); }, []);
  async function submit(data: FormData) {
    if (await save(String(data.get("title") || ""))) close();
  }
  return <form className="chat-rename" action={submit}>
    <label htmlFor="chat-title">Conversation name</label>
    <input ref={input} id="chat-title" name="title" className="input" maxLength={100} required value={title} onChange={(event) => change(event.target.value)} />
    <button className="button primary" type="submit" disabled={busy}>Save name</button>
    <button className="button" type="button" disabled={busy} onClick={close}>Cancel</button>
  </form>;
}
