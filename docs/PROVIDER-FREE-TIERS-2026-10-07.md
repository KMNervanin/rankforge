# Provider free tiers and idle-balance avoidance — research, 2026-10-07

Owner question: can Rankforge lean on the free daily quotas that model providers hand out, and how do we stop money from sitting unused on a provider balance when the tutor is idle? This note records what the public pages say as of 2026-10-07 and what it means for the project. It extends the pricing research of 2026-10-03 in `research_notes/`; the earlier per-token tables stay valid.

Legend: **[O]** official page read directly; **[O-s]** official page seen only through a search snippet because the direct fetch was blocked; **[3p]** third-party blog, forum or aggregator. Anything marked [3p] or "not confirmed" must be re-checked in the provider console before being relied on.

## Where Rankforge stands today

The shipped tutor uses the owner's existing ChatGPT subscription through the local OAuth client. No API balance exists, so right now nothing sits idle. The project rules still apply to any adapter added from this note: no pay-as-you-go fallback on quota or auth failure, pending messages are preserved, credentials stay out of the browser, git, logs and learning history, and public-provider adapter changes stay isolated and documented.

## Part A — free quotas usable through an API key

| Provider | Free models | Limits | Conditions | Card | Source |
| --- | --- | --- | --- | --- | --- |
| Google Gemini API, AI Studio | Gemini 3.8/3.7/3.6/3.5 Flash, 3.5 and 3.1 Flash-Lite, 2.5 Pro/Flash/Flash-Lite, Gemma 4, embeddings, TTS/Live. Not free: 3.1 Pro Preview, image and video models | Numbers are no longer published; "view in AI Studio". [3p, Sept 2026, conflicting] Flash about 10 RPM, 250K TPM, 1,500 RPD; Flash-Lite 15 RPM, 1,000 RPD; 2.5 Pro 5 RPM, 50–100 RPD | Unpaid use: Google uses submitted content to improve products and human reviewers may read it. EEA/UK/CH clients get paid terms only. Free tier means a project without a billing account | No | [O] ai.google.dev pricing, rate-limits, terms, billing |
| OpenAI | No free credits. Complimentary daily tokens only through the data-sharing program | Build orgs: 250K tokens/day on frontier models plus 2.5M/day on mini/nano; Launch/Grow: 1M plus 10M. Resets 00:00 UTC. Excludes fine-tuned models, evals, tool use | Must opt in to training on inputs/outputs and keep a positive prepaid balance. [3p] July 2026 forum reports of tokens billed by mistake | Yes, $5 to reach Build | [O] developers.openai.com rate-limits; [O-s] help 10306912 |
| Anthropic | None. Evaluation tier is lower limits, not free. Max/Team subscriptions include monthly API credits that expire each cycle | — | — | Yes | [O] platform.claude.com rate-limits; [O] support 8977456 |
| Groq | Free plan: gpt-oss-120b, gpt-oss-20b, gpt-oss-safeguard-20b, qwen3.8-27b, whisper-large-v3. Llama 3.1 8B and 3.3 70B removed from free and dev tiers on 2026-08-16 | gpt-oss: 30 RPM, 1K RPD, 8K TPM, 200K TPD; whisper 20 RPM, 2K RPD. Free tab not rendered; numbers match a [3p] quote from 2026-09-26 | Data use on the free plan not confirmed | Not for Free | [O] console.groq.com rate-limits, deprecations, billing-faqs |
| Cerebras | No permanent free tier. $5 trial credit, expires 30 days after activation | gpt-oss-120b, qwen-3.8-27b: 5 RPM, 30K uncached TPM, 1M TPD | Evaluation only, pauses when the credit is gone | Yes, verified payment method | [O] cerebras.ai pricing; inference-docs rate-limits |
| Mistral | Free mode: API keys with included monthly usage on all API models | Not published; per-model RPS, TPM and tokens/month only in Admin Panel. [3p] about 1 RPS, 500K TPM, 1B tokens/month | Free mode may train on inputs and outputs; opt-out toggle in Admin › Privacy. Zero data retention only on pay-as-you-go. [3p] phone verification | Not confirmed, likely no | [O] docs.mistral.ai usage-limits; [O-s] help 455207, 347617 |
| Cohere | Trial key: all Command models | Chat 20 req/min, 1,000 API calls per month total | Evaluation only | Not confirmed | [O] docs.cohere.com rate-limits |
| OpenRouter `:free` | Every model with the `:free` suffix, rotating list | 20 RPM; 50 RPD with lifetime purchases under $10, 1,000 RPD at $10 or more. Negative balance returns 402 even on free models | Free-model upstreams may log or train; check each model page | No, but $10 once for 1,000 RPD | [O] openrouter.ai limits, faq |
| GitHub Models | Retired 2026-07-30: playground, catalog, inference API and BYOK | — | Redirected to Azure AI Foundry and Copilot | — | [O] docs.github.com; [O-s] github.blog changelog |
| Cloudflare Workers AI | All Workers AI models | 10,000 neurons/day free on Workers Free and Paid; beyond that $0.011 per 1,000 neurons on Paid only ($5/month minimum) | Workers Free is the default plan | Not confirmed for Free | [O] developers.cloudflare.com workers-ai pricing |
| NVIDIA build.nvidia.com | 100+ hosted NIM endpoints, OpenAI-compatible | No credit system since Sept 2025; per-model rate limits shown in the UI, not published. [3p] about 40 RPM | Trial is for prototyping, research and learning; production needs NVIDIA AI Enterprise | No | [O] NVIDIA forum staff reply 344567 |
| Hugging Face Inference Providers | 200+ models through the router | Free accounts get no monthly credits; PRO gets $2/month | Pass-through provider pricing | Yes | [O] huggingface.co inference-providers pricing |
| DeepSeek | None | — | Promo balance may expire | Yes | [O] api-docs.deepseek.com pricing |
| Alibaba Model Studio, Singapore | Qwen and other eligible models | About 1,000,000 tokens per model, valid 90 days from activation | Enable "Free Quota Only" or usage rolls into pay-as-you-go | Not mentioned | [O] alibabacloud.com new-free-quota |
| Z.ai / Zhipu | GLM-4.7-Flash, GLM-4.5-Flash, GLM-4.6V-Flash priced free | Rate and concurrency limits not published | — | Not confirmed | [O] docs.z.ai pricing |
| Moonshot / Kimi | None | $1 minimum recharge gives 3 RPM, 500K TPM; $10 cumulative gives 100 RPM | — | Yes | [O] platform.kimi.ai limits |
| Together AI | No trial | $15 first purchase, then $5; credits do not expire | Prepaid | Yes | [O] docs.together.ai billing |
| Fireworks AI | $1 starter credit | [3p] 10 RPM until a payment method is added | Account suspended when the $1 is gone | No for the $1 | [O] docs.fireworks.ai billing FAQ |
| SambaNova Cloud | Free tier: DeepSeek-V3.1/V3.2, Llama-3.3-70B, gpt-oss-120b, gemma-4-31B | 20 RPM, 20 RPD, 200K TPD per model | Developer tier with card: 60–240 RPM | No for Free | [O-s] docs.sambanova.ai rate-limits |
| Hyperbolic | Basic tier, $0 deposit | 60 RPM; Pro at $5 deposit gives 600 RPM. No standing signup credit found | — | No for Basic | [O-s] hyperbolic.ai docs |

## Part B — who holds your money, and how to keep the balance near zero

- **OpenAI.** Prepaid by default, $5 minimum, credits expire one year after purchase and are non-refundable. Auto-recharge has a threshold, an amount and an optional monthly cap, dashboard only. Hard spend limits at org and project level return 429 when hit. The complimentary data-sharing tokens require a positive balance, so some money has to sit there. [O] spend-limits guide; [O-s] help 8264644.
- **Anthropic.** Prepaid, credits expire after one year, non-refundable. Auto-reload with threshold and amount in the Console. Monthly invoicing only through Sales. Self-set spend limit under the tier cap returns 400 when hit. Rate-limit API is read-only; there is no top-up API. Minimum purchase not stated officially. [O] support 8977456; rate-limits.
- **Google Gemini API.** Postpaid by default: usage accrues on Cloud Billing and is charged at month end or at an automatically assigned spend cap, so nothing sits idle. Optional prepay exists. Tier caps pause usage; project spend caps are experimental. Cloud Billing budgets alone only alert. [O] gemini-api billing; cloud billing budgets.
- **OpenRouter.** Prepaid, $5 minimum per transaction, 5.5% card fee with $0.80 minimum, may expire unused credits after 365 days, refunds only within 24 hours. The credits endpoint reads balance and usage, per-key limits can be set daily, weekly or monthly, but the former crypto purchase endpoint now returns 410. No programmatic purchase, no postpaid. [O] terms §4.1, faq, provisioning-api-keys, crypto-api.
- **DeepSeek.** Prepaid, topped-up balance does not expire, refundable through the Billing page, 402 at zero. Minimum top-up not published. No top-up API. [O-s] FAQ.
- **Mistral.** Postpaid: pay-as-you-go is billed on consumption at month end with no upfront cost, and it is an opt-in extension beyond the plan's included usage, so leaving it off is itself a hard cap. [O-s] billing docs.
- **Groq.** Postpaid in arrears, first charges at $1/$10/$100/$500/$1,000 cumulative usage, nothing billed under $0.50, automated spending limits and alerts. Payment method required for the Developer plan. [O] billing-faqs.
- **Postpaid options found:** Google Cloud Billing, Mistral, Groq, Cloudflare Workers Paid. No aggregator was confirmed postpaid for individuals; Together and Fireworks are prepaid.
- **Programmatic top-ups.** No provider offers an official API to buy credits; OpenRouter's was removed. Auto-recharge at the smallest threshold is the only official "little by little" mechanism. Automating a card checkout ourselves would mean driving a payment page with stored card data against the providers' terms, so it is not an option for Rankforge.

## What this means for Rankforge

- **The idle-money problem is solved by billing model, not by a payment bot.** Prefer providers that bill in arrears: Google Gemini on Cloud Billing, Groq Developer, Mistral pay-as-you-go. Each has a cap that actually blocks: Google tier cap, Groq spending limit, Mistral toggle. With prepaid providers the minimum is $5, and OpenAI and Anthropic credits expire after a year, so a stuck $5 is the floor there.
- **A zero-balance tutor stack exists.** Gemini free tier for Flash or Flash-Lite with no card, Groq free plan with about 1,000 requests per day on gpt-oss-120b, Cloudflare Workers AI with 10,000 neurons per day for small models. Gemini and Mistral free modes may train on submitted text; a debrief is the learner's own English about a lab, so this is acceptable only if the learner knows and nothing private is in the prompt.
- **OpenRouter free is a $10 licence, not a balance.** 50 requests per day without purchases; a one-time $10 purchase unlocks 1,000 per day and then sits there, possibly expiring after a year.
- **Do not plan around:** GitHub Models (retired), Hugging Face free credits (gone), Cerebras and SambaNova "free" (card-gated trial or 20 requests per day), NVIDIA build (unpublished limits, prototyping terms).
- **Fit with the harness contract.** A free-tier adapter is a second provider behind the same bounded harness: the game must treat a 429 or exhausted daily quota exactly like today's subscription quota failure, keep the pending message, show the reset time and never switch to a paid route by itself. The daily reset time of each free tier becomes a visible fact in the Connection panel, not a silent retry.
- **Owner access.** The earlier research recorded that Russia is absent from the OpenAI and Anthropic supported lists. Regional availability of the Gemini, Groq and Mistral free tiers for the owner's account was not checked here and must be confirmed in each console before any adapter work.

## Not confirmed

- Gemini free-tier numeric limits per model, and whether 2.5 Pro is still free.
- Groq free-plan table and its data-use policy.
- Mistral free-mode numbers and phone verification.
- Anthropic minimum purchase; DeepSeek minimum top-up.
- Whether Cohere, Cloudflare, Mistral and Z.ai require a card for free use; Z.ai rate limits.
- OpenAI complimentary-token article full text and any scheduled end date.
- Fireworks 10 RPM figure; Hyperbolic signup credit.
