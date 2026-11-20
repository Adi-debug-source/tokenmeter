# The repository's About box

Suggestions for the settings on the repository's GitHub page. Nothing here
changes them: they are set by hand, under the cog beside About and in
Settings.

## Description

> What your AI coding would have cost at API rates. Prices Claude Code, Codex and other agents' local logs, with a menu bar app, a status line and a dashboard. Your usage stays on your Mac.

That is 187 characters; GitHub allows 350. A shorter one, if it should fit
on one line of a search result (125 characters):

> What your AI coding would have cost at API rates: a menu bar app, status line and dashboard for Claude Code and other agents.

## Website

Leave it empty, or point it at the latest release:
`https://github.com/Adi-debug-source/tokenmeter/releases/latest`

## Topics

GitHub allows 20, in lower case with hyphens. In the order worth keeping if
some are dropped:

    claude-code
    llm
    cost-tracking
    token-usage
    api-pricing
    macos
    menu-bar-app
    statusline
    codex
    gemini-cli
    opencode
    anthropic
    openai
    ai-coding
    developer-tools
    cli
    dashboard
    python
    swift
    homebrew

The first five are what someone would search for; the harness and provider
names put it beside the tools it reads; the last few say what it is built
with.

## Social preview

`social-preview.png` in this folder, 1280 by 640, the size GitHub asks for.
Upload it under Settings, General, Social preview. It is what a link to the
repository shows on LinkedIn, Slack and X, in place of GitHub's default card.

It is drawn by `social_preview.swift`, as the app icon is drawn by
`costbar/icon.swift`, with the dashboard's own typefaces and colours and the
app icon. Its figures are the invented demo's, the ones in the README's menu
bar image, not anyone's usage. To draw it again after a change, from the
repository's top folder:

    swiftc -O -o /tmp/mkpreview docs/github/social_preview.swift -framework AppKit
    /tmp/mkpreview . docs/github/social-preview.png
    python3 docs/screenshots/shoot.py --plain docs/github/social-preview.png

## Also worth setting

- Tick **Releases** in the About box and untick **Packages** and
  **Deployments**, which are empty.
- Pin the repository on the profile page, since it is the one a visitor
  should see first.
