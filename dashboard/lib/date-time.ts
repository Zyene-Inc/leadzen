export const LEADZEN_TIME_ZONE = "America/New_York";
export const LEADZEN_TIME_ZONE_LABEL = "New York (Eastern Time)";

type DateValue = string | number | Date;
const formatters = new Map<string, Intl.DateTimeFormat>();

function formatter(options: Intl.DateTimeFormatOptions) {
  const fixedOptions = { ...options, timeZone: LEADZEN_TIME_ZONE };
  const key = JSON.stringify(fixedOptions);
  let value = formatters.get(key);
  if (!value) {
    value = new Intl.DateTimeFormat("en-US", fixedOptions);
    formatters.set(key, value);
  }
  return value;
}

export function formatNewYorkDateTime(
  value: DateValue,
  options: Intl.DateTimeFormatOptions = { dateStyle: "medium", timeStyle: "short" },
) {
  return formatter(options).format(new Date(value));
}

// Calendar arithmetic uses the New York date, so DST days need not be 24 hours.
export function newYorkDayKey(value: DateValue, offsetDays = 0) {
  const parts = formatter({ year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date(value));
  const part = (name: Intl.DateTimeFormatPartTypes) => Number(parts.find((item) => item.type === name)!.value);
  const calendarDate = new Date(Date.UTC(part("year"), part("month") - 1, part("day") + offsetDays));
  return calendarDate.toISOString().slice(0, 10);
}

export function newYorkHour(value: DateValue) {
  return Number(formatter({ hour: "numeric", hourCycle: "h23" }).format(new Date(value)));
}
