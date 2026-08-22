// Small hand-authored line-icon set (20x20 viewBox, single stroke weight),
// used instead of emoji throughout the UI. No external icon library
// dependency, matching this project's "no build step" architecture.
const ICON_PATHS = {
  search: '<circle cx="9" cy="9" r="6"/><line x1="18" y1="18" x2="13.4" y2="13.4"/>',
  package: '<path d="M3 6.5 10 3l7 3.5v7L10 17l-7-3.5v-7Z"/><path d="M3 6.5 10 10l7-3.5"/><line x1="10" y1="10" x2="10" y2="17"/>',
  ticket: '<rect x="2" y="5" width="16" height="10" rx="2"/><circle cx="14" cy="10" r="0.9" fill="currentColor" stroke="none"/><line x1="6" y1="6" x2="6" y2="14" stroke-dasharray="1.6 1.6"/>',
  building: '<rect x="4" y="2" width="12" height="16" rx="1"/><circle cx="7" cy="6" r="0.6" fill="currentColor" stroke="none"/><circle cx="10" cy="6" r="0.6" fill="currentColor" stroke="none"/><circle cx="13" cy="6" r="0.6" fill="currentColor" stroke="none"/><circle cx="7" cy="9.5" r="0.6" fill="currentColor" stroke="none"/><circle cx="10" cy="9.5" r="0.6" fill="currentColor" stroke="none"/><circle cx="13" cy="9.5" r="0.6" fill="currentColor" stroke="none"/><line x1="8" y1="18" x2="8" y2="13"/><line x1="12" y1="18" x2="12" y2="13"/>',
  "file-text": '<path d="M5 2h7l4 4v12H5Z"/><path d="M12 2v4h4"/><line x1="7.5" y1="10" x2="14" y2="10"/><line x1="7.5" y1="13" x2="14" y2="13"/>',
  scale: '<line x1="10" y1="2" x2="10" y2="16"/><line x1="4" y1="5" x2="16" y2="5"/><path d="M4 5 2 9a2.2 2.2 0 0 0 4 0Z"/><path d="M16 5 14 9a2.2 2.2 0 0 0 4 0Z"/><line x1="6" y1="18" x2="14" y2="18"/>',
  "edit-3": '<path d="M13.4 3.6 16.4 6.6 7 16l-4 1 1-4Z"/>',
  "alert-triangle": '<path d="M10 2 18 17H2Z"/><line x1="10" y1="8" x2="10" y2="12"/><circle cx="10" cy="14.4" r="0.9" fill="currentColor" stroke="none"/>',
  "check-circle": '<circle cx="10" cy="10" r="8"/><path d="M6.3 10.3 9 13l5-6"/>',
  "chevron-right": '<path d="M7 3l7 7-7 7"/>',
  plus: '<line x1="10" y1="3" x2="10" y2="17"/><line x1="3" y1="10" x2="17" y2="10"/>',
  send: '<path d="M17 3 3 9.5l6 1.5 1.5 6Z"/><line x1="9" y1="11" x2="17" y2="3"/>',
  "message-circle": '<path d="M2 10a8 8 0 1 1 3 6.2L2 18l1.3-3.6A7.96 7.96 0 0 1 2 10Z"/>',
  megaphone: '<path d="M3 8v4l4 1 9 3V4L7 7Z"/><path d="M7 13v3a2 2 0 0 0 4 0v-2"/>',
  close: '<line x1="5" y1="5" x2="15" y2="15"/><line x1="15" y1="5" x2="5" y2="15"/>',
};

function icon(name, extraClass) {
  const inner = ICON_PATHS[name] || ICON_PATHS["file-text"];
  const cls = extraClass ? `icon ${extraClass}` : "icon";
  return `<svg class="${cls}" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${inner}</svg>`;
}

const TOOL_ICON = {
  get_order: "package", get_ticket: "ticket", get_account: "building",
  search_policy_documents: "file-text", create_action: "megaphone",
};
