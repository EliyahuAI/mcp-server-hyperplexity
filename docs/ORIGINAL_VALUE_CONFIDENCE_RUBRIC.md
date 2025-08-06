# Original Value Confidence Rubric

## 3-Level Confidence Assessment for Original Values

### Core Principle
Only assign confidence when there's a validation decision to make. No confidence color for blanks that remain blank.

### GREEN - Original value is correct
**No update needed**
- Matches authoritative sources
- Verified as accurate and current
- Only minor formatting differences (if any)

### YELLOW - Original value needs minor adjustment
**Small to moderate updates**
- Minor corrections needed (formatting, precision)
- Moderate uncertainty about the proposed change
- Update is somewhat different but not substantial

### RED - Original value is wrong
**Substantial update needed**
- Contradicts authoritative sources
- Significantly different from verified information
- Blank original that now has a verified value

## Special Rules

1. **Blank Originals**:
   - If staying blank: NO confidence assignment (no color)
   - If filling with value: RED (substantial change)

2. **Quick Decision Logic**:
   - No update needed → GREEN
   - Minor/moderate update → YELLOW
   - Major update → RED
   - Blank staying blank → NO COLOR

## Implementation Note
```json
{
  "original_confidence": {
    "type": "string",
    "enum": ["GREEN", "YELLOW", "RED", null],
    "description": "null when blank remains blank, otherwise confidence in original"
  }
}
```