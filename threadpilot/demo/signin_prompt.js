// Part A of the demo recording: the workspace key is already in this tab (a placeholder; the offline replay checks no key)
// and no name is, so the app's own sign-in box opens, the key masked, and the recording types the name on camera.
try { sessionStorage.setItem('threadpilot-access:' + location.origin, 'offline-replay'); } catch {}
