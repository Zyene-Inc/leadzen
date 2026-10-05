"use client";
import { PageHeading } from "@/components/page-heading";
import { useEffect, useRef } from "react";
import { Sidebar } from "@/components/sidebar";
import { SetupTools } from "@/components/setup-tools";
import { SetupIdentity, SetupOffer } from "@/components/setup-profile";
import { SetupAudience } from "@/components/setup-audience";
import { stepLabels, type Wizard } from "@/lib/setup-wizard";
import { useSetupWizard } from "@/lib/use-setup-wizard";
import type { Account } from "@/lib/auth";

export default function Onboarding({
  user,
  initial,
}: {
  user: Account;
  initial: Wizard | null;
}) {
  const {
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
  } = useSetupWizard(user, initial);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, [step]);
  return (
    <div className="shell">
      <Sidebar user={user} active="onboarding" />
      <main className="main">
        <div className="topbar">
          <PageHeading title="Set up your workspace" help="Connect your tools, introduce your offer, and define who you want to reach. You can update these in Settings later." />
        </div>
        <ol className="setup-steps" aria-label="Setup progress">
          {stepLabels.map((label, index) => (
            <li
              key={label}
              aria-current={step === index + 1 ? "step" : undefined}
              className={step === index + 1 ? "current" : ""}
            >
              <span>{index + 1}</span>
              {label}
            </li>
          ))}
        </ol>
        <h2 ref={heading} tabIndex={-1} className="setup-step-heading">
          Step {step} of 6 · {stepLabels[step - 1]}
        </h2>
        {activity.error && (
          <div className="error" role="alert">
            {activity.error}
          </div>
        )}
        {!state ? (
          <button
            type="button"
            className="button secondary"
            disabled={activity.busy}
            onClick={reload}
          >
            Retry loading setup
          </button>
        ) : (
          <form
            onSubmit={submit}
            className="setup-form"
            aria-busy={activity.busy}
          >
            <fieldset disabled={activity.busy} className="setup-fields">
              {[1, 2, 4].includes(step) && (
                <SetupTools
                  step={step}
                  settings={state.settings}
                  credentials={state.credentials}
                  checks={state.wizard.checks}
                  discoveryEnabled={state.draft.discovery_enabled}
                  testing={activity.testing !== null}
                  onSettings={editSettings}
                  onCredentials={editCredentials}
                  onTest={(kind) => void test(kind)}
                  onDiscovery={(enabled) =>
                    setState({
                      ...state,
                      draft: { ...state.draft, discovery_enabled: enabled },
                    })
                  }
                />
              )}
              {step === 3 && (
                <SetupIdentity
                  draft={state.draft}
                  countries={state.wizard.countries}
                  onChange={(draft) => setState({ ...state, draft })}
                />
              )}
              {step === 5 && (
                <SetupOffer
                  draft={state.draft}
                  onChange={(draft) => setState({ ...state, draft })}
                />
              )}
              {step === 6 && (
                <SetupAudience
                  draft={state.draft}
                  countries={state.wizard.countries}
                  onChange={(draft) => setState({ ...state, draft })}
                />
              )}
            </fieldset>
            <div className="settings-actions setup-actions">
              <button
                type="button"
                className="button secondary"
                disabled={activity.busy || step === 1}
                onClick={() => {
                  setState({ ...state, step: step - 1 });
                  setActivity({ busy: false, testing: null, error: "" });
                }}
              >
                Back
              </button>
              <span>
                Saved as you continue · Connection tests last 24 hours
              </span>
              <button type="submit" className="button" disabled={activity.busy}>
                {activity.busy
                  ? "Please wait…"
                  : step === 6
                    ? "Finish setup"
                    : "Continue"}
              </button>
            </div>
          </form>
        )}
      </main>
    </div>
  );
}
