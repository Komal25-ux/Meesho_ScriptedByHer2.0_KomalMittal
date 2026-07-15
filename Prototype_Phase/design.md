---
version: "alpha"
name: "Denim and Industrial Craft"
description: "Denim style landing, jeans texture background, gold stitching, industrial craft, textile aesthetic, rugged design. Ideal for landing pages, modern websites. AI-ready template."
colors:
  primary: "#9F2089"
  secondary: "#FFFFFF"
  tertiary: "#FC8B16"
  neutral: "#1E1E24"
  surface: "#F7F7FA"
  accent: "#F43397"
typography:
  h1:
    fontFamily: Roboto Slab
    fontSize: 2.5rem
    fontWeight: 700
  body-md:
    fontFamily: Roboto Slab
    fontSize: 1rem
    fontWeight: 400
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.neutral}"
    padding: 12px
---

## Overview

Denim style landing, jeans texture background, gold stitching, industrial craft, textile aesthetic, rugged design. Ideal for landing pages, modern websites. AI-ready template. Denim entered digital design the same way it entered culture — through labor. The indigo wash, the visible selvedge, the copper rivet detail. These weren't decorative choices. They were functional signals lifted from a century of workwear heritage. Levi's understood this early: their digital presence leans on raw texture photography, tight crops on warp and weft, type that feels stamped rather than set. Carhartt WIP took it further — bridging the gap between factory floor and streetwear with interfaces that feel worn-in, not polished.

What makes denim textures work on screen is their inherent honesty. A twill weave pattern communicates something no gradient ever could: that this thing was built to last. The industrial craft aesthetic — exposed stitching, canvas overlays, aged metal hardware — translates into UI elements that reject slickness in favor of substance. It's anti-corporate by nature.

The tension is what makes it interesting. Pairing raw textile imagery with futuristic typography or tech-forward layouts creates a friction that feels contemporary. Heritage meeting innovation. The hand-touched meeting the machine-precise. That's where the energy lives.

- Density: 5/10 — Balanced
- Variance: 4/10 — Moderate
- Motion: 4/10 — Subtle

- **Style:** Tactile, Durable, Textured
- **Keywords:** denim, fabric, jeans, texture, stitch, craft, industrial, copper, rugged
- **Era:** Heritage Craft
- **Light/Dark:** ✗ No / ✓ Full

## Colors

- **Background** (#9F2089) — Meesho Jamuni/Purple background surface
- **Text** (#FFFFFF) — Primary text color
- **Accent** (#FC8B16) — Meesho Aam/Mango accent, CTAs and interactive elements
- **Dark Wash** (#1E1E24) — Deep contrast/dark neutral surface
- **Thread Gold** (#F43397) — Meesho Pink accent, decorative highlights
- **Leather Brown** (#F7F7FA) — Light background surface
- **Rivet Copper** (#42BC9E) — Success/Teal accent, decorative detail


## Typography

- **Display / Hero:** Roboto Slab — Weight 700, tight tracking, used for headline impact
- **Body:** Roboto Slab — Weight 400, 16px/1.6 line-height, max 72ch per line
- **UI Labels / Captions:** Roboto Slab — 0.875rem, weight 500, slight letter-spacing
- **Monospace:** JetBrains Mono — Used for code, metadata, and technical values

Scale:
- Hero: clamp(2.5rem, 5vw, 4rem)
- H1: 2.25rem
- H2: 1.5rem
- Body: 1rem / 1.6
- Small: 0.875rem


## Layout

- **Grid:** CSS Grid primary. Max-width containment: 1280px centered with 1.5rem side padding.
- **Spacing rhythm:** Balanced. Base unit: 0.5rem (8px).
- **Section vertical gaps:** clamp(4rem, 8vw, 8rem).
- **Hero layout:** Split-screen (text left, visual right).
- **Feature sections:** Zig-zag alternating text+image rows. No 3-equal-columns.
- **Mobile collapse:** All multi-column layouts collapse below 768px. No horizontal overflow.
- **z-index contract:** base (0) / sticky-nav (100) / overlay (200) / modal (300) / toast (500).


## Elevation & Depth

Realistic denim fabric background, embroidered text, patch-style diagrams, copper rivets, heavy cotton canvas weave.

- **Physics:** Ease-out curves, 200-300ms duration. Smooth and predictable.
- **Entry animations:** Fade + translate-Y (16px → 0) over 420ms ease-out. Staggered cascades for lists: 80ms between items.
- **Hover states:** Subtle color shift + shadow adjustment over 200ms.
- **Page transitions:** Fade only (200ms).
- **Performance:** Only transform and opacity animated. No layout-triggering properties.


## Shapes

Base corner radius: 8px. See rounded tokens in front matter for the full scale.


## Components

- **Primary Button:** Subtly rounded (0.5rem) shape. Accent color fill. Hover: 8% darken + subtle lift shadow. Active: -1px translate tactile press. Font weight 600. No outer glows.
- **Secondary / Ghost Button:** Outline variant. 1.5px border in muted color. Text in primary color. Hover: subtle background fill.
- **Cards:** Subtly rounded (0.5rem) corners. Surface background. Subtle shadow (0 2px 12px rgba(0,0,0,0.06)). 1px border stroke.
- **Inputs:** Label above input. 1px border stroke. Focus ring: 2px accent color offset 2px. Error text below in semantic red. No floating labels.
- **Navigation:** Primary surface background. Active item: accent color indicator. Font weight 500 when active.
- **Skeletons:** Shimmer animation matching component dimensions. No circular spinners.
- **Empty States:** Icon-based composition with descriptive text and action button.


## Do's and Don'ts

- No emojis in UI — use icon system only (Lucide, Heroicons)
- No pure black (#000000) — use off-black or charcoal variants
- No oversaturated accent colors (saturation cap: 80%)
- No 3-column equal-width feature layouts — use zig-zag or asymmetric grid
- No `h-screen` — use `min-h-[100dvh]`
- No AI copywriting clichés: "Elevate", "Seamless", "Unleash", "Next-Gen"
- No broken external image links — use picsum.photos or inline SVG
- No generic lorem ipsum in demos

- Do Denim texture background
- Do Dashed borders (stitching)
- Do Gold/Yellow accent colors (thread)
- Do Slab serif typography
- Do Patch-like container elements


## Use Case

Landing pages, Modern websites

<!-- Source: https://designmd.app/library/denim-and-industrial-craft · designmd.app -->
