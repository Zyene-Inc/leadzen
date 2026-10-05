"use client";
import { useRef, useState, type FormEvent } from "react";
import {
  emptyCredentials,
  settingsBody,
  type Credentials,
  type Settings,
} from "@/lib/connection-settings";
import {
  initialConnections,
  initialDraft,
  stepValues,
  type CheckKind,
  type Wizard,
} from "@/lib/setup-wizard";
import type { Account } from "@/lib/auth";
import { api } from "@/lib/client-api";

function view(wizard: Wizard) {
  const next = wizard.onboarded
    ? 1
    : Math.min(
        6,
        [1, 2, 3, 4, 5, 6].find(
          (step) => !wizard.completed_steps.includes(step),
        ) ?? 6,
      );
  return {
    wizard,
    settings: initialConnections(wizard.connections),
    draft: initialDraft(wizard),
    credentials: { ...emptyCredentials },
    step: next,
  };
}
type View = ReturnType<typeof view>;
const post = (body: unknown, method = "POST") => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export function useSetupWizard(user: Account, initial: Wizard | null) {
  const submitting = useRef(false);
  const [state, setState] = useState<View | null>(() =>
    initial ? view(initial) : null,
  );
  const [activity, setActivity] = useState<{
    busy: boolean;
    testing: CheckKind | null;
    error: string;
  }>({
    busy: false,
    testing: null,
    error: initial ? "" : "Unable to load setup. Please retry.",
  });
  const step = state?.step ?? 1;

  function editSettings(next: Settings) {
    setState((current) => {
      if (!current) return current;
      const checks = { ...current.wizard.checks };
      if (JSON.stringify(next.llm) !== JSON.stringify(current.settings.llm))
        checks.ai = { connected: false };
      if (
        JSON.stringify(next.mailbox) !==
        JSON.stringify(current.settings.mailbox)
      )
        checks.mailbox = { connected: false };
      const providerChanged =
        next.llm.provider !== current.settings.llm.provider ||
        next.llm.base_url !== current.settings.llm.base_url;
      const mailboxChanged =
        next.mailbox.address !== current.settings.mailbox.address ||
        next.mailbox.smtp_host !== current.settings.mailbox.smtp_host ||
        next.mailbox.imap_host !== current.settings.mailbox.imap_host;
      const apiChanged =
        next.mailbox.transport !== current.settings.mailbox.transport ||
        next.mailbox.api_url !== current.settings.mailbox.api_url ||
        mailboxChanged;
      return {
        ...current,
        settings: {
          ...next,
          llm: {
            ...next.llm,
            api_key_configured: providerChanged
              ? false
              : next.llm.api_key_configured,
          },
          mailbox: {
            ...next.mailbox,
            password_configured: mailboxChanged
              ? false
              : next.mailbox.password_configured,
            imap_password_configured: mailboxChanged
              ? false
              : next.mailbox.imap_password_configured,
            api_key_configured: apiChanged
              ? false
              : next.mailbox.api_key_configured,
          },
        },
        wizard: { ...current.wizard, checks },
        credentials: {
          ...current.credentials,
          ai: providerChanged ? "" : current.credentials.ai,
          smtp: mailboxChanged ? "" : current.credentials.smtp,
          imap: mailboxChanged ? "" : current.credentials.imap,
          mailApi: apiChanged ? "" : current.credentials.mailApi,
        },
      };
    });
  }
  function editCredentials(next: Credentials) {
    setState((current) => {
      if (!current) return current;
      const checks = { ...current.wizard.checks };
      if (next.ai !== current.credentials.ai) checks.ai = { connected: false };
      if (next.bettercontact !== current.credentials.bettercontact)
        checks.discovery = { connected: false };
      if (
        next.smtp !== current.credentials.smtp ||
        next.imap !== current.credentials.imap ||
        next.mailApi !== current.credentials.mailApi
      )
        checks.mailbox = { connected: false };
      return {
        ...current,
        credentials: next,
        wizard: { ...current.wizard, checks },
      };
    });
  }
  async function test(kind: CheckKind) {
    if (!state || activity.busy || submitting.current) return;
    submitting.current = true;
    setActivity({ busy: true, testing: kind, error: "" });
    setState((current) =>
      current
        ? {
            ...current,
            wizard: {
              ...current.wizard,
              checks: {
                ...current.wizard.checks,
                [kind]: { connected: false },
              },
            },
          }
        : current,
    );
    try {
      const wizard = await api<Wizard>(
        "onboarding/test",
        post({ kind, ...settingsBody(state.settings, state.credentials) }),
      );
      setState((current) =>
        current
          ? {
              ...current,
              wizard,
              settings: initialConnections(wizard.connections),
              credentials: { ...emptyCredentials },
            }
          : current,
      );
      setActivity({ busy: false, testing: null, error: "" });
    } catch (caught) {
      setActivity({
        busy: false,
        testing: null,
        error:
          caught instanceof Error ? caught.message : "Connection test failed",
      });
    } finally {
      submitting.current = false;
    }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!state || activity.busy || submitting.current) return;
    submitting.current = true;
    setActivity({ busy: true, testing: null, error: "" });
    try {
      const wizard = await api<Wizard>(
        "onboarding/wizard",
        post(
          {
            step,
            values: stepValues(step, state.draft),
            ...settingsBody(state.settings, state.credentials),
          },
          "PUT",
        ),
      );
      setState({
        ...state,
        wizard,
        credentials: { ...emptyCredentials },
        settings: initialConnections(wizard.connections),
        draft: initialDraft(wizard),
        step: Math.min(6, step + 1),
      });
      if (step === 6) {
        await api("onboarding/complete", post({}));
        window.location.assign(user.tour_completed || user.tour_started || user.tour_skipped ? "/" : "/tour");
      } else setActivity({ busy: false, testing: null, error: "" });
    } catch (caught) {
      setActivity({
        busy: false,
        testing: null,
        error:
          caught instanceof Error ? caught.message : "Unable to save setup",
      });
    } finally {
      submitting.current = false;
    }
  }
  async function reload() {
    if (submitting.current) return;
    submitting.current = true;
    setActivity({ busy: true, testing: null, error: "" });
    try {
      setState(view(await api<Wizard>("onboarding/wizard")));
      setActivity({ busy: false, testing: null, error: "" });
    } catch {
      setActivity({
        busy: false,
        testing: null,
        error: "Unable to load setup. Please retry.",
      });
    } finally {
      submitting.current = false;
    }
  }
  return {
    state,
    setState,
    activity,
    setActivity,
    step,
    editSettings,
    editCredentials,
    test,
    submit,
    reload,
  };
}
