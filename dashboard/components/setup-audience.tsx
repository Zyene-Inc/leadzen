"use client";
import { CountrySelect } from "@/components/setup-profile";
import {
  roleOptions,
  seniorityOptions,
  targetPreview,
  type Audience,
  type Country,
  type Draft,
} from "@/lib/setup-wizard";
const defaultRoles = new Set(roleOptions);

function toggle(values: string[], value: string, checked: boolean) {
  return checked
    ? [...values, value]
    : values.filter((entry) => entry !== value);
}
export function SetupAudience({
  draft,
  countries,
  onChange,
}: {
  draft: Draft;
  countries: Country[];
  onChange: (draft: Draft) => void;
}) {
  const audience = draft.audience;
  const chosenRoles = new Set(audience.roles);
  const chosenSeniority = new Set(audience.seniority);
  function update(changes: Partial<Audience>) {
    onChange({
      ...draft,
      audience: { ...audience, ...changes },
      confirmed: false,
    });
  }
  const customRoles = audience.roles.filter((role) => !defaultRoles.has(role));
  return (
    <section className="panel settings-card">
      <div className="panel-head">
        <h2 className="panel-title">Who do you want to reach?</h2>
      </div>
      <div className="form-grid">
        <label>
          Industry
          <input
            className="input"
            required
            maxLength={300}
            value={audience.industry}
            onChange={(event) => update({ industry: event.target.value })}
            placeholder="Dental practices"
          />
        </label>
        <CountrySelect
          label="Target country"
          countries={countries}
          value={audience.country}
          onChange={(country) => update({ country })}
        />
        <label>
          Company size
          <select
            className="select"
            required
            value={audience.company_size}
            onChange={(event) => update({ company_size: event.target.value })}
          >
            {["any", "1-10", "2-50", "11-50", "51-200", "201-500", "501+"].map(
              (size) => (
                <option key={size} value={size}>
                  {size === "any" ? "Any" : `${size} employees`}
                </option>
              ),
            )}
          </select>
        </label>
      </div>
      <fieldset className="setup-choice-group">
        <legend>Target roles</legend>
        <div className="setup-choice-grid">
          {roleOptions.map((role) => (
            <label key={role}>
              <input
                type="checkbox"
                checked={chosenRoles.has(role)}
                onChange={(event) =>
                  update({
                    roles: toggle(audience.roles, role, event.target.checked),
                  })
                }
              />
              {role}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="form-grid">
        <label className="wide">
          Other roles (comma-separated)
          <input
            className="input"
            maxLength={1200}
            value={customRoles.join(",")}
            onBlur={() =>
              update({
                roles: Array.from(
                  new Set(
                    audience.roles.map((role) => role.trim()).filter(Boolean),
                  ),
                ),
              })
            }
            onChange={(event) =>
              update({
                roles: [
                  ...audience.roles.filter((role) => defaultRoles.has(role)),
                  ...Array.from(new Set(event.target.value.split(","))).filter(
                    (role) => !defaultRoles.has(role.trim()),
                  ),
                ],
              })
            }
            placeholder="Restaurant manager, Agency director"
          />
        </label>
      </div>
      <fieldset className="setup-choice-group">
        <legend>Seniority</legend>
        <div className="setup-choice-grid">
          {seniorityOptions.map(([level, label]) => (
            <label key={level}>
              <input
                type="checkbox"
                checked={chosenSeniority.has(level)}
                onChange={(event) =>
                  update({
                    seniority: toggle(
                      audience.seniority,
                      level,
                      event.target.checked,
                    ),
                  })
                }
              />
              {label}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="form-grid">
        <label className="wide">
          Additional instructions
          <textarea
            className="input textarea"
            rows={4}
            maxLength={5000}
            value={audience.instructions}
            onChange={(event) => update({ instructions: event.target.value })}
            placeholder="Decision-makers responsible for marketing or operations. Exclude students, trainees and people outside the target country."
          />
        </label>
      </div>
      {draft.legacy_target && (
        <details className="setup-legacy">
          <summary>Previous audience notes</summary>
          <p>{draft.legacy_target}</p>
        </details>
      )}
      <div className="setup-preview">
        <h3>Target preview</h3>
        <p>{targetPreview(audience, countries)}</p>
        <p className="settings-help">
          These are instructions for discovery and AI qualification, not a
          guarantee that every profile matches. Review contacts before approving
          outreach.
        </p>
        <label className="setup-confirm">
          <input
            type="checkbox"
            required
            checked={draft.confirmed}
            onChange={(event) =>
              onChange({ ...draft, confirmed: event.target.checked })
            }
          />
          Looks good — I reviewed this target
        </label>
      </div>
      <label className="check-row">
        <input
          type="checkbox"
          required
          checked={draft.accepted_legal_notice}
          onChange={(event) =>
            onChange({ ...draft, accepted_legal_notice: event.target.checked })
          }
        />
        I’m authorized to use this mailbox and will respect consent, opt-outs
        and provider policies.
      </label>
    </section>
  );
}
