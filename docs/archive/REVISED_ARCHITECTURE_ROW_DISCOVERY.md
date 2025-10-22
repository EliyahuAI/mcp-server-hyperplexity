# Revised Architecture - Row Discovery with Integrated Scoring

**Date:** October 20, 2025
**Status:** Architecture Revision Before Testing

---

## Key Architectural Changes

### 1. Scoring Happens During Search (Not After)

**OLD FLOW (What We Built):**
```
Web Search (sonar-pro) → Get results →
  LLM Scoring (claude) → Score each candidate →
    Return scored candidates
```
**PROBLEMS:**
- Two separate calls per subdomain
- Scoring disconnected from search context
- Extra latency and cost

**NEW FLOW (Revised):**
```
Web Search with Integrated Scoring (sonar-pro) →
  Returns pre-scored candidates directly
```

**IMPLEMENTATION:**
```python
# In row_discovery_stream.py
result = await self.ai_client.validate_with_perplexity(
    prompt=f"""
Find and score AI companies for: {subdomain['focus']}

For each company found, provide:
- Company name and website
- Match score (0-1) based on:
  * Relevancy to requirements (40%)
  * Source reliability (30%)
  * Recency (30%)

SCORING RUBRIC:
- 0.9-1.0: Perfect match, reliable sources (company site, Crunchbase), info <3 months old
- 0.7-0.89: Strong match, good sources (tech news, LinkedIn), info <6 months old
- 0.5-0.69: Moderate match, decent sources, info <12 months old
- <0.5: Weak match, unreliable sources, or outdated info

Return JSON: {{"candidates": [{{"company": "...", "website": "...", "score": 0.95, "rationale": "..."}}]}}
    """,
    model='sonar-pro',
    search_context_size='high',
    return_json=True
)
```

**BENEFITS:**
- One call instead of two per subdomain
- Scoring aware of search context and sources
- Faster and cheaper
- Recency built into scoring

---

### 2. Subdomains Defined in Column Definition (Not Separate Call)

**OLD FLOW (What We Built):**
```
Column Definition → search_strategy →
  Subdomain Analysis (separate AI call) → subdomains →
    Row Discovery
```

**NEW FLOW (Revised):**
```
Column Definition → columns + search_strategy + subdomains →
  Row Discovery (uses subdomains directly)
```

**SCHEMA UPDATE (`column_definition_response.json`):**
```json
{
  "columns": [...],
  "search_strategy": {
    "description": "...",
    "search_queries": [...],
    "subdomains": [  // NEW: Moved here from separate call
      {
        "name": "AI Research Companies",
        "focus": "Academic/research-focused AI companies",
        "search_queries": ["..."],
        "target_rows": 7  // Distribute 20 rows across subdomains
      },
      {
        "name": "Healthcare AI",
        "focus": "AI in healthcare/biotech",
        "search_queries": ["..."],
        "target_rows": 7
      },
      {
        "name": "Enterprise AI",
        "focus": "B2B AI solutions",
        "search_queries": ["..."],
        "target_rows": 6
      }
    ]
  },
  "table_name": "..."
}
```

**BENEFITS:**
- One fewer AI call (saves ~3-5s and ~$0.01-0.02)
- Subdomains designed with column context in mind
- More coherent search strategy

---

### 3. Scoring Rubric (Concise Anchoring System)

**THREE DIMENSIONS (100 points total):**

#### Relevancy to Requirements (40 points)
- **36-40:** Perfect match to all requirements
- **28-35:** Matches most requirements, minor gaps
- **20-27:** Matches core requirements, notable gaps
- **<20:** Weak match to requirements

#### Source Reliability (30 points)
- **27-30:** Primary sources (company site, official docs, Crunchbase)
- **21-26:** Secondary sources (TechCrunch, LinkedIn, reputable news)
- **15-20:** Tertiary sources (blogs, forums, aggregators)
- **<15:** Unreliable or unverified sources

#### Recency (30 points)
- **27-30:** Information <3 months old
- **21-26:** Information 3-6 months old
- **15-20:** Information 6-12 months old
- **<15:** Information >12 months old or undated

**FINAL SCORE:** Sum / 100 = 0.0-1.0

**EXAMPLE:**
- Anthropic: Relevancy 38/40 + Reliability 28/30 + Recency 29/30 = 95/100 = **0.95**
- Small Startup: Relevancy 32/40 + Reliability 18/30 + Recency 22/30 = 72/100 = **0.72**

---

### 4. WebSocket Management for Parallel Operations

**PROBLEM:**
Multiple parallel streams trying to send WebSocket messages simultaneously:
- Race conditions
- Out-of-order messages
- Confusing user experience

**SOLUTION: WebSocket Queue with Rules**

```python
class WebSocketQueue:
    """Thread-safe queue for WebSocket messages with ordering rules."""

    def __init__(self, websocket_client, session_id):
        self.websocket_client = websocket_client
        self.session_id = session_id
        self.message_queue = asyncio.Queue()
        self.is_running = False

    async def send(self, message: Dict[str, Any], priority: str = 'normal'):
        """
        Queue a message for sending.

        Priority levels:
        - 'critical': Errors, completion (send immediately)
        - 'high': Step transitions (buffer 1s)
        - 'normal': Progress updates (buffer 3s, aggregate)
        """
        await self.message_queue.put({
            'message': message,
            'priority': priority,
            'timestamp': time.time()
        })

    async def process_queue(self):
        """Process queued messages with aggregation rules."""
        self.is_running = True
        last_sent = 0
        aggregated_updates = []

        while self.is_running:
            try:
                # Wait for messages with timeout
                item = await asyncio.wait_for(
                    self.message_queue.get(),
                    timeout=1.0
                )

                priority = item['priority']
                message = item['message']

                if priority == 'critical':
                    # Send immediately
                    self._send_now(message)
                    last_sent = time.time()

                elif priority == 'high':
                    # Buffer 1 second
                    if time.time() - last_sent >= 1.0:
                        self._send_now(message)
                        last_sent = time.time()
                    else:
                        await asyncio.sleep(1.0 - (time.time() - last_sent))
                        self._send_now(message)
                        last_sent = time.time()

                else:  # normal
                    # Aggregate progress updates
                    aggregated_updates.append(message)
                    if time.time() - last_sent >= 3.0:
                        # Send aggregated update
                        combined = self._aggregate_messages(aggregated_updates)
                        self._send_now(combined)
                        aggregated_updates = []
                        last_sent = time.time()

            except asyncio.TimeoutError:
                # No messages, send aggregated if any
                if aggregated_updates and time.time() - last_sent >= 3.0:
                    combined = self._aggregate_messages(aggregated_updates)
                    self._send_now(combined)
                    aggregated_updates = []
                    last_sent = time.time()

    def _aggregate_messages(self, messages: List[Dict]) -> Dict:
        """Combine multiple progress updates into one."""
        if not messages:
            return None

        # Take latest message, add summary of all
        latest = messages[-1]
        latest['updates_aggregated'] = len(messages)
        return latest

    def _send_now(self, message: Dict):
        """Send message via WebSocket immediately."""
        try:
            self.websocket_client.send_to_session(self.session_id, message)
        except Exception as e:
            logger.error(f"WebSocket send failed: {e}")
```

**USAGE IN PARALLEL EXECUTION:**
```python
# Initialize queue
ws_queue = WebSocketQueue(websocket_client, session_id)
queue_task = asyncio.create_task(ws_queue.process_queue())

# Parallel streams send to queue
async def run_stream(subdomain):
    # Progress update
    await ws_queue.send({
        'type': 'table_execution_update',
        'status': f'Searching {subdomain["name"]}: 5 candidates found'
    }, priority='normal')  # Will be aggregated

    # Error
    await ws_queue.send({
        'type': 'table_execution_update',
        'status': f'Stream failed: {error}'
    }, priority='critical')  # Sent immediately

# Run parallel
await asyncio.gather(*[run_stream(s) for s in subdomains])

# Cleanup
ws_queue.is_running = False
await queue_task
```

---

### 5. Sequential Testing First

**TESTING STRATEGY:**

#### Phase A: Sequential Testing (No Parallelization)
```python
# Test with max_parallel_streams=1 (force sequential)
result = await row_discovery.discover_rows(
    ...,
    max_parallel_streams=1  # Process one subdomain at a time
)
```

**VALIDATES:**
- Each component works independently
- Scoring rubric produces good results
- Deduplication works correctly
- No race conditions to debug

#### Phase B: Parallel Testing (2 streams)
```python
result = await row_discovery.discover_rows(
    ...,
    max_parallel_streams=2
)
```

**VALIDATES:**
- Parallel execution works
- WebSocket queue handles concurrency
- Results merge correctly

#### Phase C: Full Parallel (3-5 streams)
```python
result = await row_discovery.discover_rows(
    ...,
    max_parallel_streams=5
)
```

**VALIDATES:**
- Production-level parallelization
- Performance targets met
- No resource contention

---

## Revised Component Changes

### Changes Needed

#### 1. `column_definition_response.json` Schema
**ADD subdomains to search_strategy:**
```json
{
  "search_strategy": {
    "description": "...",
    "subdomains": [
      {
        "name": "...",
        "focus": "...",
        "search_queries": ["..."],
        "target_rows": 7
      }
    ]
  }
}
```

#### 2. `column_definition.md` Prompt
**ADD subdomain specification instructions:**
```markdown
## Search Strategy with Subdomains

Define 2-5 subdomains for parallel row discovery.

**Subdomain Guidelines:**
- Each subdomain covers 20-30% of search space
- Search queries prioritize MULTI-ROW results (lists, directories, comparisons)
- Distribute target_rows across subdomains (sum = target_row_count × 1.5)

**Search Query Prioritization:**
1. List-based: "Top 10 AI companies", "AI startups that raised funding"
2. Aggregator sources: Crunchbase, industry reports, directories
3. Comparative: "AI companies comparison", "Best ML research labs"
4. Specific: Single entity searches (use sparingly)
```

#### 3. `row_discovery_stream.py` - Integrated Scoring
**REPLACE** two-step process with single call:

```python
async def discover_rows(self, subdomain: Dict, columns: List, search_strategy: Dict,
                       target_rows: int = 7, scoring_model: str = 'sonar-pro') -> Dict:
    """
    Discover and score rows in one integrated call.

    Args:
        subdomain: Subdomain with name, focus, search_queries, target_rows
        columns: Column definitions
        search_strategy: Overall strategy
        target_rows: How many rows to find for this subdomain
        scoring_model: Model to use (default: sonar-pro)
    """

    # Build prompt with scoring rubric
    prompt = f"""
Find {target_rows} entities matching: {subdomain['focus']}

Requirements: {search_strategy['description']}

ID Columns: {[col['name'] for col in columns if col['is_identification']]}

SCORING RUBRIC (0-1.0 scale):
Score = (Relevancy × 0.4) + (Source Reliability × 0.3) + (Recency × 0.3)

Relevancy (0-1):
  1.0 = Perfect match to all requirements
  0.7 = Matches most requirements
  0.4 = Matches core requirements only
  0.0 = Weak or no match

Source Reliability (0-1):
  1.0 = Primary source (company site, Crunchbase, official)
  0.7 = Secondary source (TechCrunch, LinkedIn, WSJ)
  0.4 = Tertiary source (blogs, aggregators)
  0.0 = Unreliable or unverified

Recency (0-1):
  1.0 = <3 months old
  0.7 = 3-6 months old
  0.4 = 6-12 months old
  0.0 = >12 months or undated

For each entity, return:
- ID column values
- Final match score (calculated using formula above)
- Brief rationale (1 sentence explaining score)
- Source URLs used

Return JSON with candidates sorted by score descending.
"""

    # Single call to sonar-pro with scoring
    result = await self.ai_client.validate_with_perplexity(
        prompt=prompt,
        model=scoring_model,  # sonar-pro does search + scoring
        search_context_size='high',
        return_json=True,
        max_tokens=8000
    )

    # Parse and validate
    candidates = result.get('candidates', [])

    return {
        'subdomain': subdomain['name'],
        'candidates': candidates[:target_rows],  # Limit to target
        'processing_time': result.get('processing_time', 0)
    }
```

#### 4. `row_discovery.py` - Row Overshooting
```python
async def discover_rows(
    self,
    search_strategy: Dict[str, Any],
    columns: List[Dict[str, Any]],
    target_row_count: int = 20,
    discovery_multiplier: float = 1.5,  # NEW: Find 30, keep best 20
    min_match_score: float = 0.6,
    max_parallel_streams: int = 5
) -> Dict[str, Any]:
    """Discover rows with overshooting."""

    # Subdomains now come from search_strategy (not separate call)
    subdomains = search_strategy.get('subdomains', [])

    # Calculate overshooting
    total_to_find = int(target_row_count * discovery_multiplier)  # 20 × 1.5 = 30

    # Distribute across subdomains
    rows_per_subdomain = total_to_find // len(subdomains)

    # Each subdomain already has target_rows from column definition
    # Use that as the target

    # Execute streams (sequential or parallel based on max_parallel_streams)
    # ...

    # Consolidate: Get all candidates (should be ~30)
    consolidated = self.consolidator.consolidate(
        stream_results=stream_results,
        target_row_count=target_row_count,  # Final count: 20
        min_match_score=min_match_score
    )

    # Returns top 20 from ~30 candidates
```

#### 5. WebSocket Queue for Parallel Management
**NEW FILE:** `src/lambdas/interface/actions/table_maker/websocket_queue.py`

Implements the queue system described above with:
- Priority levels (critical, high, normal)
- Message aggregation for progress updates
- Thread-safe operation
- Sequential message delivery

---

## Revised Data Flow

### Column Definition Output
```json
{
  "columns": [
    {"name": "Company Name", "is_identification": true},
    {"name": "Website", "is_identification": true},
    {"name": "Is Hiring for AI?", ...}
  ],
  "search_strategy": {
    "description": "Find AI companies actively hiring",
    "subdomains": [  // DEFINED HERE, not separate call
      {
        "name": "AI Research Companies",
        "focus": "Academic and research-focused",
        "search_queries": [
          "top AI research labs hiring 2024",  // Multi-row query
          "AI research companies with job openings",  // Multi-row query
          "academic AI institutes recruiting"  // Multi-row query
        ],
        "target_rows": 10  // Overshoot: find 10 for this subdomain
      },
      {
        "name": "Healthcare AI",
        "focus": "Medical AI and biotech",
        "search_queries": [
          "healthcare AI companies list",  // Multi-row query
          "medical AI startups with FDA approval"  // Multi-row query
        ],
        "target_rows": 10  // Find 10 for this subdomain
      },
      {
        "name": "Enterprise AI",
        "focus": "B2B AI solutions",
        "search_queries": [
          "enterprise AI software companies",  // Multi-row query
          "B2B AI automation companies list"  // Multi-row query
        ],
        "target_rows": 10  // Find 10 for this subdomain
      }
    ]
  },
  "table_name": "AI Companies Hiring Status"
}
```

**TOTAL DISCOVERED:** 10 + 10 + 10 = 30 candidates
**AFTER DEDUP & SCORING:** Top 20 delivered

---

### Row Discovery Per Subdomain (Integrated Scoring)
```json
{
  "subdomain": "AI Research Companies",
  "candidates": [
    {
      "id_values": {"Company Name": "Anthropic", "Website": "anthropic.com"},
      "match_score": 0.95,
      "score_breakdown": {
        "relevancy": 0.95,    // 38/40 points
        "reliability": 0.93,  // 28/30 points
        "recency": 0.97       // 29/30 points
      },
      "match_rationale": "Leading AI safety research company. Source: anthropic.com (primary). Updated Oct 2025.",
      "source_urls": ["https://anthropic.com/careers", "https://www.crunchbase.com/..."]
    }
  ]
}
```

---

## Revised Pipeline

### STEP 1: Column Definition (~30s)
**ONE AI CALL** outputs:
- Columns (ID + research)
- Search strategy with subdomains (2-5)
- Each subdomain has: name, focus, search_queries, target_rows

### STEP 2: Parallel Execution (~90s)

**2A: Row Discovery (parallel streams)**
```
For each subdomain (parallel, up to 5):
  - Execute integrated scoring search (sonar-pro)
  - Find target_rows candidates (e.g., 10 per subdomain)
  - Return scored candidates

Consolidate:
  - Merge all streams (30 total candidates)
  - Deduplicate (fuzzy matching)
  - Filter by min_match_score (0.6)
  - Sort by score descending
  - Return top 20
```

**2B: Config Generation (parallel)**
- Runs simultaneously with row discovery
- Uses columns from Step 1

**WebSocket Updates:** Managed by queue, aggregated

### STEP 3: Table Population (~90s)
- Populate 20 rows in batches
- Use discovered IDs

### STEP 4: Validation (~10s)
- Validate complete table

---

## Changes to Implement

### Priority 1: Core Architecture
1. **Update `column_definition_response.json`** - Add subdomains to search_strategy
2. **Update `column_definition.md` prompt** - Instructions for subdomain specification
3. **Update `row_discovery_stream.py`** - Integrated scoring in single sonar-pro call
4. **Update `row_discovery.py`** - Remove subdomain_analyzer call, use subdomains from column_def
5. **Add scoring rubric** to `row_discovery.md` prompt
6. **Add `discovery_multiplier` to config** (default: 1.5)

### Priority 2: WebSocket Queue
7. **Create `websocket_queue.py`** - Queue implementation
8. **Update `execution.py`** - Use queue for parallel operations
9. **Update `row_discovery_handler.py`** - Pass queue to streams

### Priority 3: Configuration
10. **Add to config:**
```json
{
  "row_discovery": {
    "web_search_model": "sonar-pro",
    "scoring_model": "sonar-pro",  // Same model does both
    "discovery_multiplier": 1.5,
    "target_row_count": 20
  }
}
```

11. **Update row_discovery_stream.py** - Read models from config

### Priority 4: Testing
12. **Create sequential test script** (max_parallel_streams=1)
13. **Run with real API keys**
14. **Validate scoring quality**
15. **Test parallel with queue** (max_parallel_streams=2, then 5)

---

## AI Calls Comparison

### OLD (What We Built)
1. Column Definition (claude-sonnet-4-5)
2. Subdomain Analysis (claude-sonnet-4-5)
3. Row Discovery Stream 1 - Web Search (sonar-pro)
4. Row Discovery Stream 1 - Scoring (claude-sonnet-4-5)
5. Row Discovery Stream 2 - Web Search (sonar-pro)
6. Row Discovery Stream 2 - Scoring (claude-sonnet-4-5)
7. Row Discovery Stream 3 - Web Search (sonar-pro)
8. Row Discovery Stream 3 - Scoring (claude-sonnet-4-5)

**TOTAL:** 8 calls (1 + 1 + 6)

### NEW (Revised)
1. Column Definition with Subdomains (claude-sonnet-4-5)
2. Row Discovery Stream 1 - Integrated (sonar-pro)
3. Row Discovery Stream 2 - Integrated (sonar-pro)
4. Row Discovery Stream 3 - Integrated (sonar-pro)

**TOTAL:** 4 calls (1 + 3)

**SAVINGS:** 4 fewer calls, ~$0.03-0.05 per table, ~15-20 seconds faster

---

## Next Steps

**BEFORE ANY TESTING:**

1. I'll implement these architectural revisions
2. Create local sequential test script
3. You run it with your API keys
4. We validate scoring quality
5. Then we add parallelization + WebSocket queue
6. Then consolidate docs
7. Then update frontend
8. Then deploy to AWS

**ESTIMATED TIME:**
- Architectural revisions: ~45 minutes
- Local test script: ~15 minutes
- Your testing: ~10-15 minutes
- Total: ~1.5 hours to validated local system

---

**Should I proceed with implementing these architectural revisions?**
