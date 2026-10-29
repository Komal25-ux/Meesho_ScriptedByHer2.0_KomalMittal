// One conversation per browser tab. The backend keys every piece of
// cross-turn state (a draft awaiting approval, a return in progress, the
// product being discussed) and the agent-trace stream by this id, so two
// people using the demo at the same time never see or steer each other's
// chat. sessionStorage keeps it across a reload of the same tab and drops it
// when the tab closes; a new tab is a new conversation.
const STORAGE_KEY = 'sakhi.session_id';

export function newId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  // randomUUID needs a secure context (https or localhost). Same v4 layout
  // from getRandomValues, so the backend's pattern check still passes.
  const b = window.crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const hex = [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function loadSessionId() {
  try {
    const saved = window.sessionStorage.getItem(STORAGE_KEY);
    if (saved) return saved;
    const id = newId();
    window.sessionStorage.setItem(STORAGE_KEY, id);
    return id;
  } catch {
    // Storage blocked (private mode, embedded frame): still a valid id, it
    // just won't survive a reload.
    return newId();
  }
}

export const SESSION_ID = loadSessionId();
