# Embedded fonts

Latin-subset variable fonts, base64'd into the dashboard at render time so it
looks the same with no network. Both are freely licensed for this use.

| File | Family | Licence |
|---|---|---|
| `fraunces.woff2` | Fraunces (opsz, wght, SOFT, WONK axes) | SIL Open Font License 1.1 |
| `inter-tight.woff2` | Inter Tight (wght axis) | SIL Open Font License 1.1 |

The OFL permits embedding in a document. Keep this file with them so the
attribution travels too.

If these are deleted the dashboard still renders; `render_html` falls back to
the system serif and sans stacks.

Refresh them with the snippet in MAINTENANCE.md.
