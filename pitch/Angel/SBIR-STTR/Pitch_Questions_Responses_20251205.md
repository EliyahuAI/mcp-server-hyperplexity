Here’s a regenerated, more “NSF-native” version of all four answers, with the questions included and the tone tuned to hit the chords reviewers care about: **deep tech, unproven but high-impact R&D, clear market pull, and a PI who can actually pull it off.**

I’m assuming “Hyperplexity” (engine) + “Chex” (first app) are the focus of this pitch. 

---

### 13. Briefly describe the technology innovation that would be the focus of a Phase 1 project. Include a sentence discussing the origin(s) of the innovation as well as an explanation as to why it meets the program’s mandate to focus on supporting research and development (R&D) of unproven high-impact innovation. This section should not just discuss the features and benefits of your solution, it must also clearly explain the uniqueness, innovation, and/or novelty in how your product or service is designed and functioned. (Up to 3500 characters)

The proposed Phase I project will advance *Hyperplexity*, a new computational substrate for “multi-entity reasoning” with AI: a research-table engine that can generate, verify, and continuously update large structured matrices of information with explicit confidence and citations. The innovation originated in a concrete enterprise problem: while training medical writers, the PI watched a team attempt to maintain a 114-conference × 23-field table (submission dates, costs, participation rules, etc.) using Perplexity and other tools. Even with modern LLMs, the team could only work one conference at a time; any attempt to scale or revisit the table led to inconsistency, missing data, and no way to know which cells were trustworthy. 

Hyperplexity is not another chatbot or single-agent “AI assistant.” It is a multi-agent orchestration and verification layer that decomposes a research table into hundreds or thousands of sub-queries, groups them into efficient batches, executes them in parallel across multiple LLM providers, and then recombines the results into a coherent table with cell-level confidence scores, citations, and stability metrics. Early prototypes built by the PI have successfully processed tables as large as 278 rows × 23 columns and delivered 91% “high confidence” cells, while ChatGPT and Claude break down at 10–19 rows on the same task. 

This work fits NSF’s mandate for *unproven, high-impact R&D* because it tackles core, unsolved research questions that lie beneath current AI applications: How can we quantify cross-model disagreement across thousands of structured outputs? How can we guarantee repeatable, stable results when orchestrating hundreds of agents over time? How can we attach statistically meaningful confidence to each cell of a dynamic research matrix, rather than to a single text answer? These questions are not addressed by existing chat interfaces, paper-focused tools, or entity-enrichment APIs. 

Technically, Hyperplexity’s novelty lies in: (1) grouped-query algorithms that minimize redundant API calls while preserving recall; (2) cross-model consensus and divergence scoring over structured tables; (3) iterative stability scoring across runs; and (4) a verification layer that links claims to supporting citations at scale. Together, these create a new kind of AI research infrastructure: instead of asking one question at a time, organizations can maintain living research matrices that cover entire domains (drugs, trials, conferences, citations) with measurable trust. If successful, this architecture will enable high-impact applications in AI verification, research integrity, and dynamic data enrichment that are not feasible with today’s single-query LLM tools. 

---

### 14. Briefly describe the technical objectives and challenges. Include the highest risk research challenges to be investigated in a Phase 1 effort that are specific to your innovation. This section should also include a brief description of your unique scientific approach to solving those challenges and how this would lead to a sustainable competitive advantage for the company. Please note that challenges common to an industry or market are not responsive in this section. (Up to 3500 characters)

The Phase I project will focus on four tightly scoped, high-risk research objectives that are specific to Hyperplexity’s architecture and cannot be solved by generic LLM improvements alone.

**Objective 1 – Grouped-Query Optimization for Research Tables.**
*Challenge:* A 278×23 table can require 5,000+ sub-queries if handled naively. Executing each query independently is prohibitively expensive and slow. The research challenge is to design algorithms that cluster related queries into shared prompts, while preserving recall and avoiding context overload effects in LLMs.
*Scientific Approach:* We will develop and evaluate grouping heuristics and graph-based clustering over the bipartite structure (entities × attributes), then benchmark them against naive baselines on large real-world tables (e.g., oncology trials, conference calendars). Success metrics will include ≥50% reduction in API calls with ≤5–10% loss in factual recall versus a full, ungrouped run. 

**Objective 2 – Cross-Model Consensus and Divergence Estimation.**
*Challenge:* Hyperplexity orchestrates multiple models (e.g., GPT-4, Claude, Perplexity), but there is no standard way to quantify disagreement across models at cell level or to combine them into a single, trustworthy value. This is a structured, multi-entity extension of uncertainty estimation that has not been resolved in current AI literature.
*Scientific Approach:* Building on the PI’s prior work and patents in AI confidence reporting, we will design divergence metrics (e.g., distributional similarity, entailment checks across candidate answers and citations) and test whether these can bound empirical error rates on labeled benchmark tables. Hypothesis: we can define a consensus confidence score whose calibration error is below a defined threshold (e.g., <10% miscalibration on held-out data). 

**Objective 3 – Iterative Stability Scoring Across Time.**
*Challenge:* In real workflows, research tables are refreshed repeatedly as new data appears. Today’s LLM systems produce unstable outputs from run to run, which is unacceptable in regulated or scientific contexts. Hyperplexity needs a principled notion of “table stability” over time.
*Scientific Approach:* We will explore Monte-Carlo prompting, repeated sampling, and change-point detection over successive table versions to define an instability metric at the cell and column levels. We will investigate when differences across runs reflect genuine world changes versus model noise. The goal is to derive stability scores that correlate with human judgments of “safe to trust vs. needs review.”

**Objective 4 – Scalable Citation-Backed Verification.**
*Challenge:* Chex (Hyperplexity’s first app) must verify claims and citations at scale, not just retrieve references. We need methods that can, for each cell, check that a cited source actually supports the stated fact.
*Scientific Approach:* We will extend lightweight retrieval-augmented verification pipelines that compare extracted claims with citation content using entailment-style checks, optimized for hundreds of parallel cells. Success will be measured by precision/recall against human-labeled citation–claim pairs in biomedical and technical domains. 

**Sustainable Advantage.**
Solving these challenges yields proprietary orchestration, stability, and verification algorithms tuned to large research tables. These are not generic industry problems; they are unique to multi-entity, table-centric AI research. The resulting models, benchmarks, and metrics will be embedded deeply into Hyperplexity’s engine and workflows, creating a durable technical moat: competitors would need to reproduce years of this R&D—not just copy a UI—to reach comparable reliability.

---
Nice, let’s crank up the idea density dial 🔧

Below are **tight, high-density versions of Q15 and Q16**, each kept safely under **1,750 characters** (including spaces). You can paste these directly into the NSF portal.

---

### 15. Briefly describe the market opportunity. Describe the customer profile and pain point(s) that will be the near-term commercial focus related to this technical project (up to 1750 characters).

The near-term commercial focus targets organizations whose core workflows depend on large, structured research tables that must be correct, defensible, and continuously updated. Primary early adopters are (1) pharma / biotech competitive-intelligence and medical-affairs teams and (2) scientific publishers and medical-writing groups responsible for citation and claim integrity.

A typical CI group maintains 200–500 drugs, trials, or KOLs, each described by tens of attributes (mechanism, trial status, geography, conference activity, etc.). These matrices are maintained through fragmented combinations of internal databases, manual web research, and ad-hoc use of LLMs. Update cycles often take weeks, cost tens of thousands of dollars in analyst or writer time, and still produce inconsistencies, gaps, and undocumented assumptions that propagate into portfolio, partnering, and regulatory decisions.

Publishers and medical writers face an analogous problem at the level of manuscripts: each claim must be mapped to a specific citation, checked against retractions or contradictory findings, and revisited as the literature evolves. Existing “AI assistants” can draft text but cannot maintain a living, auditable claim–citation graph across dozens of papers.

Hyperplexity is designed for this precise job: maintain high-stakes research tables with explicit confidence scores, stability metrics, and source links, rather than answer isolated questions. By enabling dense research matrices to be generated, re-verified, and refreshed in hours instead of weeks, the system compresses cycle time and labor cost while making residual epistemic risk visible, creating a compelling value proposition for these early adopters.

---

### 16. Briefly describe the company and team. Describe the background and current status of the submitting small business, including team members related to the technical and/or commercial efforts discussed in this Project Pitch (up to 1750 characters).

Hyperplexity.AI is a newly formed C-corporation dedicated to making AI-assisted research trustworthy at scale. The company is a spin-out from Eliyahu.AI, where the founder built more than 500 GenAI research workflows for enterprise clients and bootstrapped over $1M in revenue. Hyperplexity (the research-table engine) and Chex (the citation / claim-checking application) emerged as internal tools for high-stakes research tasks; all relevant IP and code have been transferred into the new entity.

The PI and CEO, Dr. Elliot Greenblatt, holds a PhD from MIT and has 19 years of experience in AI / ML, including 8 years in deep learning, 20+ publications, and 8 patents, several in AI confidence and uncertainty reporting that directly inform the proposed verification layer. As former Head of Advanced Special Projects at Invicro, he led small teams delivering production AI systems for medical imaging and drug-discovery pipelines in regulated environments, giving him direct experience with end-to-end validation, deployment, and stakeholder integration.

Over the past seven months he has architected and implemented the Hyperplexity prototype and Chex largely solo using AI-augmented development, demonstrating the ability to execute a focused Phase I R&D plan with a lean technical team. An advisory group contributes depth in scientific imaging, AWS cloud architecture, finance / operations, and pharma business development, and the Phase I effort will add part-time support for marketing / customer discovery. The company is pre-revenue but has live products, early marketing signal (≈5% CTR at ≈$1.50/visit), and a clear pathway from Phase I technical milestones to 1–3 pilot deployments in pharma CI and scientific publishing.

---
