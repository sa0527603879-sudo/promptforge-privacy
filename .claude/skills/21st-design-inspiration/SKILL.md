---
name: 21st-design-inspiration
description: >
  Pull design inspiration from 21st.dev (12,000+ crafted React/Tailwind components by
  design engineers) BEFORE designing or redesigning any UI. Use whenever the user asks to
  design, redesign, beautify, or upgrade the look of anything — a page, section, hero,
  pricing table, card, form, navbar, footer, button, landing page — or says things like
  "make it prettier", "higher level", "premium look", "תעצב", "תשדרג את העיצוב",
  "משהו יותר יפה", "ברמה גבוהה", "תיקח השראה מ-21st". Also use when starting any new
  page or component from scratch.
---

# 21st.dev Design Inspiration

21st.dev is a curated library of 12,000+ production-grade React + Tailwind components
built by professional design engineers. We use it as our design reference bar: before
building or restyling any UI, look at how the best versions of that component are done
there, extract the *visual language*, and adapt it to this project's stack.

## Why this workflow exists

The user (Shlomi) explicitly asked: every time we design something that should look
high-end, take inspiration from 21st.dev first. Never design "from memory" when the
task is visual polish — always ground the design in 2-4 real references from 21st.dev.

## How to access 21st.dev

Direct fetches to 21st.dev are **blocked by the network egress proxy** in remote
sessions (`WebFetch` returns EGRESS_BLOCKED). Use the Firecrawl MCP tools instead —
they browse from Firecrawl's own servers and work:

```
mcp__Firecrawl__firecrawl_search
  query: "<component type> <style keywords>"
  includeDomains: ["21st.dev"]
  limit: 6-10
```

(Load it via ToolSearch first if not loaded: `select:mcp__Firecrawl__firecrawl_search`.)

Search result descriptions often contain the full component source code inline.
Useful URL patterns on the site:

- Category listings: `https://21st.dev/community/components/s/<category>`
  (e.g. `s/hero`, `s/pricing-section`, `s/testimonials`, `s/navbar`, `s/footer`,
  `s/card`, `s/button`, `s/form`, `s/features`, `s/faq`, `s/cta`)
- Individual components: `https://21st.dev/@<author>/components/<slug>` — these pages
  include the import snippet and often full TSX source.

If Firecrawl is unavailable in the local (non-remote) environment, try `WebFetch`
directly — it may work outside the proxy. If both fail, fall back to describing the
established 21st.dev-style patterns from the checklist below.

## The workflow

1. **Identify the component type** being designed (hero, pricing, nav, card, full
   landing page → search 2-3 section types separately).
2. **Search 21st.dev** with 1-2 Firecrawl queries. Pick 2-4 strong references. Prefer
   components whose code appears in the results so you can read real spacing/type/color
   values, not just marketing copy.
3. **Extract the visual language**, not the code:
   - Layout & composition (asymmetry, grid, whitespace rhythm, max-widths)
   - Typography scale (hero display sizes, tracking, weight contrast, muted subtitles)
   - Color strategy (near-black/near-white surfaces, one saturated accent, gradients,
     glow/blur effects, subtle borders like `1px solid rgb(255 255 255 / 0.1)`)
   - Depth cues (soft large-radius shadows, glassmorphism, layered cards)
   - Micro-details (badges/pills above headlines, icon treatment, hover states,
     entrance animations, dot/grid background patterns)
4. **Adapt to the project's actual stack.** This repo (and many of Shlomi's projects)
   is plain HTML/CSS, RTL Hebrew — do NOT paste React/Tailwind code verbatim.
   Translate Tailwind utilities into equivalent CSS. Preserve RTL correctness
   (`dir="rtl"`, logical properties like `padding-inline-start`, `text-align: start`)
   and the existing light/dark scheme (`prefers-color-scheme`).
5. **Tell the user which references you used** — name the component/author or category
   page so the design decisions are traceable.

## Quality bar checklist (distilled from 21st.dev top components)

- One accent color used sparingly; everything else near-neutral.
- Generous whitespace: sections breathe (padding-block 80-120px on desktop).
- Type contrast: big bold display headline vs. small muted supporting text.
- Border radius consistent across the page (pick one: e.g. 12px cards / 8px controls).
- Subtle 1px borders + soft shadows instead of hard outlines.
- A small "badge"/eyebrow element above major headlines.
- Hover/focus transitions of 150-250ms on interactive elements.
- Dark mode is a first-class variant, not an afterthought.
