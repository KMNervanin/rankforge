# What an active user costs in LLM inference — public evidence, 2026-10-08

Owner question: is there research on how much an average player costs a company in LLM API spend in services like Rankforge? Short answer: no consumer tutor or companion company publishes a per-user inference figure. What exists is price points justified by compute cost, gross-margin disclosures, one serving-cost ceiling, and vendor models. Collected by a research subagent on 2026-10-08 from the sources below; third-party and modeled figures are marked.

## Datapoints that are actually on the record

- **Khan Academy, Khanmigo.** Pilot in 2023 asked a $20 per month donation to cover GPT-4 cost; district price cut from $60 to $35 per student per year in Nov 2023 citing engineering work on "the high computational costs of AI"; consumer price $4 per month or $44 per year with the site stating that every interaction has costs and the payment covers them. Sal Khan in May 2024 hoped to reach $10–20 per student per year. Sources: blog.khanacademy.org/harnessing-ai-so-that-all-students-benefit, thejournal.com 2023-11-16, khanmigo.ai/learners, cnbc.com 2024-05-21 via summary. Official prices, not disclosed costs; they bound the GPT-4-era cost at roughly $3–5 per school student per month.
- **Duolingo, SEC filings and calls.** Gross margin 72.2% in FY2025 versus 72.8%, decline attributed to AI costs in Video Call; Max was 5–8% of subscribers through 2025. In the Q2 2026 call the company said a Video Call fell from about $0.30 to under $0.01 per call after moving to open-weight models, and that AI inside cost of goods is "tens of millions of dollars" against revenue near $1.2B. Sources: sec.gov 10-K FY2025, Q1 FY26 letter, fool.com Q2 2026 transcript. Blended that is well under $0.10 per daily user per month; the division is ours, not disclosed.
- **Character.AI.** Serving cost "less than one cent per hour of conversation" on self-hosted in-house models, June 2024. A one-hour-a-day user is therefore at most about $0.30 per month. Source: blog.character.ai/optimizing-ai-inference-at-character-ai.
- **Boot.dev.** Boots is available to members only; the company cites hosting and maintenance costs, "especially AI chats", as the reason it refuses lifetime deals. Source: boot.dev/blog/education/is-boot-dev-free. No per-user number.
- **Chai AI.** Blocked free use in low-revenue countries in early 2026 citing compute bills and added an ad-supported basic tier. Source: Wikipedia summary of press. Qualitative only.

## Modeled estimates, vendor or analyst

- Inworld, July 2026 prices: text companion at 50 messages a day costs $0.09 per daily user per month on a self-hosted Gemma 4 26B and $7.50 on GPT-5.5; realtime voice $1–18. inworld.ai/resources/unit-economics-of-consumer-ai-apps.
- RevenueCat, March 2026: baseline $0.02 per AI-active user per month for ten requests of a thousand tokens, $0.10 in a heavier scenario, with only about 15% of monthly users touching the AI feature at all. revenuecat.com/blog/growth/ai-feature-cost-subscription-app-margins.
- ibl.ai, May 2026: one tutoring session of 1k input and 1.5k output costs $0.002 on Gemini 3 Flash, $0.009 on Haiku 4.5, $0.025 on Sonnet 4.6, $0.128 on Opus 4.7. Vendor with a self-hosting agenda. ibl.ai/blog/what-ai-tutoring-actually-costs-2026.
- Margin benchmarks: AI-native app gross margins cluster at 45–60% with inference around 20–25% of revenue at scale (ICONIQ via SaaStr, Bessemer via 1752.vc). a16z's Sarah Wang: an 85–90% margin on an AI app "means nobody's actually using the product".

## Ranges to plan with

- GPT-4 era, 2023–24: $3–5 per active student per month was the revealed floor at Khan Academy.
- 2026, cheap or mid models, text only: $0.05–0.50 per active user per month is the practical planning range; frontier text or realtime voice $2–20.
- Rankforge's own bound sits below the low end of that range: two free debriefs per mission on Gemini Flash cost about one cent per mission, and coaching costs only what the item economy issues. The owner's Boot.dev experience, items rarely spent because tasks were tedious rather than hard, matches RevenueCat's assumption that most users touch the AI feature rarely.

## Cost-bounding patterns in the wild

- Daily battery or energy drained by AI use: Khanmigo's AI power battery resets nightly; Duolingo Energy with 25 units for free users, buyable with gems, unlimited on paid tiers.
- Hard daily prompt caps for free users: Codecademy five prompts a day, Langua 75 messages a day, Talkpal ten minutes a day.
- AI chat as a paid-only feature: Boot.dev Boots, Quizlet Q-Chat, Brilliant's Koji.
- Premium model behind a daily quota: Character.AI lite sells a daily allowance of larger models.
- Expensive features relaxed as cost falls: Duolingo moving Video Call from Max to Super once it cost under a cent.
- No public data on the share of users who hit these caps; the only proxy is Duolingo's remark that beginners ran out of hearts twice as often, the reason for Energy.

## Not found

Per-user inference figures from Khan Academy, Duolingo at the Max level, Speak, Replika, Character.AI, Quizlet, Chegg, Brilliant, Boot.dev, CodeCrafters, Codecademy or Exercism. Figures circulating on review sites for Khanmigo, "$9 per month" or "$2–4 per student per year", are unsourced. Claims about Copilot or ChatGPT losing money per user are disputed and not usable here.
