"use client";
import { HelpText } from "@/components/help-tooltip";
import type { Country, Draft } from "@/lib/setup-wizard";

export function CountrySelect({
  label,
  value,
  countries,
  onChange,
}: {
  label: string;
  value: string;
  countries: Country[];
  onChange: (value: string) => void;
}) {
  return (
    <label>
      {label}
      <select
        className="select"
        required
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {countries.map((country) => (
          <option key={country.code} value={country.code}>
            {country.name}
          </option>
        ))}
      </select>
    </label>
  );
}
export function SetupIdentity({
  draft,
  countries,
  onChange,
}: {
  draft: Draft;
  countries: Country[];
  onChange: (draft: Draft) => void;
}) {
  return (
    <section className="panel settings-card">
      <div className="panel-head">
        <h2 className="panel-title">About you</h2>
      </div>
      <HelpText label="Outreach identity">Your name and email identify you in outreach. They are separate from your sending mailbox and do not change your LeadZen login.</HelpText>
      <div className="form-grid">
        <label>
          Your name
          <input
            className="input"
            autoComplete="name"
            required
            maxLength={200}
            value={draft.operator_name}
            onChange={(event) =>
              onChange({ ...draft, operator_name: event.target.value })
            }
            aria-describedby="identity-name-help"
          />
        </label>
        <label>
          Your email
          <input
            className="input"
            type="email"
            autoComplete="email"
            required
            maxLength={150}
            value={draft.operator_email}
            onChange={(event) =>
              onChange({ ...draft, operator_email: event.target.value })
            }
          />
        </label>
        <CountrySelect
          label="Country"
          value={draft.operator_country_code}
          countries={countries}
          onChange={(value) =>
            onChange({ ...draft, operator_country_code: value })
          }
        />
      </div>
      <p className="settings-help" id="identity-name-help">
        Use your name, not an email address.
      </p>
    </section>
  );
}
export function SetupOffer({
  draft,
  onChange,
}: {
  draft: Draft;
  onChange: (draft: Draft) => void;
}) {
  return (
    <section className="panel settings-card">
      <div className="panel-head">
        <h2 className="panel-title">What are you selling?</h2>
      </div>
      <HelpText label="Writing a useful offer">Describe who your product helps, the problem it solves, and its value. The agent uses this to qualify leads and draft outreach.</HelpText>
      <div className="form-grid">
        <label>
          Outreach purpose
          <select
            className="select"
            value={draft.purpose}
            required
            onChange={(event) =>
              onChange({ ...draft, purpose: event.target.value })
            }
          >
            <option value="zyene_reviews">
              Zyene Reviews — a Zyene product
            </option>
            <option value="zyene_services">Zyene services</option>
            <option value="other">Another approved initiative</option>
          </select>
        </label>
        <label>
          Workspace name
          <input
            className="input"
            required
            maxLength={160}
            value={draft.workspace_name}
            onChange={(event) =>
              onChange({ ...draft, workspace_name: event.target.value })
            }
            placeholder="Dental practice outreach"
          />
        </label>
        <label className="wide">
          Product name
          <input
            className="input"
            required
            maxLength={160}
            value={draft.product_name}
            onChange={(event) =>
              onChange({ ...draft, product_name: event.target.value })
            }
            placeholder="Your product or service"
          />
        </label>
        <label className="wide">
          Describe your product
          <textarea
            className="input textarea"
            rows={4}
            required
            maxLength={10000}
            value={draft.product_docs}
            onChange={(event) =>
              onChange({ ...draft, product_docs: event.target.value })
            }
            placeholder="What does it do, who is it for, and what problem does it solve?"
          />
        </label>
        <label className="wide">
          Booking link (optional)
          <input
            className="input"
            type="url"
            maxLength={500}
            value={draft.booking_link}
            onChange={(event) =>
              onChange({ ...draft, booking_link: event.target.value })
            }
            placeholder="https://…"
          />
        </label>
      </div>
    </section>
  );
}
