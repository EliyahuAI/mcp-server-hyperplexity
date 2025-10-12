# Discount System

## Overview

The discount system provides automatic cost reductions for qualifying validation runs. Currently, it offers 100% discount for demo sessions using v1 configurations.

## Business Rules

- **Demo sessions with v1 configs**: 100% discount (free)
- **All other sessions**: No discount

A session qualifies as a "demo" if its `session_id` contains the word "demo" (case-insensitive).

## Architecture

### Discount Calculation

**Function**: `calculate_discount()` in `background_handler.py:423`

```python
def calculate_discount(session_id: str, config_version: int, quoted_validation_cost: float) -> float
```

**Logic**:
```python
is_demo = 'demo' in session_id.lower()
is_v1_config = (config_version == 1)

if is_demo and is_v1_config:
    return quoted_validation_cost  # 100% discount
else:
    return 0.0  # No discount
```

### Cost Flow

1. **Raw Cost Calculation**: System calculates base `eliyahu_cost` from API usage
2. **Domain Multiplier**: Applied to get `charged_cost` (customer-facing price)
3. **Discount Application**: `discount = calculate_discount(...)`
4. **Effective Cost**: `effective_cost = charged_cost - discount`
5. **Billing**: User is charged `effective_cost` (what they actually pay)

## Implementation Details

### Backend (background_handler.py)

#### Preview Mode (Lines 1915-1924)
```python
discount = calculate_discount(session_id, config_version, quoted_full_cost)
effective_cost = max(0.0, quoted_full_cost - discount)
```

#### Full Validation Mode (Lines 3818-3853)
```python
# Try to get discount from preview data first
discount = preview_data.get('discount') if preview_data else 0.0

# If not available, recalculate
if discount is None:
    config_version = config_data.get('storage_metadata', {}).get('version', 1)
    discount = calculate_discount(session_id, config_version, charged_cost)

effective_cost = max(0.0, charged_cost - discount)
charged_amount = effective_cost  # CRITICAL: Use effective_cost for billing
```

### API Response Format

#### Standard (No Discount)
```json
{
  "cost_estimates": {
    "quoted_validation_cost": 12.50,
    "discount": 0.0,
    "effective_cost": 12.50
  }
}
```

#### With Discount
```json
{
  "cost_estimates": {
    "quoted_validation_cost": 0.00,
    "original_cost": 12.50,
    "discount": 12.50,
    "effective_cost": 0.00
  }
}
```

**Key Fields**:
- `quoted_validation_cost`: What user will actually pay (after discount)
- `original_cost`: Original price before discount (only present when discount > 0)
- `discount`: Discount amount applied
- `effective_cost`: Final cost after discount

**Locations**: Lines 2104-2120, 2503-2529 in `background_handler.py`

### Frontend Display (perplexity_validator_interface2.html)

**Function**: `showPreviewResults()`

```javascript
const estimatedCost = previewData.cost_estimates.quoted_validation_cost || 0;
const originalCost = previewData.cost_estimates.original_cost || null;

if (originalCost && originalCost > estimatedCost) {
    const discount = originalCost - estimatedCost;
    // Display: Original Cost, Demo Discount, Total Cost
    estimatesHtml += `Original Cost: $${originalCost.toFixed(2)}`;
    estimatesHtml += `Demo Discount: -$${discount.toFixed(2)}`;
    estimatesHtml += `Total Cost: $${estimatedCost.toFixed(2)}`;
} else {
    // Display: Cost
    estimatesHtml += `Cost: $${estimatedCost.toFixed(2)}`;
}
```

### Email & Receipt Behavior (email_sender.py)

#### Cost Display in Email (Lines 946-953)
```python
cost = billing_info.get('amount_charged', 0)
if cost > 0:
    cost_info = f"<p><b>Cost:</b> ${cost:.2f}</p>"
```

**Result**:
- Free demos: No cost line in email
- Paid runs: Cost line displayed

#### Receipt Attachment (Lines 689)
```python
if billing_info and billing_info.get('amount_charged', 0) > 0 and not preview_email:
    # Generate and attach receipt
```

**Result**:
- Free demos: No receipt attached
- Paid runs: Receipt attached

### Billing (background_handler.py)

#### Balance Deduction (Lines 4576-4590)
```python
if not is_preview and effective_cost > 0:
    deduct_success = deduct_from_balance(
        email=email,
        amount=Decimal(str(effective_cost)),  # Uses discounted price
        session_id=session_id,
        description=f"Full validation - {rows} rows" +
                   (f" (${discount:.2f} discount applied)" if discount > 0 else ""),
        run_key=run_key  # Prevents duplicate charges
    )
```

**Result**:
- Free demos: No balance deduction (effective_cost = 0)
- Paid runs: Deducts effective_cost from balance

## Data Flow Example

### Demo Session Example

**Input**:
- `session_id`: "user123_demo_2024"
- `config_version`: 1
- `eliyahu_cost`: $5.00
- `multiplier`: 2.5

**Calculation**:
```
charged_cost = eliyahu_cost * multiplier = $5.00 * 2.5 = $12.50
discount = calculate_discount("demo", 1, $12.50) = $12.50
effective_cost = $12.50 - $12.50 = $0.00
charged_amount = $0.00
```

**Results**:
- ✅ User pays: $0.00
- ✅ Balance change: $0.00
- ✅ Email shows: No cost line
- ✅ Receipt: Not attached
- ✅ Frontend displays: "Original Cost: $12.50, Demo Discount: -$12.50, Total: $0.00"

### Regular Session Example

**Input**:
- `session_id`: "user123_prod_2024"
- `config_version`: 2
- `eliyahu_cost`: $5.00
- `multiplier`: 2.5

**Calculation**:
```
charged_cost = eliyahu_cost * multiplier = $5.00 * 2.5 = $12.50
discount = calculate_discount("prod", 2, $12.50) = $0.00
effective_cost = $12.50 - $0.00 = $12.50
charged_amount = $12.50
```

**Results**:
- ✅ User pays: $12.50
- ✅ Balance change: -$12.50
- ✅ Email shows: "Cost: $12.50"
- ✅ Receipt: Attached
- ✅ Frontend displays: "Cost: $12.50"

## Testing

### Manual Testing

Test a demo session:
```bash
# Session ID must contain "demo"
session_id = "user@example.com_demo_20241012"
config_version = 1
```

**Expected**:
- Preview shows $0 cost with discount breakdown
- Full validation completes without charging
- Email has no cost line
- No receipt attached
- Balance unchanged

### Key Files to Verify

1. **backend_handler.py**:
   - Line 423: `calculate_discount()` logic
   - Line 3933: `charged_amount = effective_cost`
   - Lines 2106, 2504: `quoted_validation_cost = effective_cost`

2. **email_sender.py**:
   - Line 689: Receipt attachment conditional
   - Line 946: Cost display conditional

3. **frontend**:
   - `showPreviewResults()`: Discount display logic

## Troubleshooting

### Issue: Demo showing cost in email
**Cause**: `charged_amount` not set to `effective_cost`
**Fix**: Verify line 3933 in `background_handler.py`

### Issue: Receipt attached for free demo
**Cause**: `billing_info['amount_charged']` > 0
**Fix**: Trace `charged_amount` assignment through billing_info creation

### Issue: Balance decreases for demo
**Cause**: Billing logic using wrong cost variable
**Fix**: Verify line 4584 uses `effective_cost` in `deduct_from_balance()`

### Issue: Frontend not showing discount
**Cause**: Backend not sending `original_cost` field
**Fix**: Verify lines 2117-2118, 2511-2512 add `original_cost` when discount > 0

## Future Enhancements

Potential discount rules to add:
- Promotional codes
- Volume discounts (e.g., 10% off for 10k+ rows)
- Subscription tiers
- Loyalty discounts
- Seasonal promotions

**To Add New Rule**:
1. Update `calculate_discount()` function
2. Add business logic conditions
3. Update this documentation
4. Add tests
