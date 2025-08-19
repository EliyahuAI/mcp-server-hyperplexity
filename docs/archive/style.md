# Eliyahu.AI Style Guide

## Brand Colors

### Primary Colors
- **Primary Green**: `#00FF00` (Bright Lime Green) - Used for accent highlights, underlines, and call-to-action elements
- **Background**: `#FFFFFF` (Pure White) - Clean, professional background
- **Text Primary**: `#000000` (Black) - Main heading and body text

### Secondary Colors
- **Text Secondary**: `#666666` (Medium Gray) - Subtext and descriptions
- **Border/Divider**: `#E5E5E5` (Light Gray) - Subtle borders and separators

## Typography

### Headings
- **Font Family**: Sans-serif (likely Helvetica, Arial, or similar)
- **Main Heading**: Large, bold, black text
- **Weight**: Bold (700+)
- **Style**: Clean, modern, minimal

### Body Text
- **Font Family**: Sans-serif
- **Color**: Medium gray (#666666)
- **Weight**: Regular (400)
- **Line Height**: Generous spacing for readability

## Layout & Spacing

### Structure
- **Max Width**: Centered content with generous margins
- **Padding**: Ample white space around content blocks
- **Alignment**: Center-aligned content with balanced composition

### Navigation
- **Style**: Minimal, clean navigation bar
- **Color**: Black text on white background
- **Hover**: Subtle interaction states

## Interactive Elements

### Buttons
- **Primary Button**: 
  - Background: Black (`#000000`)
  - Text: White
  - Border Radius: Subtle rounding
  - Padding: Generous internal spacing
  - Hover: Slight opacity or color change

### Accent Elements
- **Highlight**: Bright green underline (`#00FF00`)
- **Usage**: Under key phrases like "Generative AI"

## Design Principles

### Minimalism
- Clean, uncluttered design
- Generous white space
- Focus on essential content

### Professional
- Corporate-friendly color scheme
- Readable typography
- Clear hierarchy

### Modern
- Contemporary sans-serif fonts
- Subtle animations and interactions
- Responsive design approach

## CSS Variables (Implementation)

```css
:root {
  /* Colors */
  --primary-green: #00FF00;
  --primary-black: #000000;
  --primary-white: #FFFFFF;
  --text-secondary: #666666;
  --border-gray: #E5E5E5;
  
  /* Typography */
  --font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-weight-normal: 400;
  --font-weight-bold: 700;
  
  /* Spacing */
  --spacing-xs: 8px;
  --spacing-sm: 16px;
  --spacing-md: 24px;
  --spacing-lg: 32px;
  --spacing-xl: 48px;
  --spacing-xxl: 64px;
  
  /* Border Radius */
  --border-radius: 4px;
  --border-radius-lg: 8px;
}
```

## Email Design Application

### For Validation Emails
- Use white background with black text
- Green accents for highlights and call-to-action elements
- Clean, minimal layout with generous spacing
- Professional typography hierarchy
- Interactive elements (checkboxes, buttons) in brand colors

### Warning/Notice Boxes
- Background: Light yellow/cream (`#FFF8DC`)
- Border: Subtle gray with green left accent
- Text: Dark gray for readability
- Icons: Green accent color

### Code Display
- Background: Light gray (`#F8F9FA`)
- Border: Green accent (`#00FF00`)
- Font: Monospace for code readability
- High contrast for accessibility 