# Design System Document

## 1. Overview & Creative North Star: "The Synthetic Architect"

This design system is built to bridge the gap between heavy industry and high-bandwidth intelligence. For an industrial intelligence platform, we move away from "standard SaaS blue" and generic cards. Our Creative North Star is **"The Synthetic Architect."**

The aesthetic is characterized by surgical precision, high-contrast editorial typography, and a "built" environment. We reject the template look by embracing intentional asymmetry and density. Elements shouldn't just sit on a page; they should feel like components of a complex, well-oiled machine. This is achieved through tonal depth rather than structural lines, creating a UI that feels like a head-up display for modern manufacturing.

---

## 2. Colors

The color palette is anchored by a high-visibility Amber, evoking industrial safety signals and glowing vacuum tubes, set against a deep, sophisticated "Carbon" background.

### Core Palette
- **Primary (`#ffc183`)**: Used for high-priority actions and brand accents.
- **Primary Container (`#ff9a00`)**: The core Amber signal. Use this for primary CTAs and active states.
- **Surface (`#131313`)**: The canvas. A deep, near-black that provides the foundation for high information density.
- **Tertiary (`#8bd7ff`)**: A cool "Oxygen Blue" used for data visualization and secondary technical indicators to balance the warmth of the Amber.

### The "No-Line" Rule
To maintain a premium, editorial feel, **1px solid borders are prohibited for sectioning.** Traditional boxes make a layout look like a template. Instead, define boundaries through background color shifts. A section should be distinguished by moving from `surface` to `surface_container_low`. If a container requires further nesting, use `surface_container_high`.

### Signature Textures & Glass
- **Glassmorphism:** For floating overlays (modals, dropdowns, or hovering tooltips), use a semi-transparent `surface_variant` with a 12px-20px backdrop blur. This allows the industrial data beneath to "ghost" through, maintaining context.
- **Micro-Gradients:** Avoid flat fills for major components. Primary CTAs should utilize a subtle linear gradient from `primary` to `primary_container` at a 135-degree angle to add a metallic, "machined" luster.

---

## 3. Typography

The system utilizes a dual-font strategy to balance industrial authority with technical readability.

- **Headlines (Manrope):** Chosen for its geometric precision. Use `display-lg` and `headline-lg` for editorial moments. High tracking (letter-spacing) should be avoided; keep it tight and structural.
- **Body & Labels (Inter):** A workhorse typeface for high-density data. `label-sm` and `label-md` are the backbone of the "Industrial Intelligence" look—use them for metadata and technical specs.

**Editorial Hierarchy:** Use extreme scale shifts. A `display-lg` headline should sit near `label-sm` metadata to create an authoritative, "monitored" atmosphere.

---

## 4. Elevation & Depth

In this system, depth is a function of light and material, not drop shadows.

### The Layering Principle (Tonal Nesting)
Depth is achieved by "stacking" the surface-container tiers.
1.  **Level 0 (Base):** `surface` (`#131313`)
2.  **Level 1 (Sub-section):** `surface_container_low` (`#1c1b1b`)
3.  **Level 2 (Cards/Modules):** `surface_container` (`#201f1f`)
4.  **Level 3 (Interactive/Active):** `surface_container_high` (`#2a2a2a`)

### Ambient Shadows
Shadows must be invisible until they are needed. Use a blur of 32px-64px with an opacity of 6% using the `on_surface` color. This creates a soft, ambient "lift" that mimics natural lighting in a controlled facility.

### The "Ghost Border" Fallback
If accessibility requirements demand a border (e.g., in high-glare environments), use a **Ghost Border**: `outline_variant` at 15% opacity. It should be felt, not seen.

---

## 5. Components

### Buttons
- **Primary:** Gradient fill (`primary` to `primary_container`). Text color: `on_primary_fixed` (`#2c1600`). Use `DEFAULT` (0.25rem) or `full` roundedness for a pill-shaped "Control" feel.
- **Secondary:** Transparent fill with a `Ghost Border`. Text color: `primary`.
- **Tertiary:** No background, no border. Use for low-emphasis technical actions.

### Technical Chips
Industrial status is conveyed through "Indicator Chips." These use `label-sm` caps and a small leading dot (4px). For "Active" states, use `primary_container`. For "Standby," use `surface_variant`.

### Input Fields
Inputs should feel like a digital readout. Use `surface_container_highest` for the field background with a bottom-only stroke (2px) of `outline_variant` that transitions to `primary` on focus. No full-box strokes.

### Cards & Data Modules
**Forbidden:** Divider lines. 
**Required:** Vertical white space from the Spacing Scale (e.g., `8` or `10`). To separate content within a card, use a subtle background shift to `surface_container_lowest` for the footer or header area.

### Industrial "Status" Tooltips
Tooltips should utilize the Glassmorphism rule. They are technical readouts, not just hints. Use `body-sm` in `on_surface` color with high-contrast `label-md` for headers.

---

## 6. Do's and Don'ts

### Do
*   **Do** use `primary_container` (Amber) sparingly. It is a "signal" color. If everything is Amber, nothing is important.
*   **Do** embrace high information density. Use the `0.5`, `1`, and `2` spacing tokens to group technical data tightly.
*   **Do** use asymmetrical layouts. Align a headline to the far left while technical data sits in a narrow column on the far right.
*   **Do** use `Manrope` for all numerical readouts in headers to ensure a modern, precise look.

### Don't
*   **Don't** use standard "Material Design" shadows. They feel too consumer-grade and "soft" for an industrial tool.
*   **Don't** use dividers (`<hr>`). Use a 1.1rem (`5`) or 1.3rem (`6`) gap instead.
*   **Don't** use bright white text on black. Use `on_surface` (`#e5e2e1`) to reduce eye strain during long shifts.
*   **Don't** use large corner radii. Stick to `DEFAULT` (0.25rem) or `sm` (0.125rem) to maintain a precise, "machined" aesthetic.