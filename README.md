Prepared UI v4 to match a1.1.10 screenshot.

Key fixes vs v3:
- Removed time.sleep animation (non-blocking animation via st_autorefresh) to avoid 'SessionInfo not initialized' / Bad message format.
- Proper role names shown even when snap is minimal (merge snap with engine state).
- Cleaner control bar sizing.
