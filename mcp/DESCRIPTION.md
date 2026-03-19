# Hyperplexity — AI Research Tables with Citations and Confidence Scores

**Turn a prompt into a verified, cited research table. Or fact-check any table or document you already have.**

Hyperplexity gives Claude the ability to conduct deep, structured research across entire domains — not one question at a time, but hundreds of cells simultaneously, each with a sourced answer, a confidence rating, and links to the evidence.

---

## What it does

You describe what you want in plain English. Hyperplexity researches it, validates every fact, and returns a structured table where each cell has:

- ✅ A verified answer
- 📊 A confidence score (HIGH / MEDIUM / LOW)
- 🔗 Citations to the actual sources

The output is an Excel file and a shareable interactive viewer. Claude drives the full workflow — you just review and approve.

---

## Three ways to start

Once installed, tell Claude what you want in plain English — it drives everything from there.

| Goal | What to say to Claude |
|------|----------------------|
| **Generate a table from a prompt** | *"Use Hyperplexity to create a table of the top 20 US biotech companies with columns: company, market cap, lead drug, and phase."* |
| **Validate an existing Excel or CSV** | *"Use Hyperplexity to validate `companies.xlsx`. Interview me about what each column means, then run the preview."* |
| **Fact-check a document or passage** | *"Use Hyperplexity to fact-check this analyst report."* *(paste text or share a file path)* |

Claude handles the full workflow — upload, configure, preview, approve — pausing only when a decision genuinely needs you.

---

## What each workflow does

### Generate a table from a prompt
Claude starts a table-maker session, clarifies the structure if needed, builds the table, runs a free 3-row preview, and waits for your approval before billing.

### Validate an existing Excel or CSV file
Upload any table and Hyperplexity fact-checks every cell against live sources. It learns the meaning of your columns through a short interview (or you can skip the interview entirely with a one-line description), then runs the same preview-then-approve flow.

### Fact-check a document or text passage
Paste an analyst report, a research abstract, or any text with factual claims. Hyperplexity extracts each claim, verifies it independently, and returns support levels: **SUPPORTED / PARTIAL / UNSUPPORTED / UNVERIFIABLE** — with the source for every verdict.

### Refresh a table you already ran
Re-run validation on any prior job to pick up changes in source data. No re-upload or configuration needed.

---

## Why it's different

Most AI tools answer one question at a time. Hyperplexity answers a whole research domain at once — running hundreds of targeted searches, applying QC passes, and reconciling conflicting sources — then packages the results into a structured, citable format.

The MCP integration means Claude can drive the entire workflow autonomously: upload, configure, preview, approve, and retrieve results — pausing only when a decision genuinely requires human input.

---

## Pricing

| | Cost |
|--|--|
| Preview (first 3 rows) | Free |
| Standard validation | ~$0.05 / cell |
| Advanced validation | up to ~$0.25 / cell |
| Minimum per run | $2.00 |

New accounts get **$20 in free credits** — enough for several full tables.

---

## Get started

1. Get your API key at [hyperplexity.ai/account](https://hyperplexity.ai/account)
2. Install the MCP server — pick whichever method you prefer:

**Option A — Smithery (recommended, no env var setup needed):**
```bash
smithery mcp add hyperplexity/production
```

**Option B — Direct (Claude Code):**
```bash
claude mcp add hyperplexity uvx mcp-server-hyperplexity \
  -e HYPERPLEXITY_API_KEY=hpx_live_your_key_here
```

3. Ask Claude: *"Use Hyperplexity to generate a table of…"*

Full documentation: [eliyahu.ai/api-guide](https://eliyahu.ai/api-guide)
