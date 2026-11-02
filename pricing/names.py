"""Host and harness spellings of a model, mapped to the maker's table and id.

Data only: the engine's maker_name() in tokenmeter.py reads it. A key is
(harness, provider, model) exactly as a reader records the call, with "" for
the harness meaning any harness; the value is (table, id) in pricing/. Exact
matches only, and only the same model: an id that is not here is priced as
recorded, by its table or the online lookup, as before.

An entry never overrides a table: a call whose recorded table already lists
its id (exactly, by ALIASES or by SNAPSHOT) keeps that price. An entry whose
table is not in TABLES, or whose id that table does not list, is skipped.

Sources, read on 2 November 2026:
- Kimi Code: the reader records the model as sent, never the alias
  kimi-code/k3 (adapters/README.md, "Model id spellings", and
  adapters/kimi_code.py on the readers branch). Kimi Code's model page
  (kimi.com/code/docs, "Model Configuration") names each model id's
  version: k3.1-pro is K3.1 Pro, k3.1-pro-highspeed is K3.1 Pro Highspeed,
  k3 and k3-256k (its 256K context version) are K3, and
  kimi-for-coding-highspeed is K2.7 Code Highspeed. Those are the models
  Moonshot's API prices as kimi-k3.1-pro, kimi-k3.1-pro-highspeed, kimi-k3
  and kimi-k2.7-code-highspeed. A Kimi Code subscription is priced at
  Moonshot's API rate (the brief, decision 4). Keyed to the harness, so no
  other harness's bare "k3" is caught.
- OpenRouter: its model list (openrouter.ai/api/v1/models) and models.dev's
  "openrouter" provider, which is OpenCode's providerID, both list each id
  below. Each is "<maker's prefix>/<the maker's table id>" with a published
  weights repository on Hugging Face, so an open-weight model, priced at its
  maker's rate whoever served it (decision 4). OpenRouter's frontier models,
  those with no weights published, keep the host's price through the lookup.
"""

NAMES = {
    # Kimi Code, the model as sent in llm.request.
    ("kimi-code", "moonshot", "k3"): ("moonshot", "kimi-k3"),
    ("kimi-code", "moonshot", "k3-256k"): ("moonshot", "kimi-k3"),
    ("kimi-code", "moonshot", "k3.1-pro"): ("moonshot", "kimi-k3.1-pro"),
    ("kimi-code", "moonshot", "k3.1-pro-highspeed"): ("moonshot", "kimi-k3.1-pro-highspeed"),
    ("kimi-code", "moonshot", "kimi-for-coding-highspeed"): ("moonshot", "kimi-k2.7-code-highspeed"),

    # OpenRouter, open-weight models only, through any harness.
    ("", "openrouter", "moonshotai/kimi-k2.6"): ("moonshot", "kimi-k2.6"),
    ("", "openrouter", "moonshotai/kimi-k2.7-code"): ("moonshot", "kimi-k2.7-code"),
    ("", "openrouter", "moonshotai/kimi-k3"): ("moonshot", "kimi-k3"),
    ("", "openrouter", "z-ai/glm-4.5"): ("zai", "glm-4.5"),
    ("", "openrouter", "z-ai/glm-4.5-air"): ("zai", "glm-4.5-air"),
    ("", "openrouter", "z-ai/glm-4.6"): ("zai", "glm-4.6"),
    ("", "openrouter", "z-ai/glm-4.7"): ("zai", "glm-4.7"),
    ("", "openrouter", "z-ai/glm-4.7-flash"): ("zai", "glm-4.7-flash"),
    ("", "openrouter", "z-ai/glm-5"): ("zai", "glm-5"),
    ("", "openrouter", "z-ai/glm-5.1"): ("zai", "glm-5.1"),
    ("", "openrouter", "z-ai/glm-5.2"): ("zai", "glm-5.2"),
    ("", "openrouter", "z-ai/glm-5.3"): ("zai", "glm-5.3"),
    ("", "openrouter", "z-ai/glm-5.3-flash"): ("zai", "glm-5.3-flash"),
    ("", "openrouter", "deepseek/deepseek-v4-flash"): ("deepseek", "deepseek-v4-flash"),
    ("", "openrouter", "deepseek/deepseek-v4-flash-vision-exp"): ("deepseek", "deepseek-v4-flash-vision-exp"),
    ("", "openrouter", "deepseek/deepseek-v4-pro"): ("deepseek", "deepseek-v4-pro"),
    ("", "openrouter", "mistralai/ministral-3b-2512"): ("mistral", "ministral-3b-2512"),
    ("", "openrouter", "mistralai/ministral-8b-2512"): ("mistral", "ministral-8b-2512"),
    ("", "openrouter", "mistralai/ministral-14b-2512"): ("mistral", "ministral-14b-2512"),
    ("", "openrouter", "mistralai/mistral-small-2603"): ("mistral", "mistral-small-2603"),
    ("", "openrouter", "xiaomi/mimo-v2.6-flash"): ("mimo", "mimo-v2.6-flash"),
    ("", "openrouter", "xiaomi/mimo-v2.6-pro"): ("mimo", "mimo-v2.6-pro"),
    ("", "openrouter", "minimax/minimax-m3"): ("minimax", "MiniMax-M3"),
    ("", "openrouter", "minimax/minimax-m3.1-flash"): ("minimax", "MiniMax-M3.1-Flash"),
}
