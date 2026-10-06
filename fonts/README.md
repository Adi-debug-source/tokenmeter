# Embedded fonts

Latin-subset variable fonts, base64'd into the dashboard at render time so it
looks the same with no network. Both are freely licensed for this use.

| File | Family | Licence |
|---|---|---|
| `fraunces.woff2` | Fraunces (opsz, wght, SOFT, WONK axes) | SIL Open Font License 1.1, see `OFL-Fraunces.txt` |
| `inter-tight.woff2` | Inter Tight (wght axis) | SIL Open Font License 1.1, see `OFL-InterTight.txt` |

The OFL permits embedding in a document, and asks that the licence travel with
the fonts. The two licence files are the ones Google Fonts publishes with each
family, unchanged. Keep them and this file beside the fonts.

If these are deleted the dashboard still renders; `render_html` falls back to
the system serif and sans stacks.

Refresh them with the snippet in MAINTENANCE.md.
