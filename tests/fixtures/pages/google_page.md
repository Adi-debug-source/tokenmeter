## Gemini 4 Argon  {% id="gemini-4-argon" %}

{% two-column-layout %}
  {% left-column class="center-vertically" %}
  *[`gemini-4-argon`](/docs/models/gemini-4-argon)*

  {% /left-column %}

  {% right-column class="center-vertically right-align" %}
  {% button href="https://aistudio.google.com/prompts/new_chat?model=gemini-4-argon" variant="ais" %}
  Try it in Google AI Studio

  {% /button %}

  {% /right-column %}

{% /two-column-layout %}

{% hr /%}

Our flagship reasoning model, built for complex software engineering, deep
mathematical and scientific problem solving, autonomous multi-step agents, and
long-decode generation up to 1M tokens.

{% callout type="note" %}
  Gemini 4 Argon is not available on the Free tier. Every token the model processes is counted and billed, including thinking tokens and internal tool system instructions and function declarations when using grounding.

{% /callout %}

{% tabs %}
  {% tab title="Standard" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $2.00 through November 30, 2026.   
  $4.00 starting December 1, 2026.

  ---

  * Output price (including thinking tokens)
  * Not available
  * $10.00 through November 30, 2026.   
  $20.00 starting December 1, 2026.

  ---

  * Context caching price
  * Not available
  * $0.10 through November 30, 2026.   
  $0.20 starting December 1, 2026.   
  Implicit caching only (explicit caching is not supported).

  ---

  * Grounding with Google Search{% sup %}*{% /sup %}
  * Not available
  * 5,000 free search requests per month (shared across all Gemini 3 and newer models),
  then $14 per 1,000 requests (subject to a [daily cap](/docs/pricing#pricing-for-tools) of 1,500 requests per day).

  ---

  * Grounding with Google Maps
  * Not available
  * 5,000 requests per month (free, shared across all Gemini 3 and newer models), then $14 / 1,000
  search queries.

  ---

  * Used to improve our products
  * Not available
  * [No](/docs/terms)
  {% /table %}

  {% sup %}*{% /sup %} A customer-submitted request to Gemini may result in one or
    more queries to Google Search. You will be charged for each individual search
    query performed.
    

  {% /tab %}

  {% tab title="Batch" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $1.00 through November 30, 2026.   
  $2.00 starting December 1, 2026.

  ---

  * Output price (including thinking tokens)
  * Not available
  * $5.00 through November 30, 2026.   
  $10.00 starting December 1, 2026.

  ---

  * Context caching price
  * Not available
  * $0.05 through November 30, 2026.   
  $0.10 starting December 1, 2026.   
  Implicit caching only (explicit caching is not supported).

  ---

  * Used to improve our products
  * Not available
  * [No](/docs/terms)
  {% /table %}

  {% sup %}*{% /sup %} A customer-submitted request to Gemini may result in one or
    more queries to Google Search. You will be charged for each individual search
    query performed.
    

  {% /tab %}

  {% tab title="Flex" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $1.00 through November 30, 2026.   
  $2.00 starting December 1, 2026.

  ---

  * Output price (including thinking tokens)
  * Not available
  * $5.00 through November 30, 2026.   
  $10.00 starting December 1, 2026.

  ---

  * Context caching price
  * Not available
  * $0.05 through November 30, 2026.   
  $0.10 starting December 1, 2026.   
  Implicit caching only (explicit caching is not supported).

  ---

  * Used to improve our products
  * Not available
  * [No](/docs/terms)
  {% /table %}

  {% sup %}*{% /sup %} A customer-submitted request to Gemini may result in one or
    more queries to Google Search. You will be charged for each individual search
    query performed.
    

  {% /tab %}

  {% tab title="Priority" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $3.60 through November 30, 2026.   
  $7.20 starting December 1, 2026.

  ---

  * Output price (including thinking tokens)
  * Not available
  * $18.00 through November 30, 2026.   
  $36.00 starting December 1, 2026.

  ---

  * Context caching price
  * Not available
  * $0.18 through November 30, 2026.   
  $0.36 starting December 1, 2026.   
  Implicit caching only (explicit caching is not supported).

  ---

  * Grounding with Google Search{% sup %}*{% /sup %}
  * Not available
  * 5,000 free search requests per month (shared across all Gemini 3 and newer models),
  then $14 per 1,000 requests (subject to a [daily cap](/docs/pricing#pricing-for-tools) of 1,500 requests per day).

  ---

  * Grounding with Google Maps
  * Not available
  * 5,000 requests per month (free, shared across all Gemini 3 and newer models), then $14 / 1,000
  search queries.

  ---

  * Used to improve our products
  * Not available
  * [No](/docs/terms)
  {% /table %}

  {% sup %}*{% /sup %} A customer-submitted request to Gemini may result in one or
    more queries to Google Search. You will be charged for each individual search
    query performed.
    

  {% /tab %}

  {% tab title="Contributor" %}
  {% callout type="note" %}
  The Gemini API Contributor Tier is offered as a private preview on an
      invite-only basis. Speed and reliability are equivalent to
      [Standard Tier inference](/docs/optimization). Eligible users will be invited by
      email and see a callout in AI Studio.

  {% /callout %}

  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD{% sup %}*{% /sup %}

  ---

  * Input price
  * Not available
  * $1.00

  ---

  * Output price (including thinking tokens)
  * Not available
  * $5.00

  ---

  * Context caching price
  * Not available
  * $0.05   
  Implicit caching only (explicit caching is not supported).

  ---

  * Used to improve our products
  * Not available
  * [Yes](/docs/logs-policy#contributor-tier)
  {% /table %}

  {% sup %}*{% /sup %} Discounts and model availability are subject to change.
    

  {% /tab %}

{% /tabs %}

## Gemini 3.5 Flash-Lite  {% id="gemini-3.5-flash-lite" %}

{% two-column-layout %}
  {% left-column %}
  *[`gemini-3.5-flash-lite`](/docs/models/gemini-3.5-flash-lite)*

  {% /left-column %}

  {% right-column class="center-vertically right-align" %}
  {% button href="https://aistudio.google.com/prompts/new_chat?model=gemini-3.5-flash-lite" variant="ais" %}
  Try it in Google AI Studio

  {% /button %}

  {% /right-column %}

{% /two-column-layout %}

{% hr /%}

A cost-efficient model, optimized for high-volume agentic tasks, translation,
and simple data processing.

{% tabs %}
  {% tab title="Standard" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Free of charge
  * $0.30 (text / image / video / audio)

  ---

  * Output price (including thinking tokens)
  * Free of charge
  * $2.50

  ---

  * Context caching price
  * Not available
  * $0.03    
  $1.00 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search{% sup %}*{% /sup %}
  * Not available{% sup %}**{% /sup %}
  * 5,000 free search requests per month (shared across all Gemini 3 and newer models),
  then $14 per 1,000 requests (subject to a [daily cap](/docs/pricing#pricing-for-tools) of 1,500 requests per day).

  ---

  * Grounding with Google Maps
  * Not available{% sup %}**{% /sup %}
  * 5,000 requests per month (free, shared across all Gemini 3 and newer models), then $14 / 1,000
  search queries.

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% sup %}*{% /sup %} A customer-submitted request to Gemini may result in one or
    more queries to Google Search. You will be charged for each individual search
    query performed.

  {% sup %}**{% /sup %} Can be tested in Google AI Studio.
    

  {% /tab %}

  {% tab title="Batch" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Free of charge
  * $0.15 (text / image / video / audio)

  ---

  * Output price (including thinking tokens)
  * Free of charge
  * $1.25

  ---

  * Context caching price
  * Not available
  * $0.015    
  $1.00 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search{% sup %}*{% /sup %}
  * Not available{% sup %}**{% /sup %}
  * 5,000 free search requests per month (shared across all Gemini 3 and newer models),
  then $14 per 1,000 requests (subject to a [daily cap](/docs/pricing#pricing-for-tools) of 1,500 requests per day).

  ---

  * Grounding with Google Maps
  * Not available{% sup %}**{% /sup %}
  * 5,000 requests per month (free, shared across all Gemini 3 and newer models), then $14 / 1,000
  search queries.

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% sup %}*{% /sup %} A customer-submitted request to Gemini may result in one or
    more queries to Google Search. You will be charged for each individual search
    query performed.

  {% sup %}**{% /sup %} Can be tested in Google AI Studio.
    

  {% /tab %}

  {% tab title="Flex" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $0.15 (text / image / video / audio)

  ---

  * Output price (including thinking tokens)
  * Not available
  * $1.25

  ---

  * Context caching price
  * Not available
  * $0.02    
  $1.00 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search{% sup %}*{% /sup %}
  * Not available{% sup %}**{% /sup %}
  * 5,000 free search requests per month (shared across all Gemini 3 and newer models),
  then $14 per 1,000 requests (subject to a [daily cap](/docs/pricing#pricing-for-tools) of 1,500 requests per day).

  ---

  * Grounding with Google Maps
  * Not available{% sup %}**{% /sup %}
  * 5,000 requests per month (free, shared across all Gemini 3 and newer models), then $14 / 1,000
  search queries.

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% sup %}*{% /sup %} A customer-submitted request to Gemini may result in one or
    more queries to Google Search. You will be charged for each individual search
    query performed.

  {% sup %}**{% /sup %} Can be tested in Google AI Studio.
    

  {% /tab %}

  {% tab title="Priority" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Free of charge
  * $0.54 (text / image / video / audio)

  ---

  * Output price (including thinking tokens)
  * Free of charge
  * $4.50

  ---

  * Context caching price
  * Not available
  * $0.05    
  $1.00 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search{% sup %}*{% /sup %}
  * Not available{% sup %}**{% /sup %}
  * 5,000 free search requests per month (shared across all Gemini 3 and newer models),
  then $14 per 1,000 requests (subject to a [daily cap](/docs/pricing#pricing-for-tools) of 1,500 requests per day).

  ---

  * Grounding with Google Maps
  * Not available{% sup %}**{% /sup %}
  * 5,000 requests per month (free, shared across all Gemini 3 and newer models), then $14 / 1,000
  search queries.

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% sup %}*{% /sup %} A customer-submitted request to Gemini may result in one or
    more queries to Google Search. You will be charged for each individual search
    query performed.

  {% sup %}**{% /sup %} Can be tested in Google AI Studio.
    

  {% /tab %}

  {% tab title="Contributor" %}
  {% callout type="note" %}
  The Gemini API Contributor Tier is offered as a private preview on an
      invite-only basis. Speed and reliability are equivalent to
      [Standard Tier inference](/docs/optimization). Eligible users will be invited by
      email and see a callout in AI Studio.

  {% /callout %}

  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD{% sup %}*{% /sup %}

  ---

  * Input price
  * Free of charge
  * $0.15 (text / image / video / audio)

  ---

  * Output price (including thinking tokens)
  * Free of charge
  * $1.25

  ---

  * Context caching price
  * Not available
  * $0.015    
  $1.00 / 1,000,000 tokens per hour (storage price)

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [Yes](/docs/logs-policy#contributor-tier)
  {% /table %}

  {% sup %}*{% /sup %} Discounts and model availability are subject to change.
    

  {% /tab %}

{% /tabs %}

## Gemini 3.8 Live, Gemini 3.8 Live Extended Thinking, and Gemini 3.1 Flash Live Preview  {% id="gemini-3.8-live" %}

{% two-column-layout %}
  

  {% left-column class="center-vertically" %}
  *[`gemini-3.8-live`](/docs/models/gemini-3.8-live),
    [`gemini-3.8-live-extended-thinking`](/docs/models/gemini-3.8-live-extended-thinking),
    [`gemini-3.1-flash-live-preview`](/docs/models/gemini-3.1-flash-live-preview)*

  {% /left-column %}

  

  {% right-column class="center-vertically right-align" %}
   {% button href="https://aistudio.google.com/live?model=gemini-3.8-live" variant="ais" %} Try it in Google AI Studio {% /button %}

  {% /right-column %}

  

{% /two-column-layout %}

{% hr /%}

Our low-latency, audio-to-audio models optimized for real-time dialogue with
acoustic nuance detection, numeric precision, and multimodal awareness.

{% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Free of charge
  * $0.75 (text)    
    $3.00 or $0.005/min (audio)    
    $1.00 or $0.002/min (image/video)

  ---

  * Output price (including thinking tokens)
  * Free of charge
  * $4.50 (text)    
    $12.00 or $0.018/min (audio)

  ---

  * Grounding with Google Search{% sup %}*{% /sup %}
  * Supported
  * 5,000 free search requests per month (shared across all Gemini 3 and newer models),
    then $14 per 1,000 requests (subject to a [daily cap](/docs/pricing#pricing-for-tools) of 1,500 requests per day).

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
{% /table %}

{% sup %}*{% /sup %} A customer-submitted request to Gemini may result in one or
more queries to Google Search. You will be charged for each individual search
query performed.

## Gemini 3.1 Pro Preview  {% id="gemini-3.1-pro-preview" %}

{% two-column-layout %}
  {% left-column class="center-vertically" %}
  *[`gemini-3.1-pro-preview`](/docs/models/gemini-3.1-pro-preview) and
    [`gemini-3.1-pro-preview-customtools`](/docs/models/gemini-3.1-pro-preview#gemini-31-pro-preview-customtools)*

  {% /left-column %}

  {% right-column class="center-vertically right-align" %}
  {% button href="https://aistudio.google.com/prompts/new_chat?model=gemini-3.1-pro-preview" variant="ais" %}
  Try it in Google AI Studio

  {% /button %}

  {% /right-column %}

{% /two-column-layout %}

{% hr /%}

Our 3rd generation Pro model, built for multimodal understanding, agentic
capabilities, and vibe-coding.

{% tabs %}
  {% tab title="Standard" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $2.00, prompts <= 200k tokens    
  $4.00, prompts > 200k tokens

  ---

  * Output price (including thinking tokens)
  * Not available
  * $12.00, prompts <= 200k tokens    
  $18.00, prompts > 200k

  ---

  * Context caching price
  * Not available
  * $0.20, prompts <= 200k tokens    
  $0.40, prompts > 200k    
  $4.50 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search{% sup %}*{% /sup %}
  * Not available{% sup %}**{% /sup %}
  * 5,000 free search requests per month (shared across all Gemini 3 and newer models),
  then $14 per 1,000 requests (subject to a [daily cap](/docs/pricing#pricing-for-tools) of 1,500 requests per day).

  ---

  * Grounding with Google Maps
  * Not available{% sup %}**{% /sup %}
  * 5,000 requests per month (free, shared across all Gemini 3 and newer models), then $14 / 1,000
  search queries.

  ---

  * Used to improve our products
  * Not available
  * [No](/docs/terms)
  {% /table %}

  {% sup %}*{% /sup %} A customer-submitted request to Gemini may result in one or
    more queries to Google Search. You will be charged for each individual search
    query performed.

  {% sup %}**{% /sup %} Can be tested in Google AI Studio.
    

  {% /tab %}

  {% tab title="Batch" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $1.00, prompts <= 200k tokens    
  $2.00, prompts > 200k tokens

  ---

  * Output price (including thinking tokens)
  * Not available
  * $6.00, prompts <= 200k tokens    
  $9.00, prompts > 200k

  ---

  * Context caching price
  * Not available
  * *Same as Standard*    
  $0.20, prompts <= 200k tokens    
  $0.40, prompts > 200k    
  $4.50 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search{% sup %}*{% /sup %}
  * Not available{% sup %}**{% /sup %}
  * 5,000 free search requests per month (shared across all Gemini 3 and newer models),
  then $14 per 1,000 requests (subject to a [daily cap](/docs/pricing#pricing-for-tools) of 1,500 requests per day).

  ---

  * Grounding with Google Maps
  * Not available{% sup %}**{% /sup %}
  * 5,000 requests per month (free, shared across all Gemini 3 and newer models), then $14 / 1,000
  search queries.

  ---

  * Used to improve our products
  * Not available
  * [No](/docs/terms)
  {% /table %}

  {% sup %}*{% /sup %} A customer-submitted request to Gemini may result in one or
    more queries to Google Search. You will be charged for each individual search
    query performed.

  {% sup %}**{% /sup %} Can be tested in Google AI Studio.
    

  {% /tab %}

  {% tab title="Flex" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $1.00, prompts <= 200k tokens    
  $2.00, prompts > 200k tokens

  ---

  * Output price (including thinking tokens)
  * Not available
  * $6.00, prompts <= 200k tokens    
  $9.00, prompts > 200k

  ---

  * Context caching price
  * Not available
  * *Same as Standard*    
  $0.20, prompts <= 200k tokens    
  $0.40, prompts > 200k    
  $4.50 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search{% sup %}*{% /sup %}
  * Not available{% sup %}**{% /sup %}
  * 5,000 free search requests per month (shared across all Gemini 3 and newer models),
  then $14 per 1,000 requests (subject to a [daily cap](/docs/pricing#pricing-for-tools) of 1,500 requests per day).

  ---

  * Grounding with Google Maps
  * Not available{% sup %}**{% /sup %}
  * 5,000 requests per month (free, shared across all Gemini 3 and newer models), then $14 / 1,000
  search queries.

  ---

  * Used to improve our products
  * Not available
  * [No](/docs/terms)
  {% /table %}

  {% sup %}*{% /sup %} A customer-submitted request to Gemini may result in one or
    more queries to Google Search. You will be charged for each individual search
    query performed.

  {% sup %}**{% /sup %} Can be tested in Google AI Studio.
    

  {% /tab %}

  {% tab title="Priority" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $3.60, prompts <= 200k tokens    
  $7.20, prompts > 200k tokens

  ---

  * Output price (including thinking tokens)
  * Not available
  * $21.60, prompts <= 200k tokens    
  $32.40, prompts > 200k

  ---

  * Context caching price
  * Not available
  * $0.36, prompts <= 200k tokens    
  $0.72, prompts > 200k    
  $8.10 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search{% sup %}*{% /sup %}
  * Not available{% sup %}**{% /sup %}
  * 5,000 free search requests per month (shared across all Gemini 3 and newer models),
  then $14 per 1,000 requests (subject to a [daily cap](/docs/pricing#pricing-for-tools) of 1,500 requests per day).

  ---

  * Grounding with Google Maps
  * Not available{% sup %}**{% /sup %}
  * 5,000 requests per month (free, shared across all Gemini 3 and newer models), then $14 / 1,000
  search queries.

  ---

  * Used to improve our products
  * Not available
  * [No](/docs/terms)
  {% /table %}

  {% sup %}*{% /sup %} A customer-submitted request to Gemini may result in one or
    more queries to Google Search. You will be charged for each individual search
    query performed.

  {% sup %}**{% /sup %} Can be tested in Google AI Studio.
    

  {% /tab %}

  {% tab title="Contributor" %}
  {% callout type="note" %}
  The Gemini API Contributor Tier is offered as a private preview on an
      invite-only basis. Speed and reliability are equivalent to
      [Standard Tier inference](/docs/optimization). Eligible users will be invited by
      email and see a callout in AI Studio.

  {% /callout %}

  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD{% sup %}*{% /sup %}

  ---

  * Input price
  * Not available
  * $1.00, prompts <= 200k tokens    
  $2.00, prompts > 200k tokens

  ---

  * Output price (including thinking tokens)
  * Not available
  * $6.00, prompts <= 200k tokens    
  $9.00, prompts > 200k tokens

  ---

  * Context caching price
  * Not available
  * $0.10, prompts <= 200k tokens    
  $0.20, prompts > 200k tokens    
  $4.50 / 1,000,000 tokens per hour (storage price)

  ---

  * Used to improve our products
  * Not available
  * [Yes](/docs/logs-policy#contributor-tier)
  {% /table %}

  {% sup %}*{% /sup %} Discounts and model availability are subject to change.
    

  {% /tab %}

{% /tabs %}

## Gemini 2.5 Flash  {% id="gemini-2.5-flash" %}

{% two-column-layout %}
  {% left-column class="center-vertically" %}
  *[`gemini-2.5-flash`](/docs/models/gemini-2.5-flash)*

  {% /left-column %}

  {% right-column class="center-vertically right-align" %}
  {% button href="https://aistudio.google.com?model=gemini-2.5-flash" variant="ais" %}
  Try it in Google AI Studio

  {% /button %}

  {% /right-column %}

{% /two-column-layout %}

{% hr /%}

Our first hybrid reasoning model which supports a 1M token context window and
has thinking budgets.

{% tabs %}
  {% tab title="Standard" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Free of charge
  * $0.30 (text / image / video)    
  $1.00 (audio)

  ---

  * Output price (including thinking tokens)
  * Free of charge
  * $2.50

  ---

  * Context caching price
  * Not available
  * $0.03 (text / image / video)    
  $0.1 (audio)    
  $1.00 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search
  * Free of charge, up to 500 RPD (limit shared with Flash-Lite RPD)
  * 1,500 RPD (free, limit shared with Flash-Lite RPD), then $35 / 1,000
  grounded prompts

  ---

  * Grounding with Google Maps
  * 500 RPD
  * 1,500 RPD (free), then $25 / 1,000 grounded prompts

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

  {% tab title="Batch" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $0.15 (text / image / video)    
  $0.50 (audio)

  ---

  * Output price (including thinking tokens)
  * Not available
  * $1.25

  ---

  * Context caching price
  * Not available
  * $0.03 (text / image / video)    
  $0.1 (audio)    
  $1.00 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search
  * Not available
  * 1,500 RPD (free, limit shared with Flash-Lite RPD), then $35 / 1,000
  grounded prompts

  ---

  * Grounding with Google Maps
  * Not available
  * Not available

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

  {% tab title="Flex" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Not available
  * $0.15 (text / image / video)    
  $0.50 (audio)

  ---

  * Output price (including thinking tokens)
  * Not available
  * $1.25

  ---

  * Context caching price
  * Not available
  * $0.03 (text / image / video)    
  $0.1 (audio)    
  $1.00 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search
  * Not available
  * 1,500 RPD (free, limit shared with Flash-Lite RPD), then $35 / 1,000
  grounded prompts

  ---

  * Grounding with Google Maps
  * Not available
  * Not available

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

  {% tab title="Priority" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Free of charge
  * $0.54 (text / image / video)    
  $1.80 (audio)

  ---

  * Output price (including thinking tokens)
  * Free of charge
  * $4.50

  ---

  * Context caching price
  * Not available
  * $0.054 (text / image / video)    
  $0.18 (audio)    
  $1.80 / 1,000,000 tokens per hour (storage price)

  ---

  * Grounding with Google Search
  * Free of charge, up to 500 RPD (limit shared with Flash-Lite RPD)
  * 1,500 RPD (free, limit shared with Flash-Lite RPD), then $35 / 1,000
  grounded prompts

  ---

  * Grounding with Google Maps
  * 500 RPD
  * 1,500 RPD (free), then $25 / 1,000 grounded prompts

  ---

  * Used to improve our products
  * [Yes](/docs/terms)
  * [No](/docs/terms)
  {% /table %}

  {% /tab %}

{% /tabs %}

