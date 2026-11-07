/** "1 recipient", "3 recipients"; pass the plural when it is not just +s. */
export function plural(count: number | null | undefined, singular: string, pluralForm = `${singular}s`) {
  if (typeof count !== "number" || !Number.isFinite(count)) return `— ${pluralForm}`;
  return `${count.toLocaleString("en-US")} ${count === 1 ? singular : pluralForm}`;
}

/** Stored states such as "failed" or "needs_review" read as "Failed", "Needs review". */
export function stateLabel(state: string) {
  const text = state.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
