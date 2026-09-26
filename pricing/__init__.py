"""One price table per provider. See README.md in this folder before adding one.

Each module defines the same names: PROVIDER, NAME, SOURCE, VERIFIED_ON,
MEASURED, CACHE_WRITE_5M_MULT, CACHE_WRITE_1H_MULT, WEB_SEARCH_PER_1K,
SNAPSHOT, PRICES and FALLBACK_MODEL, and optionally ALIASES and
page_rates(), which reads the provider's own pricing page. The engine does
the arithmetic; these files hold the rates, the evidence for them, and how to
read the page they came from.
"""

from . import anthropic, deepseek, google, mistral, moonshot, openai, xai, zai

TABLES = {m.PROVIDER: m for m in (anthropic, openai, google, xai, deepseek, mistral, moonshot, zai)}
