# Config Generation & Refinement Interface Specification

## Complete UI Specification for Config Generation & Refinement

### **1. Initial Config Options**
- Two buttons: "Upload Config" or "Create Config"
- **Upload Path**: 
  - If validation fails → User confirmation: "Repair" or "Generate New"
  - If Repair → Open refine card with validation errors as first message
  - If Generate New → Follow create path
- **Create Path**: Open "Create Config Card"

### **2. Create Configuration Card**
- Explanation: "Configuration develops research strategy and provides table metadata"
- Submit button triggers config generation
- Progress tracked via unified WebSocket function

### **3. Unified WebSocket Progress System**
- **Stage** (primary): "Generating Config", "Refining Config", "Testing Config"
- **Feedback** (secondary): Creative descriptive text underneath
- Progress bar fills 75% over ~1 minute, then holds or completes when result arrives
- Reusable function for all waiting states

### **4. Conversational Chat Layout**
- AI responses: Left-aligned chat bubbles
- User inputs: Right-aligned chat bubbles
- **AI Text Streaming**: Words appear at ~10 words/second for artificial streaming effect
- **Streaming Pauses**: 0.2s pause at each period (.), comma (,), semicolon (;), or newline
- All conversations remain visible sequentially

### **5. AI Response Processing**
- **ai_summary**: Main response in chat bubble (streamed)
- **reasoning**: Used for context/logging
- **clarifying_questions**: Shown only when "Refine Again" pressed
- **clarification_urgency**: Used to determine UI emphasis/styling

### **6. Refine Config Card**
- Appears after initial generation
- Shows AI summary in chat bubble
- Text input area for user refinement requests
- "Refine" button → WebSocket progress → AI response
- Two buttons after response: "Refine Again" | "Accept"

### **7. Refinement Cycle**
- **Refine Again**: Shows stored clarifying_questions + new text input
- **Accept**: Opens preview card
- Each refinement creates new config version in unified storage
- All chat history remains visible

### **8. Post-Preview Refinement**
- "Refine Config" button appears below preview
- Same refine card expands with preview markdown included in context
- Sequential refinements and previews in same card
- New preview button after each refinement

### **9. Technical Implementation**
- Unified storage: One session, all interactions tracked
- Mobile responsive but desktop-optimized
- WebSocket integration for real-time progress
- Config versioning in backend

## AI Response Schema Elements

Every AI-generated config includes these feedback elements:

```json
{
  "clarifying_questions": {
    "type": "string",
    "description": "2-4 specific questions to help improve the configuration further"
  },
  "clarification_urgency": {
    "type": "number",
    "minimum": 0,
    "maximum": 1,
    "description": "Urgency score from 0-1: 0 = no clarification needed, 1 = critical columns will likely be wrong without clarification"
  },
  "reasoning": {
    "type": "string",
    "description": "Explanation of the changes made and why the questions were asked"
  },
  "ai_summary": {
    "type": "string",
    "description": "Required AI summary explaining what was done: for new configs - overview of structure, critical columns, and clarification needs; for refinements - list of important changes and further needs"
  }
}
```

## Implementation Notes

### Text Streaming Animation
- Base speed: ~10 words per second
- Pause duration: 0.2 seconds at periods (.), commas (,), semicolon (;), or newlines
- Creates natural reading rhythm

### WebSocket Progress Stages
- **Generating Config**: "Analyzing table structure", "Identifying data patterns", "Creating validation targets"
- **Refining Config**: "Processing refinement request", "Updating validation strategy", "Optimizing search groups"
- **Testing Config**: "Validating configuration", "Checking compatibility", "Finalizing structure"

### Session Management
- Single session tracks all interactions
- Each refinement creates new config version
- All chat history and previews remain visible
- Unified storage maintains complete conversation context

### Mobile Responsiveness
- Desktop-optimized but mobile-aware
- Chat bubbles stack vertically on narrow screens
- Progress bars and buttons scale appropriately
- Text input areas adapt to screen width