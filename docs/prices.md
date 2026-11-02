# Supported models and prices

Every model Tokenmeter has a checked price for, generated from the tables in
`pricing/` by `python3 tokenmeter.py --list-prices --markdown`. US dollars per
million tokens, standard tier. A model not listed here is still priced, by the
online lookup at startup, and labelled as looked up rather than checked.

## Anthropic

Source: <https://platform.claude.com/docs/en/about-claude/pricing>. Last verified 27 Oct 2026, checked against the published page and against real usage.

| Model | Input | Cached input | Cache write | Output | Also |
|---|---:|---:|---:|---:|---|
| `claude-fable-5-1` | $10 | $0.25 | $12.50 | $50 | 1-hour cache write $20 |
| `claude-mythos-5-1` | $10 | $0.25 | $12.50 | $50 | 1-hour cache write $20 |
| `claude-fable-5` | $10 | $1 | $12.50 | $50 | 1-hour cache write $20 |
| `claude-mythos-5` | $10 | $1 | $12.50 | $50 | 1-hour cache write $20 |
| `claude-opus-5-5` | $4 | $0.20 | $5 | $20 | 1-hour cache write $8; fast $8 / $40 |
| `claude-opus-5` | $5 | $0.50 | $6.25 | $25 | 1-hour cache write $10; fast $10 / $50 |
| `claude-opus-4-8` | $5 | $0.50 | $6.25 | $25 | 1-hour cache write $10; fast $10 / $50 |
| `claude-opus-4-7` | $5 | $0.50 | $6.25 | $25 | 1-hour cache write $10 |
| `claude-opus-4-6` | $5 | $0.50 | $6.25 | $25 | 1-hour cache write $10 |
| `claude-sonnet-5` | $2 | $0.20 | $2.50 | $10 | 1-hour cache write $4 |
| `claude-sonnet-5-5` | $2 | $0.20 | $2.50 | $10 | until 2026-10-07; 1-hour cache write $4 |
| `claude-sonnet-5-5` | $2 | $0.10 | $2.50 | $10 | from 2026-10-07; 1-hour cache write $4 |
| `claude-sonnet-4-6` | $3 | $0.30 | $3.75 | $15 | 1-hour cache write $6 |
| `claude-haiku-5-5` | $0.10 | $0.01 | $0.125 | $0.50 | 1-hour cache write $0.20; over 100K prompt tokens: input x5, output x5 |
| `claude-haiku-4-5` | $1 | $0.10 | $1.25 | $5 | 1-hour cache write $2 |
| `claude-opus-4-5` | $5 | $0.50 | $6.25 | $25 | 1-hour cache write $10 |
| `claude-opus-4-1` | $15 | $1.50 | $18.75 | $75 | 1-hour cache write $30; retirement 2026-08-05, kept at the last published price |
| `claude-opus-4` | $15 | $1.50 | $18.75 | $75 | 1-hour cache write $30; retirement 2026-06-15, kept at the last published price |
| `claude-sonnet-4-5` | $3 | $0.30 | $3.75 | $15 | 1-hour cache write $6 |
| `claude-sonnet-4` | $3 | $0.30 | $3.75 | $15 | 1-hour cache write $6; retirement 2026-06-15, kept at the last published price |
| `claude-haiku-3-5` | $0.80 | $0.08 | $1 | $4 | 1-hour cache write $1.60; retirement 2026-02-19, kept at the last published price; also claude-3-5-haiku, claude-3-5-haiku-20241022, claude-3-5-haiku-latest |
| `claude-3-7-sonnet` | $3 | $0.30 | $3.75 | $15 | 1-hour cache write $6; retirement 2026-02-19, kept at the last published price |
| `claude-3-5-sonnet` | $3 | $0.30 | $3.75 | $15 | 1-hour cache write $6; retirement 2025-10-28, kept at the last published price; also claude-3-5-sonnet-latest |
| `claude-3-opus` | $15 | $1.50 | $18.75 | $75 | 1-hour cache write $30; retirement 2026-01-05, kept at the last published price; also claude-3-opus-latest |
| `claude-3-haiku` | $0.25 | $0.03 | $0.30 | $1.25 | 1-hour cache write $0.50; retirement 2026-04-20, kept at the last published price |
| `claude-3-sonnet` | $3 | - | - | $15 | retirement 2025-07-21, kept at the last published price |
| `claude-2.1` | $8 | - | - | $24 | retirement 2025-07-21, kept at the last published price |
| `claude-2.0` | $8 | - | - | $24 | retirement 2025-07-21, kept at the last published price |

## OpenAI

Source: <https://developers.openai.com/api/docs/pricing>. Last verified 27 Oct 2026, checked against the published page; not yet against a real bill.

| Model | Input | Cached input | Cache write | Output | Also |
|---|---:|---:|---:|---:|---|
| `gpt-6-astra` | $10 | $1 | $12.50 | $50 | until 2026-10-20; over 272K prompt tokens: input x2, output x1.5; fast $20 / $100 |
| `gpt-6-astra` | $10 | $1 | $12.50 | $50 | from 2026-10-20; 1-hour cache write $25; over 272K prompt tokens: input x2, output x1.5; fast $20 / $100 |
| `gpt-6.1-sol` | $2 | $0.10 | $2.50 | $10 | until 2026-10-20; over 272K prompt tokens: input x2, output x1.5; fast $4 / $20 |
| `gpt-6.1-sol` | $2 | $0.10 | $2.50 | $10 | from 2026-10-20; 1-hour cache write $5; over 272K prompt tokens: input x2, output x1.5; fast $4 / $20 |
| `gpt-6.1-terra` | $1 | $0.05 | $1.25 | $5 | 1-hour cache write $2.50; over 272K prompt tokens: input x2, output x1.5; fast $2 / $10 |
| `gpt-6-sol` | $2 | $0.20 | $2.50 | $10 | until 2026-10-20; over 272K prompt tokens: input x2, output x1.5; fast $4 / $20 |
| `gpt-6-sol` | $2 | $0.20 | $2.50 | $10 | from 2026-10-20; 1-hour cache write $5; over 272K prompt tokens: input x2, output x1.5; fast $4 / $20 |
| `gpt-6-luna` | $0.10 | $0.01 | $0.125 | $0.50 | until 2026-10-20; over 272K prompt tokens: input x2, output x1.5; fast $0.20 / $1 |
| `gpt-6-luna` | $0.10 | $0.01 | $0.125 | $0.50 | from 2026-10-20; 1-hour cache write $0.25; over 272K prompt tokens: input x2, output x1.5; fast $0.20 / $1 |
| `gpt-5.6-sol` | $5 | $0.50 | $6.25 | $30 | until 2026-08-21; over 272K prompt tokens: input x2, output x1.5; fast $10 / $60; also gpt-daybreak-blue-latest |
| `gpt-5.6-sol` | $4 | $0.40 | $5 | $20 | from 2026-08-21; over 272K prompt tokens: input x2, output x1.5; fast $8 / $40; also gpt-daybreak-blue-latest |
| `gpt-5.6-sol` | $4 | $0.40 | $5 | $20 | from 2026-10-20; 1-hour cache write $10; over 272K prompt tokens: input x2, output x1.5; fast $8 / $40; also gpt-daybreak-blue-latest |
| `gpt-5.6-terra` | $2.50 | $0.25 | $3.125 | $15 | until 2026-07-30; over 272K prompt tokens: input x2, output x1.5; fast $5 / $30 |
| `gpt-5.6-terra` | $2 | $0.20 | $2.50 | $12 | from 2026-07-30; over 272K prompt tokens: input x2, output x1.5; fast $4 / $24 |
| `gpt-5.6-terra` | $2 | $0.20 | $2.50 | $12 | from 2026-10-20; 1-hour cache write $5; over 272K prompt tokens: input x2, output x1.5; fast $4 / $24 |
| `gpt-5.6-luna` | $1 | $0.10 | $1.25 | $6 | until 2026-07-30; over 272K prompt tokens: input x2, output x1.5; fast $2 / $12 |
| `gpt-5.6-luna` | $0.20 | $0.02 | $0.25 | $1.20 | from 2026-07-30; over 272K prompt tokens: input x2, output x1.5; fast $0.40 / $2.40 |
| `gpt-5.6-luna` | $0.20 | $0.02 | $0.25 | $1.20 | from 2026-10-20; 1-hour cache write $0.50; over 272K prompt tokens: input x2, output x1.5; fast $0.40 / $2.40 |
| `gpt-5.5` | $5 | $0.50 | - | $30 | over 272K prompt tokens: input x2, output x1.5; fast $12.50 / $75 |
| `gpt-5.5-pro` | $30 | - | - | $180 | over 272K prompt tokens: input x2, output x1.5 |
| `gpt-5.4` | $2.50 | $0.25 | - | $15 | over 272K prompt tokens: input x2, output x1.5; fast $5 / $30 |
| `gpt-5.4-pro` | $30 | - | - | $180 | over 272K prompt tokens: input x2, output x1.5 |
| `gpt-5.4-mini` | $0.75 | $0.075 | - | $4.50 | fast $1.50 / $9 |
| `gpt-5.4-nano` | $0.20 | $0.02 | - | $1.25 |  |
| `gpt-5.3-codex` | $1.75 | $0.175 | - | $14 | fast $3.50 / $28 |
| `gpt-5.2-codex` | $1.75 | $0.175 | - | $14 | fast $3.50 / $28; retirement 2026-07-23, kept at the last published price |
| `gpt-5.1-codex-max` | $1.25 | $0.125 | - | $10 | fast $2.50 / $20; retirement 2026-07-23, kept at the last published price |
| `gpt-5.1-codex` | $1.25 | $0.125 | - | $10 | fast $2.50 / $20; retirement 2026-07-23, kept at the last published price |
| `gpt-5.1-codex-mini` | $0.25 | $0.025 | - | $2 | retirement 2026-07-23, kept at the last published price |
| `gpt-5-codex` | $1.25 | $0.125 | - | $10 | fast $2.50 / $20; retirement 2026-07-23, kept at the last published price |
| `codex-mini-latest` | $1.50 | $0.375 | - | $6 | retirement 2026-02-12, kept at the last published price |
| `gpt-5.2` | $1.75 | $0.175 | - | $14 | fast $3.50 / $28 |
| `gpt-5.2-pro` | $21 | - | - | $168 |  |
| `gpt-5.1` | $1.25 | $0.125 | - | $10 | fast $2.50 / $20 |
| `gpt-5` | $1.25 | $0.125 | - | $10 | fast $2.50 / $20 |
| `gpt-5-mini` | $0.25 | $0.025 | - | $2 | fast $0.45 / $3.60 |
| `gpt-5-nano` | $0.05 | $0.005 | - | $0.40 |  |
| `gpt-5-pro` | $15 | - | - | $120 |  |
| `gpt-4.1` | $2 | $0.50 | - | $8 | fast $3.50 / $14 |
| `gpt-4.1-mini` | $0.40 | $0.10 | - | $1.60 | fast $0.70 / $2.80 |
| `gpt-4.1-nano` | $0.10 | $0.025 | - | $0.40 | fast $0.20 / $0.80; retirement 2026-10-23, kept at the last published price |
| `gpt-4o` | $2.50 | $1.25 | - | $10 | fast $4.25 / $17 |
| `gpt-4o-2024-05-13` | $5 | - | - | $15 | fast $8.75 / $26.25; retirement 2026-10-23, kept at the last published price |
| `gpt-4o-mini` | $0.15 | $0.075 | - | $0.60 | fast $0.25 / $1 |
| `o3` | $2 | $0.50 | - | $8 | fast $3.50 / $14 |
| `o3-pro` | $20 | - | - | $80 |  |
| `o4-mini` | $1.10 | $0.275 | - | $4.40 | fast $2 / $8; retirement 2026-10-23, kept at the last published price |
| `o3-mini` | $1.10 | $0.55 | - | $4.40 | retirement 2026-10-23, kept at the last published price |
| `o1` | $15 | $7.50 | - | $60 | retirement 2026-10-23, kept at the last published price |
| `o1-pro` | $150 | - | - | $600 | retirement 2026-10-23, kept at the last published price |
| `gpt-5.6-cyber` | $12.50 | $1.25 | $15.625 | $75 | until 2026-10-20; also gpt-daybreak-red-latest |
| `gpt-5.6-cyber` | $12.50 | $1.25 | $15.625 | $75 | from 2026-10-20; 1-hour cache write $31.25; also gpt-daybreak-red-latest |
| `gpt-5.5-cyber` | $12.50 | $1.25 | - | $75 |  |
| `gpt-6-rosalind` | $15 | $1.50 | $18.75 | $75 | 1-hour cache write $37.50; over 272K prompt tokens: input x2, output x1.5 |
| `gpt-6-astra-law` | $10 | $1 | - | $50 |  |
| `gpt-rosalind-research` | $5 | $0.50 | - | $25 |  |
| `gpt-rosalind-discovery` | $5 | $0.50 | - | $25 |  |
| `chat-latest` | $5 | $0.50 | - | $30 |  |
| `gpt-5-search-api` | $1.25 | $0.125 | - | $10 |  |
| `gpt-4-turbo-2024-04-09` | $10 | - | - | $30 | retirement 2026-10-23, kept at the last published price; also gpt-4-turbo, gpt-4-turbo-completions |
| `gpt-4-0613` | $30 | - | - | $60 | retirement 2026-10-23, kept at the last published price; also gpt-4, gpt-4-0613-completions, gpt-4-completions |
| `gpt-3.5-turbo` | $0.50 | - | - | $1.50 | retirement 2026-10-23, kept at the last published price |
| `gpt-3.5-turbo-0125` | $0.50 | - | - | $1.50 | retirement 2026-10-23, kept at the last published price; also gpt-3.5-turbo-completions |
| `gpt-4-1106-preview` | $10 | - | - | $30 | retirement 2026-10-23, kept at the last published price |
| `gpt-5-chat-latest` | $1.25 | $0.125 | - | $10 | retirement 2026-07-23, kept at the last published price |
| `gpt-5.1-chat-latest` | $1.25 | $0.125 | - | $10 | retirement 2026-07-23, kept at the last published price |
| `o3-deep-research` | $10 | $2.50 | - | $40 | retirement 2026-07-23, kept at the last published price |
| `o4-mini-deep-research` | $2 | $0.50 | - | $8 | retirement 2026-07-23, kept at the last published price |
| `computer-use-preview` | $3 | - | - | $12 | retirement 2026-07-23, kept at the last published price |
| `gpt-4o-search-preview` | $2.50 | - | - | $10 | retirement 2026-07-23, kept at the last published price |
| `gpt-4o-mini-search-preview` | $0.15 | - | - | $0.60 | retirement 2026-07-23, kept at the last published price |
| `gpt-5.2-chat-latest` | $1.75 | $0.175 | - | $14 | retirement 2026-08-10, kept at the last published price |
| `gpt-5.3-chat-latest` | $1.75 | $0.175 | - | $14 | retirement 2026-08-10, kept at the last published price |
| `gpt-3.5-turbo-1106` | $1 | - | - | $2 | retirement 2026-09-28, kept at the last published price |
| `gpt-3.5-turbo-instruct` | $1.50 | - | - | $2 | retirement 2026-09-28, kept at the last published price |
| `davinci-002` | $2 | - | - | $2 | retirement 2026-09-28, kept at the last published price |
| `babbage-002` | $0.40 | - | - | $0.40 | retirement 2026-09-28, kept at the last published price |
| `gpt-4-0314` | $30 | - | - | $60 | retirement 2026-03-26, kept at the last published price |
| `gpt-4-0125-preview` | $10 | - | - | $30 | retirement 2026-03-26, kept at the last published price; also gpt-4-turbo-preview, gpt-4-turbo-preview-completions |
| `chatgpt-4o-latest` | $5 | - | - | $15 | retirement 2026-02-17, kept at the last published price |
| `o1-mini` | $1.10 | $0.55 | - | $4.40 | retirement 2025-10-27, kept at the last published price |
| `o1-preview` | $15 | $7.50 | - | $60 | retirement 2025-07-28, kept at the last published price |
| `gpt-4.5-preview` | $75 | $37.50 | - | $150 | retirement 2025-07-14, kept at the last published price |
| `gpt-4-32k` | $60 | - | - | $120 | retirement 2025-06-06, kept at the last published price; also gpt-4-32k-0314, gpt-4-32k-0613 |

## Google

Source: <https://aistudio.google.com/docs/pricing>. Last verified 2 Nov 2026, checked against the published page; not yet against a real bill.

| Model | Input | Cached input | Cache write | Output | Also |
|---|---:|---:|---:|---:|---|
| `gemini-4-argon` | $2 | $0.10 | - | $10 | until 2026-12-01; fast $3.60 / $18 |
| `gemini-4-argon` | $4 | $0.20 | - | $20 | from 2026-12-01; fast $7.20 / $36 |
| `gemini-3.8-flash` | $0.75 | $0.075 | - | $3.75 | until 2027-01-01; fast $1.35 / $6.75 |
| `gemini-3.8-flash` | $1.50 | $0.15 | - | $7.50 | from 2027-01-01; fast $2.70 / $13.50 |
| `gemini-3.7-flash` | $0.75 | $0.075 | - | $3.75 | until 2027-01-01; fast $1.35 / $6.75; retirement 2026-10-08, kept at the last published price |
| `gemini-3.7-flash` | $1.50 | $0.15 | - | $7.50 | from 2027-01-01; fast $2.70 / $13.50; retirement 2026-10-08, kept at the last published price |
| `gemini-3.6-flash` | $0.75 | $0.075 | - | $3.75 | until 2027-01-01; fast $1.35 / $6.75 |
| `gemini-3.6-flash` | $1.50 | $0.15 | - | $7.50 | from 2027-01-01; fast $2.70 / $13.50 |
| `gemini-3.5-flash` | $1.50 | $0.15 | - | $9 | fast $2.70 / $16.20; retirement 2026-10-08, kept at the last published price |
| `gemini-3.5-flash-lite` | $0.30 | $0.03 | - | $2.50 | fast $0.54 / $4.50 |
| `gemini-3.1-flash-lite` | $0.25 | $0.025 | - | $1.50 | fast $0.45 / $2.70 |
| `gemini-3.1-pro-preview` | $2 | $0.20 | - | $12 | over 200K prompt tokens: input x2, output x1.5; fast $3.60 / $21.60; also gemini-3.1-pro-preview-customtools |
| `gemini-3-flash-preview` | $0.50 | $0.05 | - | $3 | fast $0.90 / $5.40 |
| `gemini-2.5-pro` | $1.25 | $0.125 | - | $10 | over 200K prompt tokens: input x2, output x1.5; fast $2.25 / $18 |
| `gemini-2.5-flash` | $0.30 | $0.03 | - | $2.50 | fast $0.54 / $4.50 |
| `gemini-2.5-flash-lite` | $0.10 | $0.01 | - | $0.40 | fast $0.18 / $0.72 |
| `gemini-2.5-computer-use-preview-10-2025` | $1.25 | - | - | $10 | over 200K prompt tokens: input x2, output x1.5; retirement 2026-07-28, kept at the last published price |
| `gemini-3-pro-preview` | $2 | $0.20 | - | $12 | over 200K prompt tokens: input x2, output x1.5; retirement 2026-03-09, kept at the last published price |
| `gemini-3.1-flash-lite-preview` | $0.25 | $0.025 | - | $1.50 | fast $0.45 / $2.70; retirement 2026-05-25, kept at the last published price |
| `gemini-2.0-flash` | $0.10 | $0.025 | - | $0.40 | retirement 2026-06-01, kept at the last published price |
| `gemini-2.0-flash-lite` | $0.075 | - | - | $0.30 | retirement 2026-06-01, kept at the last published price |
| `gemini-2.5-flash-lite-preview-09-2025` | $0.10 | $0.01 | - | $0.40 | retirement 2026-03-31, kept at the last published price |
| `gemini-2.5-flash-preview-09-2025` | $0.30 | $0.03 | - | $2.50 | retirement 2026-02-17, kept at the last published price; also gemini-2.5-flash-preview-09-25 |
| `gemini-2.5-flash-lite-preview-06-17` | $0.10 | $0.025 | - | $0.40 | retirement 2025-11-18, kept at the last published price; also gemini-2.5-flash-lite-06-17 |
| `gemini-2.5-flash-preview-05-20` | $0.15 | $0.0375 | - | $3.50 | retirement 2025-11-18, kept at the last published price |
| `gemini-2.5-flash-preview-04-17` | $0.15 | $0.0375 | - | $3.50 | retirement 2025-07-15, kept at the last published price |
| `gemini-2.5-pro-preview-06-05` | $1.25 | $0.31 | - | $10 | over 200K prompt tokens: input x2, output x1.5; retirement 2025-12-02, kept at the last published price |
| `gemini-2.5-pro-preview-05-06` | $1.25 | $0.31 | - | $10 | over 200K prompt tokens: input x2, output x1.5; retirement 2025-12-02, kept at the last published price |
| `gemini-2.5-pro-preview-03-25` | $1.25 | $0.31 | - | $10 | over 200K prompt tokens: input x2, output x1.5; retirement 2025-12-02, kept at the last published price |
| `gemini-1.5-pro` | $1.25 | $0.3125 | - | $5 | over 128K prompt tokens: input x2, output x2; retirement 2025-09-29, kept at the last published price |
| `gemini-1.5-flash` | $0.075 | $0.01875 | - | $0.30 | over 128K prompt tokens: input x2, output x2; retirement 2025-09-29, kept at the last published price |
| `gemini-1.5-flash-8b` | $0.0375 | $0.01 | - | $0.15 | over 128K prompt tokens: input x2, output x2; retirement 2025-09-29, kept at the last published price |
| `gemini-1.0-pro` | $0.50 | - | - | $1.50 | retirement 2025-02-18, kept at the last published price |

## xAI

Source: <https://docs.x.ai/developers/pricing>. Last verified 26 Sep 2026, checked against the published page; not yet against a real bill.

| Model | Input | Cached input | Cache write | Output | Also |
|---|---:|---:|---:|---:|---|
| `grok-4.7` | $2 | $0.50 | - | $6 | over 200K prompt tokens: input x2, output x2; fast $4 / $12 |
| `grok-4.6` | $2 | $0.50 | - | $6 | over 200K prompt tokens: input x2, output x2; fast $4 / $12 |
| `grok-4.5` | $2 | $0.30 | - | $6 | over 200K prompt tokens: input x2, output x2; fast $4 / $12; also grok-4.5-latest, grok-build-latest |
| `grok-4.3` | $1.25 | $0.20 | - | $2.50 | over 200K prompt tokens: input x2, output x2; fast $2.50 / $5; also grok-4.3-latest |
| `grok-4.20-0309-reasoning` | $1.25 | $0.20 | - | $2.50 | over 200K prompt tokens: input x2, output x2; fast $2.50 / $5; also grok-4.20, grok-4.20-0309, grok-4.20-beta and 12 more |
| `grok-4.20-0309-non-reasoning` | $1.25 | $0.20 | - | $2.50 | over 200K prompt tokens: input x2, output x2; fast $2.50 / $5; also grok-4.20-beta-0309-non-reasoning, grok-4.20-beta-latest-non-reasoning, grok-4.20-beta-non-reasoning and 5 more |
| `grok-4.20-multi-agent-0309` | $1.25 | $0.20 | - | $2.50 | over 200K prompt tokens: input x2, output x2; fast $2.50 / $5; also grok-4.20-multi-agent, grok-4.20-multi-agent-beta-0309, grok-4.20-multi-agent-beta-latest and 3 more |
| `grok-build-0.1` | $1 | $0.20 | - | $2 | over 200K prompt tokens: input x2, output x2; fast $2 / $4; also grok-code-fast, grok-code-fast-1, grok-code-fast-1-0825 |

## DeepSeek

Source: <https://api-docs.deepseek.com/quick_start/pricing>. Last verified 2 Nov 2026, checked against the published page; not yet against a real bill.

| Model | Input | Cached input | Cache write | Output | Also |
|---|---:|---:|---:|---:|---|
| `deepseek-flash` | $0.30 | $0.006 | - | $1.20 | half price off-peak; also deepseek-v4-flash, deepseek-v4-flash-vision-exp |
| `deepseek-v4-pro` | $1.32 | $0.044 | - | $3.96 | half price off-peak |

## Mistral

Source: <https://docs.mistral.ai/inference/pricing>. Last verified 2 Nov 2026, checked against the published page; not yet against a real bill.

| Model | Input | Cached input | Cache write | Output | Also |
|---|---:|---:|---:|---:|---|
| `mistral-large-4` | $0.70 | $0.07 | - | $2.10 | also mistral-large-4-0 |
| `mistral-large-2512` | $0.50 | $0.05 | - | $1.50 | retirement 2027-04-30, kept at the last published price |
| `mistral-medium-3-5` | $1.50 | $0.15 | - | $7.50 | retirement 2027-04-30, kept at the last published price |
| `mistral-small-2603` | $0.15 | $0.015 | - | $0.60 |  |
| `ministral-14b-2512` | $0.20 | $0.02 | - | $0.20 |  |
| `ministral-8b-2512` | $0.15 | $0.015 | - | $0.15 |  |
| `ministral-3b-2512` | $0.10 | $0.01 | - | $0.10 |  |
| `codestral-2508` | $0.30 | $0.03 | - | $0.90 |  |
| `zai-glm-5-3` | $1.40 | $0.14 | - | $4.40 |  |
| `zai-glm-5-2` | $1.40 | $0.14 | - | $4.40 | retirement 2026-10-31, kept at the last published price |

## Moonshot

Source: <https://platform.kimi.ai/docs/pricing/chat>. Last verified 27 Oct 2026, checked against the published page; not yet against a real bill.

| Model | Input | Cached input | Cache write | Output | Also |
|---|---:|---:|---:|---:|---|
| `kimi-k3.1-pro` | $2 | $0.20 | $2 | $10 | 1-hour cache write $4 |
| `kimi-k3.1-pro-highspeed` | $4 | $0.20 | $4 | $20 | 1-hour cache write $8 |
| `kimi-k3` | $3 | $0.30 | $3 | $15 | 1-hour cache write $6 |
| `kimi-k2.7-code` | $0.95 | $0.19 | - | $4 |  |
| `kimi-k2.7-code-highspeed` | $1.90 | $0.38 | - | $8 |  |
| `kimi-k2.6` | $0.95 | $0.16 | - | $4 |  |

## Z.ai

Source: <https://docs.z.ai/guides/overview/pricing>. Last verified 27 Oct 2026, checked against the published page; not yet against a real bill.

| Model | Input | Cached input | Cache write | Output | Also |
|---|---:|---:|---:|---:|---|
| `glm-5.3` | $1.40 | $0.26 | - | $4.40 |  |
| `glm-5.3-flash` | $0.15 | $0.03 | - | $0.50 |  |
| `glm-5.3-flashx` | $0.37 | $0.075 | - | $1.25 |  |
| `glm-5.3-flashx-legal` | $0.37 | $0.075 | - | $1.25 |  |
| `glm-5.2` | $1.40 | $0.26 | - | $4.40 |  |
| `glm-5.1` | $1.40 | $0.26 | - | $4.40 |  |
| `glm-5` | $1 | $0.20 | - | $3.20 |  |
| `glm-4.7` | $0.60 | $0.11 | - | $2.20 |  |
| `glm-4.7-flashx` | $0.07 | $0.01 | - | $0.40 |  |
| `glm-4.7-flash` | $0 | $0 | - | $0 |  |
| `glm-4.6` | $0.60 | $0.11 | - | $2.20 |  |
| `glm-4.5` | $0.60 | $0.11 | - | $2.20 |  |
| `glm-4.5-x` | $2.20 | $0.45 | - | $8.90 |  |
| `glm-4.5-air` | $0.20 | $0.03 | - | $1.10 |  |
| `glm-4.5-airx` | $1.10 | $0.22 | - | $4.50 |  |
| `glm-4.5-flash` | $0 | $0 | - | $0 |  |
| `glm-4-32b-0414-128k` | $0.10 | - | - | $0.10 |  |

## MiniMax

Source: <https://platform.minimax.io/docs/pricing/overview>. Last verified 2 Nov 2026, checked against the published page; not yet against a real bill.

| Model | Input | Cached input | Cache write | Output | Also |
|---|---:|---:|---:|---:|---|
| `MiniMax-M3.1-Flash` | $0.15 | $0.015 | - | $0.60 |  |
| `MiniMax-M3` | $0.30 | $0.06 | - | $1.20 | over 512K prompt tokens: input x2, output x2; fast $0.45 / $1.80 |

## Xiaomi MiMo

Source: <https://mimo.mi.com/docs/en-US/price/pay-as-you-go>. Last verified 2 Nov 2026, checked against the published page; not yet against a real bill.

| Model | Input | Cached input | Cache write | Output | Also |
|---|---:|---:|---:|---:|---|
| `mimo-v2.6-pro` | $0.435 | $0.0036 | - | $0.87 |  |
| `mimo-v2.6-flash` | $0.14 | $0.0028 | - | $0.28 |  |
| `mimo-v2.6-pro-ultraspeed` | $4.35 | $0.036 | - | $8.70 |  |
