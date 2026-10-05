"use client";

import { useId, useState, type InputHTMLAttributes } from "react";
import { Icon } from "@/components/icon";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label: string;
  containerClassName?: string;
};

/** Reveals only the current form input. Saved secrets never enter this component. */
export function SecretInput({
  label,
  id,
  containerClassName = "",
  className = "input",
  disabled,
  ...input
}: Props) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const [visible, setVisible] = useState(false);
  // A controlled form clears credentials after saving: reset the reveal state
  // too, so the next replacement key starts hidden. No secret is persisted here.
  if (visible && input.value === "") setVisible(false);

  return (
    <div className={`secret-field ${containerClassName}`}>
      <label htmlFor={inputId}>{label}</label>
      <div className="secret-control">
        <input
          {...input}
          id={inputId}
          className={className}
          type={visible ? "text" : "password"}
          disabled={disabled}
          spellCheck={false}
          autoCapitalize="none"
        />
        <button
          type="button"
          className="secret-toggle"
          aria-label={`${visible ? "Hide" : "Show"} ${label}`}
          aria-controls={inputId}
          aria-pressed={visible}
          disabled={disabled}
          onClick={() => setVisible(!visible)}
        >
          <Icon name={visible ? "eye-off" : "eye"} />
        </button>
      </div>
    </div>
  );
}
