/**
 * OpenRouter Structured Output Test
 * Tests MiniMax M2.5 and Kimi K2.5 for structured output capability.
 *
 * Models:
 *   minimax/minimax-m2.5
 *   moonshotai/kimi-k2.5
 *
 * Structured output modes tested:
 *   1. json_object  — basic JSON mode (just "return valid JSON")
 *   2. json_schema  — strict schema enforcement (OpenAI-style native structured output)
 *
 * Run with: node test_openrouter_structured.mjs
 */

const OPENROUTER_API_KEY = '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';
const BASE_URL = 'https://openrouter.ai/api/v1/chat/completions';

const MODELS = [
  'minimax/minimax-m2.5',
  'moonshotai/kimi-k2.5',
];

// ─── Schemas ────────────────────────────────────────────────────────────────

/** A realistic schema matching the project's claim-validation use case */
const CLAIM_VALIDATION_SCHEMA = {
  type: 'object',
  required: ['entity_name', 'claims', 'overall_confidence'],
  additionalProperties: false,
  properties: {
    entity_name: {
      type: 'string',
      description: 'Name of the entity being validated',
    },
    claims: {
      type: 'array',
      description: 'List of validated claims',
      items: {
        type: 'object',
        required: ['claim', 'verdict', 'confidence', 'evidence'],
        additionalProperties: false,
        properties: {
          claim: { type: 'string', description: 'The claim being validated' },
          verdict: {
            type: 'string',
            enum: ['SUPPORTED', 'REFUTED', 'UNVERIFIABLE'],
            description: 'Verdict on the claim',
          },
          confidence: {
            type: 'number',
            minimum: 0,
            maximum: 1,
            description: 'Confidence score 0–1',
          },
          evidence: {
            type: 'string',
            description: 'Brief evidence or reasoning',
          },
        },
      },
    },
    overall_confidence: {
      type: 'number',
      minimum: 0,
      maximum: 1,
      description: 'Overall confidence across all claims',
    },
    notes: {
      type: 'string',
      description: 'Optional additional context or caveats',
    },
  },
};

const PROMPT_BARE = `You are a fact-checking assistant. Validate the following claims about Anthropic:

1. Anthropic was founded in 2021.
2. Anthropic was founded by former Google employees.
3. Claude is Anthropic's AI assistant.
4. Anthropic is headquartered in New York City.

Return a structured validation result with a verdict and confidence score for each claim.`;

/**
 * Soft-schema prompt: fully describes the expected JSON structure in the prompt itself.
 * This is what ai_client uses for non-Claude models (soft_schema=True).
 */
const PROMPT_SOFT_SCHEMA = `You are a fact-checking assistant. Validate the following claims about Anthropic:

1. Anthropic was founded in 2021.
2. Anthropic was founded by former Google employees.
3. Claude is Anthropic's AI assistant.
4. Anthropic is headquartered in New York City.

Return ONLY valid JSON (no markdown, no explanation) matching this exact structure:
{
  "entity_name": "Anthropic",
  "claims": [
    {
      "claim": "<the claim text>",
      "verdict": "<SUPPORTED | REFUTED | UNVERIFIABLE>",
      "confidence": <0.0 to 1.0>,
      "evidence": "<brief evidence or reasoning>"
    }
  ],
  "overall_confidence": <0.0 to 1.0>,
  "notes": "<optional caveats>"
}

IMPORTANT: Return raw JSON only. No markdown code blocks. No prose before or after.`;

const PROMPT = PROMPT_BARE;

// ─── API Call ────────────────────────────────────────────────────────────────

async function callOpenRouter({ model, responseFormat, prompt, maxTokens = 4000 }) {
  const body = {
    model,
    messages: [{ role: 'user', content: prompt }],
    temperature: 0.1,
    max_tokens: maxTokens,
    provider: { zdr: true },
    ...(responseFormat && { response_format: responseFormat }),
  };

  const start = Date.now();
  const res = await fetch(BASE_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${OPENROUTER_API_KEY}`,
      'HTTP-Referer': 'https://hyperplexity.ai',
      'X-OpenRouter-Title': 'PerplexityValidator-Test',
    },
    body: JSON.stringify(body),
  });

  const elapsed = Date.now() - start;
  const data = await res.json();
  return { data, elapsed, status: res.status };
}

// ─── Test Runner ─────────────────────────────────────────────────────────────

async function runTest({ label, model, responseFormat, prompt: testPrompt, maxTokens }) {
  console.log(`\n${'═'.repeat(70)}`);
  console.log(`TEST: ${label}`);
  console.log(`Model: ${model}`);
  console.log(`Response format: ${JSON.stringify(responseFormat ?? '(none — natural language + JSON ask)')}`);
  console.log('─'.repeat(70));

  try {
    const { data, elapsed, status } = await callOpenRouter({
      model,
      responseFormat,
      prompt: testPrompt ?? PROMPT,
      maxTokens,
    });

    if (status !== 200) {
      console.log(`❌ HTTP ${status}:`, JSON.stringify(data, null, 2));
      return { success: false, model, label, error: `HTTP ${status}`, data };
    }

    if (data.error) {
      console.log(`❌ API error:`, JSON.stringify(data.error, null, 2));
      return { success: false, model, label, error: data.error };
    }

    const content = data.choices?.[0]?.message?.content ?? '';
    const usage = data.usage ?? {};
    const finishReason = data.choices?.[0]?.finish_reason;

    console.log(`✅ Success in ${elapsed}ms | finish: ${finishReason}`);
    console.log(`   Tokens — prompt: ${usage.prompt_tokens}, completion: ${usage.completion_tokens}, total: ${usage.total_tokens}`);

    // Attempt JSON parse
    let parsed = null;
    let parseError = null;
    try {
      parsed = JSON.parse(content);
    } catch (e) {
      // Try to extract JSON block from markdown
      const match = content.match(/```(?:json)?\s*([\s\S]+?)```/);
      if (match) {
        try { parsed = JSON.parse(match[1].trim()); } catch (_) {}
      }
      if (!parsed) parseError = e.message;
    }

    if (parsed) {
      console.log(`\n   Parsed JSON ✓`);
      // Check schema compliance
      const missingRequired = CLAIM_VALIDATION_SCHEMA.required.filter(f => !(f in parsed));
      if (missingRequired.length === 0) {
        console.log(`   Schema required fields ✓ (all present)`);
        const claims = parsed.claims ?? [];
        console.log(`   Claims validated: ${claims.length}`);
        for (const c of claims) {
          const bar = '▓'.repeat(Math.round((c.confidence ?? 0) * 10));
          console.log(`     [${c.verdict?.padEnd(12)}] ${bar.padEnd(10)} ${(c.confidence ?? 0).toFixed(2)} — "${c.claim?.substring(0, 60)}"`);
        }
        console.log(`   Overall confidence: ${parsed.overall_confidence}`);
      } else {
        console.log(`   ⚠️  Missing required fields: ${missingRequired.join(', ')}`);
      }

      // Check for additionalProperties violations
      const extraKeys = Object.keys(parsed).filter(k => !(k in CLAIM_VALIDATION_SCHEMA.properties));
      if (extraKeys.length > 0) {
        console.log(`   ⚠️  Extra keys (additionalProperties violation): ${extraKeys.join(', ')}`);
      }
    } else {
      console.log(`   ❌ Could not parse JSON: ${parseError}`);
      console.log(`\n   Raw content (first 500 chars):\n   ${content.substring(0, 500)}`);
    }

    return { success: true, model, label, parsed, elapsed, usage, finishReason };

  } catch (err) {
    console.log(`❌ Fetch error: ${err.message}`);
    return { success: false, model, label, error: err.message };
  }
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  console.log('OpenRouter Structured Output Test');
  console.log('Models: MiniMax M2.5, Kimi K2.5');
  console.log('ZDR: enabled (provider.zdr = true)');
  console.log(new Date().toISOString());

  const tests = [];

  for (const model of MODELS) {
    // Test 1: Soft schema — schema fully described in prompt + json_object mode
    // (mirrors how ai_client works for non-Claude models: soft_schema=True)
    tests.push({
      label: 'soft schema (prompt desc + json_object)',
      model,
      prompt: PROMPT_SOFT_SCHEMA,
      responseFormat: { type: 'json_object' },
      maxTokens: 1000,
    });

    // Test 2: json_schema mode (OpenAI-native structured output), higher token budget
    tests.push({
      label: 'json_schema mode (strict)',
      model,
      prompt: PROMPT_BARE,
      responseFormat: {
        type: 'json_schema',
        json_schema: {
          name: 'claim_validation_result',
          strict: true,
          schema: CLAIM_VALIDATION_SCHEMA,
        },
      },
      maxTokens: 8000,
    });

    // Test 3: json_object mode, bare prompt (no schema description)
    tests.push({
      label: 'json_object (bare prompt)',
      model,
      prompt: PROMPT_BARE,
      responseFormat: { type: 'json_object' },
      maxTokens: 4000,
    });
  }

  const results = [];
  for (const t of tests) {
    const r = await runTest(t);
    results.push(r);
  }

  // ─── Summary ───────────────────────────────────────────────────────────────
  console.log(`\n${'═'.repeat(70)}`);
  console.log('SUMMARY');
  console.log('─'.repeat(70));

  const byModel = {};
  for (const r of results) {
    if (!byModel[r.model]) byModel[r.model] = [];
    byModel[r.model].push(r);
  }

  for (const [model, mrs] of Object.entries(byModel)) {
    console.log(`\n${model}`);
    for (const r of mrs) {
      const icon = r.success && r.parsed ? '✅' : r.success ? '⚠️ ' : '❌';
      const time = r.elapsed ? `${r.elapsed}ms` : '—';
      const tokens = r.usage?.total_tokens ? `${r.usage.total_tokens} tok` : '';
      const schemaOk = r.parsed
        ? CLAIM_VALIDATION_SCHEMA.required.every(f => f in r.parsed)
          ? 'schema✓'
          : 'schema⚠️'
        : 'no JSON';
      console.log(`  ${icon} ${r.label.padEnd(35)} ${time.padStart(7)}  ${tokens.padStart(8)}  ${schemaOk}`);
    }
  }

  console.log('\nDone.');
}

main().catch(console.error);
