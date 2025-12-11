# Investor FAQ - Hyperplexity

## Product & Technology

### 1. What is Hyperplexity in one sentence?
Hyperplexity is a platform for building research applications that verify hundreds of entities at scale - solving multi-entity research problems that Perplexity, ChatGPT, and even Parallel.ai cannot.

### 2. What problem does Hyperplexity solve?
The "Confidence Barrier" is stalling AI adoption - even latest models retain 5-33% error rates on complex tasks. Current AI tools handle one query at a time, but real business decisions require synthesizing hundreds of data points. We automate multi-entity research, turning weeks of manual work into minutes of verified, structured output with confidence scores and source citations.

### 3. Why now?
Three converging factors:
- AI adoption hit inflection point (88% of enterprises using AI) but trust gap widening
- Token costs dropped 99% in 2 years making our model economically viable
- New regulations (EU AI Act 2025) mandating AI verification
The gap between AI capabilities and trust has never been wider - we bridge it.

### 4. How is Hyperplexity different from competitors?

**vs. Parallel.ai ($130M funded, closest competitor):**
Both do multi-entity research, but we win on:
- **Speed:** 5-10x faster through better parallelization
- **Direct from Table:** Can validate/update existing tables (they're prompt-only)
- **Monitoring:** Repeatable validation over time (they're one-shot)
- **Excel Integration:** Preserves formulas (they output JSON for developers)
- **Accessibility:** Built for non-technical users (they're built for developers/agents)
- **Optimization:** Auto-selects optimal models, groups searches (50% fewer API calls)

**vs. Perplexity/ChatGPT/Claude:**
- They: Break after ~10 rows when doing multi-entity web research
- We: Proven at 278×23 tables with 91% high confidence
- They: No systematic verification or confidence scoring
- We: 2-stage QC with color-coded confidence + hover citations

**vs. Academic tools (Elicit, Scite):**
- They: Paper-focused only
- We: ANY entities (drugs, conferences, companies, researchers, etc.)

### 5. What is your defensible moat?
**Honest assessment:** A skilled AI engineer could replicate in 7 months. Our advantages:

**Time:** 7-month head start already
**Platform approach:** Multiple apps on one engine (harder to compete across all)
**Marketing system:** Proprietary ad generator achieving 5% CTR
**Technical depth:** Repeatable validation, Excel preservation, search grouping
**First-mover:** Educating market, building use case library
**Speed:** Can build new apps in 2-4 weeks vs. competitors starting from scratch

### 6. What happens if Perplexity adds multi-entity support?
We welcome it - validates the market need. Our advantages remain:
- Deep enterprise features (Excel export, API, compliance)
- 2-stage verification with confidence scoring
- Multi-model approach (not locked to one provider)
- Already embedded in customer workflows
- Focus on B2B while they prioritize consumer

### 7. What's your IP strategy?
**Honest assessment:** Moat is not large - skilled AI engineer could build competitive tool in 7 months.

**Our advantages:**
- Proprietary query decomposition and grouping algorithms
- Confidence scoring methodology (founder's 8 patents include AI confidence reporting)
- Multi-model orchestration optimizations
- Trade secrets around cost/accuracy balancing
- 7-month head start with working product
- Platform approach harder to replicate across multiple applications

Real moat combines technical depth, execution speed, market education, and customer relationships.

---

## Market & Business Model

### 8. What's your TAM/SAM/SOM?
Three overlapping markets (verified using Chex, full analysis in Market_Analysis.md):

**TAM: $2.2B**
- AI Output Verification: $1.1B (5% of $22.2B gen-AI software market)
- Research Integrity: $120M (~1% of $12.65B scientific publishing)
- Data Maintenance: $1.0B (research-focused data enrichment slice)

**SAM: $1.0-1.3B** (20K high-stakes organizations, targetable verticals)

**SOM: $6-11M in 12-18 months** (conservative, reachable with current pipeline)

*Note: All market figures verified against primary sources using our own Chex system - practicing what we preach.*

### 9. Who are your target customers?
**D2C:** Content creators, researchers, analysts ($29-99/month)
**B2B Initial:** Pharma competitive intelligence, academic publishers, consultancies
**B2B Expansion:** Any organization tracking 50+ entities regularly
**Sweet spot:** Companies currently spending $500K+ annually on manual research

### 10. What's your pricing model?
**D2C:** Free preview (3 rows/claims) → Paid runs at 3x API costs (typically $5-100 per run)
**B2B:** $10-50K setup + 3x API usage (or bring-your-own-keys)
**Target margin:** 66% on usage fees
**Examples:** 278 drugs = $60, 60 citations = $30

**Platform advantage:** One pricing model scales across all applications (Chex, conference tracking, etc.)

### 11. How do you acquire customers?
**Unique advantage:** Proprietary ad generation system
- Converts copy → animated ads automatically
- Test 200+ variants, optimize winners
- Proven: 5% CTR on LinkedIn (10x industry average)
- Scalable to Google, TikTok, other platforms

**D2C:** LinkedIn ads (working), content marketing, SEO
**B2B:** Direct outreach to active prospects (SciLeads, Emit, Acumen)
**Platform benefit:** One marketing system acquires customers for all apps

---

## Traction & Metrics

### 12. What's your current traction?
**Product:**
- Pre-revenue, live product
- Live: eliyahu.ai/hyperplexity | eliyahu.ai/chex
- Proven: 278×23 table successfully processed

**Marketing:**
- 5% CTR on LinkedIn (10x industry average)
- $1.50/visit cost
- Proprietary ad system generating animated ads from copy
- Can rapidly test 200+ ad variants

### 13. Why haven't users tried the tool yet?
**Current challenge:** Getting visitors to try it (landing → first use), not preview-to-paid.

**This is a big part of the early effort. Active mitigation:**
- **Landing page redesign:** Clearer call-to-action, simpler messaging
- **Removing signup friction:** Will explore letting people try without email verification
- **Demo accessibility:** Easier access to demos + demo videos
- **Reduce perceived complexity:** Simpler "paste text → see results" flow
- **A/B testing:** Rapid iteration on what works

**Note:** Users who DO try are impressed with quality. Problem is getting them to start.

### 14. What's your path to profitability?
**Aggressive 6-month sprint to Series A-ready metrics:**

**Month 1-2:** Launch $15-20K/month ad campaigns, validate conversion
**Month 3:** Close first B2B contract, hire BD/sales support
**Month 4-6:** Scale what works, push for second B2B deal
**Month 6 Decision Point:**
- $50K+ MRR → Series A raise
- $20-35K MRR → Bridge round
- <$20K → Pivot to B2B focus

**The Bet:** Fast validation of D2C funnel (10% page→preview, 15% preview→paid) + 1-2 B2B deals.

### 15. What are your key metrics goals?
**Month 1:** $4K MRR (100 D2C customers)
**Month 3:** $21K MRR (400 D2C + 1 B2B contract)
**Month 6:** $52K MRR (850 D2C + 2 B2B contracts)

**Success criteria:** Validate strong unit economics ($100-150 CAC, $40 ARPU, 3.7-5.6mo payback, 5.8x LTV/CAC)

---

## Technical & Operational

### 16. What are your technical limitations?
**Current capabilities:**
- Unlimited rows (processes ~50 rows at a time in parallel)
- <25 columns with QC enabled (can be higher if needed)
- 3 tables concurrently at full tilt
- Largest proven: 278 rows × 23 columns

**Scaling strategy:**
- System adapts: reduces parallelization, queues runs, shifts models
- AWS + SQS architecture designed for growth
- B2B customers can bring own API keys for higher limits
- Significant serverless engineering already done (Lambda optimizations)

### 17. What about API dependency risks?
**Multi-provider strategy:** Not dependent on single API
**Degradation handling:** Automatic failover between providers
**Cost hedging:** As one provider raises prices, others compete
**BYOK option:** Enterprise customers can use own API keys
**Long-term:** Building proprietary verification models

### 18. How do you handle data security and compliance?
- **Data retention:** Minimal (debugging only)
- **Infrastructure:** AWS with SOC2-ready architecture
- **API providers:** All guarantee non-training on customer data
- **Enterprise mode:** Zero-retention option available
- **Compliance roadmap:** SOC2 Type 1 (Month 6), GDPR ready

### 19. What about regulatory risks?
**Opportunity not risk:** EU AI Act (2025) mandates verification
**Positioning:** We enable compliance, not create liability
**Legal review:** No regulatory barriers identified
**Industry-specific:** Can adapt to vertical requirements (HIPAA, etc.)

---

## Team & Execution

### 20. How do you address solo founder risk?
**Advisory board:** 5 expert advisors
- Matt Silva, PhD - CEO of Emit Imaging, Scientific & Business Advisor
- Reed Malleck - Finance & Operations Expert, COO/CFO experience
- Chris Fuller - AWS Solutions Architect, Cloud Technology Advisor
- Mike Maker - Project Management Expert
- Bill Cupelo - Chief Business Officer at Ratio Therapeutics, Sales Advisor

**Hiring plan:** Marketing support at $4K/month immediately, Direct hire for BD/sales at Month 3 ($10K/month). Staying lean - using AI to maximize productivity, no engineer hire initially.

**Track record:** Built equivalent of 2-year team effort solo in 7 months
**Network:** Strong connections for rapid hiring when needed

### 21. Why are you the right person to build this?
**Technical Foundation:**
- MIT PhD - 19 years starting in robotics computer vision
- 10 years in ML, 8 years in deep learning - trained all kinds of ML models
- Co-founder, Chief Scientific Officer - Mobella Health (AI video documentation for nurses)
- Former Head of Advanced Special Projects at Invicro (medical imaging for drug discovery)
- Led small team of PhDs and developers designing, building, and releasing production AI tools in pharma
- 20+ publications, 8 patents (including AI confidence reporting)

**Hyperplexity-Specific:**
- Deep expertise in AI confidence/uncertainty - directly relevant to our QC layer
- Identified exact customer problem while training medical writers - maintaining 114 conferences × 23 features
- Built working product solo in 7 months using AI-augmented development

**Eliyahu.AI (2023-present):**
- Built 500+ research workflows with GenAI and prototype GenAI tools
- Trained research teams to adopt generative AI at point of excellence
- Bootstrapped $1M+ revenue demonstrating ability to build and sell AI solutions

### 22. Are you working on this full-time?
Yes, full-time for 8 months and continuing. Minimal consulting only for survival until funding closes. Post-raise, 100% focused on Hyperplexity.

### 23. What's your hiring philosophy?
Lean team of exceptional individuals:
- Remote-first, async-friendly
- High autonomy, high accountability
- AI-augmented productivity (10x output per person)
- Target: 10-person team at $10M ARR

---

## Competition & Strategy

### 24. Who is your biggest competitive threat?
**Short-term:** User education (understanding the need)
**Medium-term:** Perplexity adding multi-entity features
**Long-term:** Enterprise building in-house
**Mitigation:** Move fast, own use cases, build switching costs

### 25. What's your distribution strategy?
**Phase 1:** Direct (proven channels, controlled growth)
**Phase 2:** Partnerships (integrate with existing tools)
**Phase 3:** Platform (API for others to build on)
**Network effects:** Shared verifications improve for all

### 26. How do you think about competition with OpenAI?
We're complementary, not competitive:
- We orchestrate their models (customer of theirs)
- We verify their outputs (trust layer)
- Different focus (they build models, we build workflows)
- Partnership opportunity more than threat

---

## Investment & Vision

### 27. Why raise from angels vs. institutional?
- Speed: Close in weeks not months
- Flexibility: SAFE allows quick execution
- Value-add: Need advisors more than pure capital
- Size: $200-300K funds 6-month validation sprint
- Control: Maintain velocity without heavy governance
- Stage: Pre-revenue but live product with proven tech

### 28. What does success look like in 3 years?
**Platform vision:** Hyperplexity powers multiple research applications
**Product:** One engine supporting Chex, conference monitoring, competitive intelligence, and more
**Distribution:** Proprietary ad system (5% CTR) brings customers across all apps
**Strategy:** When building is this easy, distribution is everything
**Exit options:** Strategic acquisition or standalone business

### 29. What are the key risks?

**1. Getting people to use the tool (PRIMARY RISK)**
- **Risk:** Visitors don't try it despite high CTR
- **Mitigation:** Landing page redesign, remove signup friction, demos + demo videos, A/B testing
- **Status:** Big part of early effort - users who try are impressed, need to reduce entry friction

**2. Too expensive for most people**
- **Risk:** Per-use pricing could be prohibitive at scale
- **Mitigation:**
  - AI optimizes cost/accuracy/complexity balance automatically
  - Users can adjust cost after preview based on their needs
  - Costs declining as model prices drop
  - Model usage not fully optimized yet - using best state-of-the-art to be right first
  - Will optimize for cost as we scale
- **Status:** Currently prioritizing quality over cost optimization

**3. Competition:** Moving fast, building platform moat, 7-month head start

**4. CAC rises:** Proprietary ad system (5% CTR), diversifying channels

**5. Key person risk:** Building team, documenting everything, advisory board

### 30. Why invest now?
- **Timing:** Regulation + market need converging (88% of enterprises using AI, trust gap widening)
- **Proven tech:** Live product, 278×23 tables successfully processed
- **Marketing advantage:** 5% CTR at $1.50/visit (10x industry avg) with proprietary ad system
- **Valuation:** $6M cap for working product, pre-revenue (low-risk entry point)
- **Speed:** 7-month head start, platform approach enables fast iteration
- **Clear path:** 6 months to Series A-ready metrics or informed pivot

---

## Use of Funds

### 31. How will you use the $200-300K?
**$300K funds aggressive 6-month sprint:**
- **38% Growth & Marketing:** $115K for $15-20K/month ad spend
- **43% Team:** $130K for founder salary, marketing support, BD hire at month 3
- **18% Operations:** $55K for API costs, infrastructure, tools

### 32. What milestones does this achieve?
**Month 1-2:** Launch aggressive ad campaigns ($15-20K/month), validate funnel conversion
**Month 3:** Close first B2B contract, hire BD/sales team member
**Month 4-6:** Scale successful channels, achieve 100-150 new customers/month
**Month 6:** Clear decision point based on MRR achieved

**Month 6 Outcomes:**
- **Success ($50K+ MRR):** Series A raise ($3-5M) - proven scalability
- **Strong ($35-50K MRR):** Strong bridge round ($500K-1M+)
- **Moderate ($20-35K MRR):** Bridge round, optimize further
- **Pivot (<$20K MRR):** Funnel didn't validate, pivot to B2B focus

### 33. When will you raise Series A?
**Target:** 6 months (aggressive case) or 12-15 months (with bridge)

**Aggressive path:** $50K+ MRR at month 6 → immediate Series A
**Moderate path:** Bridge round → 12-15 months → Series A

**Amount:** $3-5M
**Use:** Scale sales, expand product, grow to $10M ARR

---

## Product Details

### 34. What's Chex and how does it relate to Hyperplexity?
Chex is our consumer-facing application for claim verification, built on the Hyperplexity engine. Think of Hyperplexity as AWS and Chex as Netflix - one is infrastructure, the other is the application. Chex proves the engine works and drives D2C revenue.

### 35. Can you explain a specific use case?
**Pharma competitive intelligence:**
- Problem: Track 500 drugs across 20 data points = 10,000 facts
- Current solution: Team of 5 analysts, $2M/year, monthly updates
- Hyperplexity: Automated, $20K/year, daily updates
- ROI: 100x cost reduction, 30x speed improvement

### 36. How do you handle hallucinations?
Three-layer approach:
1. Multi-source verification (cross-check across models)
2. Confidence scoring (red/yellow/green coding)
3. Citation requirements (every claim needs source)
Result: 70% more accurate than single-model queries

---

## Exit Strategy

### 37. Who would acquire you?
**Strategic buyers:** Microsoft, Google, Adobe, Salesforce
**Data companies:** S&P, Bloomberg, Thomson Reuters
**AI platforms:** OpenAI, Anthropic, Cohere
**Rationale:** Critical infrastructure for enterprise AI adoption

### 38. What if you don't get acquired?
Strong standalone business:
- Recurring B2B revenue with 140% net retention
- Improving margins as AI costs decline
- Platform expansion opportunities
- IPO potential at $100M ARR

### 39. What's your competitive endgame?
Become the "Stripe for AI verification" - invisible infrastructure that powers thousands of applications. Every company using AI needs verification; we become the default solution.

---

## Founder Motivation

### 40. Why are you building this?
While training medical writers, encountered their exact problem maintaining research tables (114 conferences × 23 features). Even with Perplexity, it was tricky and manual. The question "Can you execute all of these in parallel in a coherent way?" sparked Hyperplexity. Built the solution, discovered thousands have the same need.

### 41. What will you do if this fails?
Failure scenario unlikely given current traction, but:
- Open source core technology
- Help customers migrate data
- Join AI infrastructure company
- Apply learnings to next venture
Commitment: See this through to meaningful outcome.

### 42. What kind of company culture will you build?
- High autonomy, high accountability
- Remote-first but connection-focused
- AI-augmented productivity (small team, big impact)
- Intellectual honesty and continuous learning
- Work-life integration, not work-life balance

### 43. Why is the platform approach better than building one product?
**Multiple advantages:**
- **Risk reduction:** Not dependent on one use case succeeding
- **Faster iteration:** 2-4 weeks to new app vs. 7 months from scratch
- **Shared marketing:** One ad system acquires for all apps
- **Compound moat:** Harder to compete across multiple applications
- **Market learning:** Each app teaches us about different verticals
- **Revenue diversity:** Multiple streams from one investment

**Example:** Chex validates citation checking. Conference tracking validates data monitoring. Both use same engine, same marketing system.

### 44. What are Hyperplexity's unique technical capabilities?
Beyond just "multi-entity research," we've built:
1. **Search grouping:** Related queries found together (~50% fewer API calls)
2. **Excel preservation:** Formulas and cell dependencies maintained
3. **Repeatable validation:** Same config = stable output over time (critical for monitoring)
4. **QC layer:** Confidence scoring with hover-to-show-source
5. **Human-in-loop:** Preview → refine → run workflow
6. **Cost optimization:** Groups searches, selects appropriate models

These aren't obvious features - they came from solving real problems.

---

## Common Clarifications

### 45. Is the $1M+ revenue from Hyperplexity?
No. The $1M+ revenue is from Eliyahu.AI, my consulting company - not Hyperplexity. Hyperplexity is pre-revenue with a live product. It spun out as an independent C-Corp with all IP transferred. The investment thesis is: proven technical founder with revenue track record, now validating a new product.

### 46. What does the 5% CTR metric refer to?
The 5% CTR is our advertising click-through rate on LinkedIn (10x industry average at $1.50/visit) - not a product engagement or beta conversion metric. We built a proprietary system that generates animated ads directly from copy, enabling rapid A/B testing of 200+ variants. That's our distribution moat.

### 47. How does your distribution keep pace with product development?
**The ad system scales across all apps:** The proprietary ad generator works for any application built on Hyperplexity. Copy in, animated ads out. When I spin up a new app (2-4 weeks on the engine), I can immediately generate and test hundreds of ad variants without starting from scratch. One distribution infrastructure, multiple products.

**Proven playbook transfers:** With Chex, we identified winning ad themes through rapid iteration - testing 200+ variants, killing underperformers, expanding what works. That playbook transfers directly to Hyperplexity and future apps.

**Channel diversification is built in:** Right now LinkedIn is working. The $15-20K/month ad spend lets us scale LinkedIn while it's hot, test Google and TikTok in parallel, and build SEO/content as a longer-term channel.

**B2B provides stability:** D2C validates fast but can be volatile. The B2B pipeline provides higher-value, stickier revenue. One $10K/month B2B contract equals 250 D2C customers.

### 48. Why stay lean and not hire faster?
The platform is built. Hyperplexity works. Chex works. The infrastructure handles concurrent users. What I need to validate isn't "can we build more?" - it's "does the funnel convert?"

Adding engineers before validating product-market fit burns cash on building features nobody's paying for. The first 60 days are about distribution execution, not development.

**What I'm actually hiring for:**
- **Marketing support (immediate, $4K/month):** Execute on ad campaigns, manage creative variants, track metrics. Frees me to focus on B2B conversations and product iteration.
- **BD/Sales (month 3, $10K/month):** Once we have conversion data and (ideally) first B2B contract closed, someone to run the sales process while I handle product and strategy.

No engineer hire initially. If something breaks or needs iteration, I fix it. AI-augmented development means I can ship updates fast without a team.

### 49. How does AI change team size requirements?
AI genuinely changes the math. I built Hyperplexity + Chex + the ad system in 7 months solo. That's not hustle culture; it's Claude helping me code, write copy, debug, and iterate 10x faster than I could alone.

The target is a 10-person team at $10M ARR. That's lean by design. High autonomy, high accountability, AI-augmented productivity.

**What would change the hiring plan:** If D2C conversion validates strong (15%+ preview-to-paid) by month 2, I'd accelerate the BD hire and potentially add a second marketing person. If we close a large B2B deal that needs custom work, I'd bring on engineering support for that specific engagement. But I'm not hiring ahead of validation.

### 50. How do you choose which model to use for a given task?

Hyperplexity treats models as interchangeable components. For each research question (cell), we classify it by difficulty and risk and route it to the lowest-cost model that can hit our target confidence. Simple factual lookups may go to a cheaper model; complex, high-stakes reasoning goes to a stronger one.

New models like DeepSeek v3.2 let us replace large portions of our Claude 4.5 usage for most tasks at a fraction of the cost. Because the routing logic is ours, we can adopt better/cheaper models without any change to customer workflows. Today, the most expensive part of the stack is the quality-control (QC) layer, where we still lean on high-end models like Claude Sonnet 4.5 for difficult judgments, but that layer will also migrate to cheaper, similarly capable models over time.


### 51. What’s your strategy around falling model prices and new providers like DeepSeek?

We expect model prices to keep dropping and new entrants to compete aggressively. That’s good for us. We don’t sell models; we sell verified research tables and workflows.

Our orchestration layer is designed so that every price reduction or new efficient model either:
1. Improves our margins, or  
2. Lets us reduce prices and expand the market.

Concretely, our largest cost center today is the QC layer that runs on Claude Sonnet 4.5. Our plan is to move that layer to similarly capable models such as DeepSeek v3.2 delivered via Amazon Bedrock as soon as they clear our quality bar, which we estimate would reduce unit costs for those calls by roughly 10–45x. Our investors benefit from whichever lever we decide to pull in a given segment.


### 52. How does your caching system work and why does it matter economically?

Hyperplexity caches answers at the **cell** level with metadata about sources, timestamps, and confidence. When a user reruns a table, we:

- Reuse cached cells for stable facts  
- Refresh only the columns or rows likely to have changed  
- Use cheaper “preview” runs to spot large changes before committing to full validation  

In practice, this means the first full run of a research matrix is the most expensive; subsequent refreshes are significantly cheaper and faster, which is ideal for recurring monitoring use cases.

Those cheaper preview runs are not just a cost-saving trick; they are also **tests**. Each preview encodes our current best guess at the right balance of models and cost for the system of research questions behind a table. The sequential feedback we get from users over multiple iterations — what they accept, edit, or ask us to dig into — lets us continually re-optimise that balance, which is critical in a rapidly changing model landscape.


### 53. What’s the plan for integrations with data providers and journals?

Hyperplexity is already designed to plug into external data sources.

For **data providers**, we can:
- Call their APIs directly to populate or cross-check cells  
- Run Hyperplexity in their infrastructure as the engine behind “fresh, verified tables” they sell to their customers  

For **journals and publishers**, Chex can be integrated into submission or editorial workflows to automatically verify claims and citations before publication. These integrations are higher-touch initially, but they create extremely sticky, recurring workflows and valuable proprietary datasets.


### 54. Isn’t high-touch integration at odds with a scalable SaaS business?

In the early phase, high-touch integrations are a feature, not a bug. They:

- Embed us deeply into workflows where switching costs are high  
- Generate structured ground-truth data that strengthens our models and templates  
- Produce repeatable playbooks (e.g., “journal integration template,” “data provider template”) that we can reuse  

Over time, each integration type becomes a semi-productized module, so marginal integrations get cheaper while the stickiness and data advantages compound.


### 55. Are you just a wrapper around Perplexity and Claude?

No. Perplexity and Claude are two of several engines we orchestrate. Our value is in:

- Decomposing messy research questions into hundreds of structured sub-queries  
- Choosing the right data source (web, data provider, journal) and the right model tier for each cell  
- Running verification and confidence scoring at matrix scale  
- Caching and updating tables over time instead of starting from zero on every run  

If Perplexity or Claude disappeared tomorrow, we could swap in other models (including DeepSeek via Bedrock) with minimal disruption. Customers still get the same tables and workflows, just powered by a different mix under the hood.



**Contact:** eliyahu@eliyahu.ai | Live Demo: eliyahu.ai/hyperplexity