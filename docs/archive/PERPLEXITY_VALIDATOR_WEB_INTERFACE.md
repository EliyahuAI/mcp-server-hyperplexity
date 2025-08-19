# Perplexity Validator Web Interface

## Overview
A complete JavaScript web interface for the Perplexity Validator API, designed for easy integration into Squarespace or any website.

## Features

### 1. Email Validation
- Two-step email validation process
- Automatic validation check on page load (using localStorage)
- Clean UI flow: Enter email → Receive code → Verify → Access validator

### 2. File Upload
- Drag-and-drop support for both Excel/CSV and JSON config files
- Visual feedback during drag operations
- File type validation
- File size display

### 3. Processing Modes

#### Preview Mode
- Test with 1-5 rows (adjustable slider)
- Sync/Async toggle for API Gateway timeout handling
- Real-time cost and time estimates
- Markdown table preview with confidence levels

#### Full Mode
- Process entire table or set max rows limit
- Batch size fixed at 5 for optimal performance
- Automatic async processing with progress tracking
- Email delivery of results

### 4. Results Display
- Clean markdown table rendering
- Confidence level badges (High/Medium/Low)
- Cost breakdown showing:
  - Estimated cost per row
  - Total processing time
  - Total rows in file
- Download button for completed validations

## Installation

### For Squarespace
1. Go to your Squarespace site editor
2. Add a "Code Block" to your page
3. Copy the entire contents of `perplexity_validator_interface.html`
4. Paste into the code block
5. Save and publish

### For Other Websites
Simply include the HTML file in your website:
```html
<iframe src="perplexity_validator_interface.html" width="100%" height="1200px" frameborder="0"></iframe>
```

Or copy the HTML content directly into your page.

## API Configuration
The interface is pre-configured to use:
- Base URL: `https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod`
- All required endpoints for email validation, file upload, and processing

## Styling
The interface follows the Eliyahu.AI brand guidelines:
- Primary color: Green (#4CAF50)
- Clean, professional card-based layout
- Responsive design for mobile devices
- Consistent with the reference tool design

## Security Features
- Email validation required before access
- Secure file handling with type validation
- No external dependencies (pure vanilla JavaScript)
- CORS-compliant API calls

## User Flow
1. **Email Validation** → User enters email and receives code
2. **File Upload** → Drag or select Excel and Config files
3. **Config Validation** → Optional validation of configuration
4. **Choose Mode** → Preview (1-5 rows) or Full processing
5. **Process** → View results or track async progress
6. **Results** → View markdown preview, estimates, and download

## Browser Compatibility
- Chrome, Firefox, Safari, Edge (latest versions)
- Mobile responsive
- No polyfills required (modern JavaScript)

## Customization
CSS variables make it easy to customize:
```css
:root {
    --primary-color: #4CAF50;  /* Change primary color */
    --font-family: 'Segoe UI'; /* Change font */
    --border-radius: 8px;      /* Adjust corners */
}
```

## Known Limitations
- File upload limited by browser memory (typically ~100MB)
- Async polling requires stable internet connection
- Email validation codes expire after 10 minutes

## Support
For issues or questions, visit [Eliyahu.AI](https://eliyahu.ai) 