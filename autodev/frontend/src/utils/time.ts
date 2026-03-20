/** Ensure a backend ISO string is treated as UTC before converting to local time. */
function toDate(ts: string): Date {
  // If there's no timezone indicator, append Z so the browser treats it as UTC
  return new Date(ts.endsWith('Z') || ts.includes('+') ? ts : ts + 'Z')
}

/** e.g. "3:45:12 PM" */
export function fmtTime(ts: string): string {
  return toDate(ts).toLocaleTimeString()
}

/** e.g. "1/15/2024, 3:45 PM" */
export function fmtDateTime(ts: string): string {
  return toDate(ts).toLocaleString()
}
