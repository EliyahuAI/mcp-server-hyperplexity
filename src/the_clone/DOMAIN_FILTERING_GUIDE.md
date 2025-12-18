Quick Reference:

  Academic Mode:
  clone = TheClone2Refined()
  result = await clone.query("CRISPR research", academic=True)
  # Uses 20 academic domains automatically

  Custom Whitelist:
  result = await clone.query(
      "AI news",
      include_domains=["nytimes.com", "wsj.com", "reuters.com"]
  )

  Blacklist:
  result = await clone.query(
      "Python tips",
      exclude_domains=["reddit.com", "quora.com"]
  )

  Priority:
  1. academic=True → 20 academic domains
  2. include_domains=[...] → Your whitelist
  3. exclude_domains=[...] → Blacklist (only if no include)
  4. No filters → All domains

  Full documentation: src/the_clone/DOMAIN_FILTERING_GUIDE.md