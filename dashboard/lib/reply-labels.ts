export type ReplyLabelName =
  | "interested"
  | "not_interested"
  | "out_of_office"
  | "unsubscribe"
  | "auto_reply"
  | "needs_review";

export const replyLabels: Record<ReplyLabelName, string> = {
  interested: "Interested",
  not_interested: "Not interested",
  out_of_office: "Out of office",
  unsubscribe: "Unsubscribe",
  auto_reply: "Automatic reply",
  needs_review: "Needs review",
};

function day(value: string) {
  const [year, month, date] = value.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, date)).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

/** What LeadZen did about a labelled reply, in plain words. */
export function replyLabelDetail(
  label: ReplyLabelName,
  returnDate: string | null,
  action: string,
) {
  if (action === "blocked") return "Added to Do not contact.";
  if (label === "out_of_office" && action === "held")
    return returnDate
      ? `Back ${day(returnDate)}. Follow-ups wait until the next business day.`
      : "No return date found. Follow-ups wait 7 days.";
  if (label === "out_of_office" && returnDate) return `Back ${day(returnDate)}.`;
  return "";
}
