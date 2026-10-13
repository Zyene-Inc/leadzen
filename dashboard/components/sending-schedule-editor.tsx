"use client";

import { HelpTooltip } from "@/components/help-tooltip";
import { NEW_YORK_TIMEZONE_LABEL, scheduleDays, scheduleDayNames, type SendingSchedule } from "@/lib/sending-schedule";

export function SendingScheduleEditor({ value, onChange }: { value: SendingSchedule; onChange: (value: SendingSchedule) => void }) {
  return <div className="sending-schedule-editor" data-tour="schedule-fields">
    <fieldset className="sending-schedule-days"><legend>Days each week</legend><div className="sending-day-options">{scheduleDays.map((label, day) => <label key={label} className={`sending-day ${value.days.includes(day) ? "selected" : ""}`}><input type="checkbox" aria-label={scheduleDayNames[day]} checked={value.days.includes(day)} onChange={(event) => onChange({ ...value, days: event.target.checked ? [...value.days, day].sort((a, b) => a - b) : value.days.filter((selected) => selected !== day) })} /><span>{label}</span></label>)}</div><div className="sending-day-shortcuts"><button className="button ghost" type="button" onClick={() => onChange({ ...value, days: [0, 1, 2, 3, 4] })}>Weekdays</button><button className="button ghost" type="button" onClick={() => onChange({ ...value, days: [0, 1, 2, 3, 4, 5, 6] })}>Every day</button></div></fieldset>
    <div className="form-grid sending-time-fields"><label>Start time<input className="input" type="time" required step={60} value={value.start} onChange={(event) => onChange({ ...value, start: event.target.value })} /></label><label>End time<input className="input" type="time" required step={60} value={value.end} onChange={(event) => onChange({ ...value, end: event.target.value })} /></label></div>
    <div className="sending-schedule-help"><p className="settings-help">{NEW_YORK_TIMEZONE_LABEL}</p><HelpTooltip label="New York time">All LeadZen times use New York time. Daylight saving time adjusts automatically.</HelpTooltip></div>
    <div className="sending-schedule-help"><p className="settings-help">Autopilot finds leads at the start time. Emails send until the end time.</p><HelpTooltip label="Sending schedule">Repeats every week, holidays included. Start and end on the same day. Email account limits still apply. Inbox replies can send right away. Saving does not find leads or send emails.</HelpTooltip></div>
    <p className="settings-help">Changes need a new review of automatic approvals.</p>
  </div>;
}
