# Config Probe Report

**Generated:** 2026-03-03 18:34:05 UTC

Tables uploaded without explicit configuration. First column header pluralized (+s) to avoid config cache hits.

## Summary

| test | match | qc | qc_model | group | capability | model | viewer |
|---|---|---|---|---|---|---|---|
| test_10 | 0 | False | — | Culinary Profile & Reputation | Ql | sonar-pro | [view](https://eliyahu.ai/viewer?session=session_20260303_183328_a3d1d250) |

## Per-Test Detail

### test_10 — test_10_brooklyn_pizza.csv

- **session_id:** `session_20260303_183328_a3d1d250`
- **conv_id:** `upload_conv_bec675214315`
- **viewer:** https://eliyahu.ai/viewer?session=session_20260303_183328_a3d1d250
- **match_count:** 0  perfect: False
- **s3_config:** `results/eliyahu.ai/eliyahu/session_20260303_183328_a3d1d250/config_v1_ai_generated.json`

```json
{
  "search_groups": [
    {
      "group_id": 1,
      "group_name": "Culinary Profile & Reputation",
      "capability": "Ql",
      "model": "sonar-pro",
      "columns": [
        "Style",
        "Known For"
      ],
      "description": "Validation of pizza styles and specific claims regarding signature features or operational details."
    }
  ],
  "qc_enable": false,
  "qc_model": null
}
```

