# SEO Deployment Instructions - Separate Domains

**IMPORTANT:** Each domain needs its own sitemap and robots.txt file!

---

## For eliyahu.ai

### 1. Upload Sitemap
**File:** `sitemap_eliyahu_ai.xml`
**Upload as:** `sitemap.xml`
**Location:** Root directory of eliyahu.ai
**URL should be:** https://eliyahu.ai/sitemap.xml

### 2. Upload Robots.txt
**File:** `robots_eliyahu_ai.txt`
**Upload as:** `robots.txt`
**Location:** Root directory of eliyahu.ai
**URL should be:** https://eliyahu.ai/robots.txt

### 3. Update Frontend File
**File:** `frontend/perplexity_validator_interface2.html`
**Upload to:** Squarespace (replace existing file)
**URL:** https://eliyahu.ai/hyperplexity

---

## For hyperplexity.ai

### 1. Upload Sitemap
**File:** `sitemap_hyperplexity_ai.xml`
**Upload as:** `sitemap.xml`
**Location:** Root directory of hyperplexity.ai
**URL should be:** https://hyperplexity.ai/sitemap.xml

### 2. Upload Robots.txt
**File:** `robots_hyperplexity_ai.txt`
**Upload as:** `robots.txt`
**Location:** Root directory of hyperplexity.ai
**URL should be:** https://hyperplexity.ai/robots.txt

### 3. Update Frontend File
**File:** `frontend/index.html`
**Upload to:** hyperplexity.ai root
**URL:** https://hyperplexity.ai/

---

## Verification Steps

### After Deploying to eliyahu.ai:
1. Visit https://eliyahu.ai/sitemap.xml (should show XML)
2. Visit https://eliyahu.ai/robots.txt (should show text file)
3. Visit https://eliyahu.ai/hyperplexity (should load with new meta tags)
4. Check browser console for errors (F12)
5. View page source - verify meta tags are present

### After Deploying to hyperplexity.ai:
1. Visit https://hyperplexity.ai/sitemap.xml (should show XML)
2. Visit https://hyperplexity.ai/robots.txt (should show text file)
3. Visit https://hyperplexity.ai/ (should show "Hyperplexity" not "hyperplexity.ai")
4. Check browser console for errors (F12)
5. View page source - verify meta tags are present

---

## Search Engine Submission

### Google Search Console

**For eliyahu.ai:**
1. Go to: https://search.google.com/search-console
2. Add property: eliyahu.ai
3. Verify ownership (multiple methods available)
4. Submit sitemap: https://eliyahu.ai/sitemap.xml
5. Request indexing for:
   - https://eliyahu.ai/
   - https://eliyahu.ai/hyperplexity

**For hyperplexity.ai:**
1. Go to: https://search.google.com/search-console
2. Add property: hyperplexity.ai
3. Verify ownership
4. Submit sitemap: https://hyperplexity.ai/sitemap.xml
5. Request indexing for:
   - https://hyperplexity.ai/

### Bing Webmaster Tools

**For eliyahu.ai:**
1. Go to: https://www.bing.com/webmasters
2. Add site: eliyahu.ai
3. Verify ownership
4. Submit sitemap: https://eliyahu.ai/sitemap.xml

**For hyperplexity.ai:**
1. Go to: https://www.bing.com/webmasters
2. Add site: hyperplexity.ai
3. Verify ownership
4. Submit sitemap: https://hyperplexity.ai/sitemap.xml

---

## File Mapping Summary

| Original File | Deploy to eliyahu.ai as | Deploy to hyperplexity.ai as |
|---------------|-------------------------|------------------------------|
| sitemap_eliyahu_ai.xml | sitemap.xml | - |
| sitemap_hyperplexity_ai.xml | - | sitemap.xml |
| robots_eliyahu_ai.txt | robots.txt | - |
| robots_hyperplexity_ai.txt | - | robots.txt |
| frontend/perplexity_validator_interface2.html | (Squarespace) /hyperplexity | - |
| frontend/index.html | - | index.html |

---

## Why Separate Sitemaps?

Each domain must have its own sitemap because:

1. **Domain specificity:** Sitemaps should only list URLs from their own domain
2. **Search engine requirements:** Google/Bing expect sitemap URLs to match the domain
3. **Crawl efficiency:** Helps search engines understand your site structure
4. **Validation:** Tools will flag errors if sitemap contains cross-domain URLs

**WRONG:** ❌
- eliyahu.ai/sitemap.xml listing https://hyperplexity.ai/ URLs

**CORRECT:** ✅
- eliyahu.ai/sitemap.xml lists only eliyahu.ai URLs
- hyperplexity.ai/sitemap.xml lists only hyperplexity.ai URLs

---

## Quick Checklist

### Before Deployment
- [ ] Both frontend files updated with SEO meta tags
- [ ] Separate sitemap files ready for each domain
- [ ] Separate robots.txt files ready for each domain
- [ ] Social media images created (optional, can add later)

### Deploy to eliyahu.ai
- [ ] Upload sitemap_eliyahu_ai.xml as sitemap.xml
- [ ] Upload robots_eliyahu_ai.txt as robots.txt
- [ ] Upload perplexity_validator_interface2.html to Squarespace
- [ ] Test all URLs work
- [ ] Verify meta tags in page source

### Deploy to hyperplexity.ai
- [ ] Upload sitemap_hyperplexity_ai.xml as sitemap.xml
- [ ] Upload robots_hyperplexity_ai.txt as robots.txt
- [ ] Upload index.html
- [ ] Test URL works
- [ ] Verify meta tags in page source
- [ ] Verify text shows "Hyperplexity" not "hyperplexity.ai"

### Post-Deployment
- [ ] Submit both sitemaps to Google Search Console
- [ ] Submit both sitemaps to Bing Webmaster
- [ ] Request indexing for both sites
- [ ] Test with Rich Results Test tool
- [ ] Test with Twitter Card Validator
- [ ] Test with Facebook Debugger

---

## Troubleshooting

**Sitemap not accessible (404 error):**
- Verify file is named exactly `sitemap.xml` (not sitemap_eliyahu_ai.xml)
- Check file is in root directory
- Clear CDN cache if using one

**Robots.txt not working:**
- Verify file is named exactly `robots.txt` (not robots_eliyahu_ai.txt)
- Check file is in root directory
- Ensure proper line endings (use Unix/LF not Windows CRLF)

**Meta tags not appearing:**
- Clear browser cache (Ctrl+Shift+R)
- Check for JavaScript errors in console
- On Squarespace: ensure code block is in header injection

**Search engines not picking up sitemap:**
- Wait 24-48 hours after submission
- Manually request indexing in Search Console
- Check for errors in Search Console coverage report

---

## Need Help?

Reference these files for additional guidance:
- `IMPLEMENTATION_GUIDE.md` - Full implementation details
- `FRONTEND_CHANGES.md` - What was changed and why
- `seo_llm_content_strategy.md` - Content strategy
- `seo_meta_tags.html` - Reference for all meta tags
- `seo_schema_data.json` - Additional schema examples

---

**Created:** 2025-11-04
**Branch:** seo
**Status:** Ready for deployment
