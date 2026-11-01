/* Display-only formatting; API values and exported records remain unchanged. */
// One sentence shown in small type under every stage calculation that uses the previous eight same weekdays.
// The figures come from analysis/baseline_window.py (docs/BASELINE_WINDOW.md); the chat answers "why eight?" with the full study.
window.WHY_EIGHT = 'Why eight same weekdays: the factory is closed on Sundays and each weekday runs at its own level, so a day is compared with its own weekday; on this factory’s data eight weeks cuts false alerts from about 0.67 to 0.1 a month while still catching real drops, and more weeks add little (ask “why eight?” in the chat for the study).';
window.whyEightHTML = function(){ return '<small class="why-eight">' + window.WHY_EIGHT + '</small>'; };
window.formatWorkspaceTime = function(value) {
  if (!value) return '—';
  const text = String(value);
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
  const instant = new Date(text);
  if (Number.isNaN(instant.getTime())) return text;
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
    timeZone:'Asia/Singapore', year:'numeric', month:'2-digit', day:'2-digit',
    hour:'2-digit', minute:'2-digit', hourCycle:'h23'
  }).formatToParts(instant).map(p=>[p.type,p.value]));
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
};
window.formatWorkspaceText = function(value) {
  return String(value ?? '').replace(/\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})\b/g,
    match => window.formatWorkspaceTime(match));
};
