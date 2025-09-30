### **Objective**

Implement a frontend change to display a discount for the initial run of a demo. The backend will identify when a run is free and will set the `estimated_cost` to `0`, providing the true cost in a separate `original_cost` field. The frontend must display this discount to the user.

### **Required Backend Behavior (Context for Frontend Implementation)**

The frontend implementation relies on the following backend behavior:

1.  **Standard Cost Response:** For a normal, paid validation, the backend's `get_cost_estimate` action returns a standard `cost_estimates` object.
    ```json
    {
      "cost_estimates": {
        "quoted_validation_cost": 12.50
      }
    }
    ```

2.  **Discounted Cost Response:** For a free initial demo run, the backend will calculate the true cost but return a modified `cost_estimates` object.
    ```json
    {
      "cost_estimates": {
        "quoted_validation_cost": 0,
        "original_cost": 12.50 
      }
    }
    ```
    *   `quoted_validation_cost` (the chargeable cost) is `0`.
    *   `original_cost` (a new field) contains the true cost for display purposes.

### **Frontend Implementation Plan**

The task is to modify the UI to correctly display either the standard cost or the detailed discount view, based on the API response from the backend.

**1. File to Modify:**
*   `/mnt/c/Users/ellio/OneDrive - Eliyahu.AI/Desktop/src/perplexityValidator/frontend/perplexity_validator_interface2.html`

**2. Function to Modify:**
*   `showPreviewResults(cardId, previewData)`

**3. Action: Replace a Code Block**
*   Within the `showPreviewResults` function, locate and **replace** the following code block.

**Code to Replace:**
```javascript
                        // Fix field name mismatch: backend uses quoted_validation_cost, frontend was looking for quoted_full_cost
                        const estimatedCost = previewData.cost_estimates.quoted_validation_cost || previewData.cost_estimates.quoted_full_cost || 0;
                        const estimatedTime = previewData.cost_estimates.estimated_validation_time || 0;
                        
                        let estimatesHtml = '';
                        
                        if (totalRows > 0) {
                            estimatesHtml += `<div class="cost-item"><span class="cost-label">Total Rows</span><span class="cost-value">${totalRows.toLocaleString()}</span></div>`;
                        }
                        
                        if (metrics.validated_columns_count) {
                            estimatesHtml += `<div class="cost-item"><span class="cost-label">Columns to Validate</span><span class="cost-value">${metrics.validated_columns_count}</span></div>`;
                        }
                        
                        const perplexityGroups = (metrics.search_groups_count || 0) - (metrics.claude_search_groups_count || 0);
                        const claudeGroups = metrics.claude_search_groups_count || 0;
                        
                        if (perplexityGroups > 0) {
                            const totalPerplexityCalls = totalRows * perplexityGroups;
                            estimatesHtml += `<div class="cost-item"><span class="cost-label">Perplexity Calls</span><span class="cost-value">${totalPerplexityCalls.toLocaleString()}</span></div>`;
                        }
                        
                        if (claudeGroups > 0) {
                            const totalClaudeCalls = totalRows * claudeGroups;
                            estimatesHtml += `<div class="cost-item"><span class="cost-label">Claude Calls</span><span class="cost-value">${totalClaudeCalls.toLocaleString()}</span></div>`;
                        }
                        
                        estimatesHtml += `<div class="cost-item"><span class="cost-label">Est. Time</span><span class="cost-value">${Math.ceil(estimatedTime / 60)} min</span></div>`;
                        estimatesHtml += `<div class="cost-item"><span class="cost-label">Cost</span><span class="cost-value">$${estimatedCost.toFixed(2)}</span></div>`;
                        
                        // Domain multiplier is hidden from frontend display
                        
                        // Add account balance information if available
                        if (previewData.account_info) {
                            const accountInfo = previewData.account_info;
                            const currentBalance = accountInfo.current_balance || 0;
                            const sufficientBalance = accountInfo.sufficient_balance;
                            const creditsNeeded = accountInfo.credits_needed || 0;
                            
                            estimatesHtml += `<hr style="margin: 10px 0; border: none; border-top: 1px solid #eee;">`;
                            estimatesHtml += `<div class="cost-item"><span class="cost-label">Your Balance</span><span class="cost-value">$${currentBalance.toFixed(2)}</span></div>`;
                            
                            if (!sufficientBalance && creditsNeeded > 0) {
                                estimatesHtml += `<div class="cost-item"><span class="cost-label" style="color: #f44336;">Credits Needed</span><span class="cost-value" style="color: #f44336;">$${creditsNeeded.toFixed(2)}</span></div>`;
                            }
                        }
```

**Replacement Code:**
```javascript
                        // Fix field name mismatch: backend uses quoted_validation_cost, frontend was looking for quoted_full_cost
                        const estimatedCost = previewData.cost_estimates.quoted_validation_cost || previewData.cost_estimates.quoted_full_cost || 0;
                        const originalCost = previewData.cost_estimates.original_cost || null;
                        const estimatedTime = previewData.cost_estimates.estimated_validation_time || 0;
                        
                        let estimatesHtml = '';
                        
                        if (totalRows > 0) {
                            estimatesHtml += `<div class="cost-item"><span class="cost-label">Total Rows</span><span class="cost-value">${totalRows.toLocaleString()}</span></div>`;
                        }
                        
                        if (metrics.validated_columns_count) {
                            estimatesHtml += `<div class="cost-item"><span class="cost-label">Columns to Validate</span><span class="cost-value">${metrics.validated_columns_count}</span></div>`;
                        }
                        
                        const perplexityGroups = (metrics.search_groups_count || 0) - (metrics.claude_search_groups_count || 0);
                        const claudeGroups = metrics.claude_search_groups_count || 0;
                        
                        if (perplexityGroups > 0) {
                            const totalPerplexityCalls = totalRows * perplexityGroups;
                            estimatesHtml += `<div class="cost-item"><span class="cost-label">Perplexity Calls</span><span class="cost-value">${totalPerplexityCalls.toLocaleString()}</span></div>`;
                        }
                        
                        if (claudeGroups > 0) {
                            const totalClaudeCalls = totalRows * claudeGroups;
                            estimatesHtml += `<div class="cost-item"><span class="cost-label">Claude Calls</span><span class="cost-value">${totalClaudeCalls.toLocaleString()}</span></div>`;
                        }
                        
                        estimatesHtml += `<div class="cost-item"><span class="cost-label">Est. Time</span><span class="cost-value">${Math.ceil(estimatedTime / 60)} min</span></div>`;

                        if (originalCost && originalCost > estimatedCost) {
                            const discount = originalCost - estimatedCost;
                            estimatesHtml += `<div class="cost-item"><span class="cost-label">Original Cost</span><span class="cost-value">$${originalCost.toFixed(2)}</span></div>`;
                            estimatesHtml += `<div class="cost-item"><span class="cost-label" style="color: var(--primary-color);">Demo Discount</span><span class="cost-value" style="color: var(--primary-color);">- $${discount.toFixed(2)}</span></div>`;
                            estimatesHtml += `<div class="cost-item"><span class="cost-label">Total Cost</span><span class="cost-value" style="font-weight: bold;">$${estimatedCost.toFixed(2)}</span></div>`;
                        } else {
                            estimatesHtml += `<div class="cost-item"><span class="cost-label">Cost</span><span class="cost-value">$${estimatedCost.toFixed(2)}</span></div>`;
                        }
                        
                        // Domain multiplier is hidden from frontend display
                        
                        // Add account balance information if available
                        if (previewData.account_info) {
                            const accountInfo = previewData.account_info;
                            const currentBalance = accountInfo.current_balance || 0;
                            const sufficientBalance = accountInfo.sufficient_balance;
                            const creditsNeeded = accountInfo.credits_needed || 0;
                            
                            estimatesHtml += `<hr style="margin: 10px 0; border: none; border-top: 1px solid #eee;">`;
                            estimatesHtml += `<div class="cost-item"><span class="cost-label">Your Balance</span><span class="cost-value">$${currentBalance.toFixed(2)}</span></div>`;
                            
                            if (!sufficientBalance && creditsNeeded > 0) {
                                estimatesHtml += `<div class="cost-item"><span class="cost-label" style="color: #f44336;">Credits Needed</span><span class="cost-value" style="color: #f44336;">$${creditsNeeded.toFixed(2)}</span></div>`;
                            }
                        }
```