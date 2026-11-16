# Exposure UI refresh

The requested change is a more professional application interface and neutral
product wording, including a change of fonts. The existing audit pipeline,
allowlists, risk rules, API contracts and offline operation stay in place.

## Approach

Refresh the existing static HTML, CSS and JavaScript. A new frontend framework
would add a build/runtime dependency without improving this small local app.
A colors-only pass would leave the long onboarding page and weak form hierarchy
unresolved. The chosen implementation is a complete visual pass over the upload,
progress, report, error and feedback views, using the current application stack.

## Visual direction

- Canvas #F5F7F9, surface #FFFFFF, ink #192521, secondary #65736D,
  action #176B55, and line #DFE5E1. Red and amber indicate risk or caveats.
- Bahnschrift headings, locally bundled Source Sans 3 body text. No font CDN.
- Left-aligned content, generous whitespace, a compact application header.
- Desktop: introduction and data scope on the left, a focused upload panel on
  the right. Mobile: a single column with the primary workflow kept prominent.
- Reports: clear risk cards and a separate recommended-actions column. Preserve
  accessible headings, native controls, keyboard focus and print-only safety card.

```text
Exposure                              Runs on this device
---------------------------------------------------------
See what your posts reveal.           Start a privacy audit
Short product explanation             [Choose export ZIP]
Instagram / YouTube                   [Optional voice match]
Included / excluded content           [Run privacy audit]
YouTube import limitations
```

## Copy and validation

Describe the application rather than a person: "Included in the audit",
"Excluded from the audit", "No urgent exposure identified", "Add a finding".
Keep the YouTube synthetic-verification and real-Takeout limitations accurate.
Never add guarantees of safety, numerical risk scores, or unmeasured claims.

Verify file selection, progress, errors, reports, feedback, exclusion disclosures,
payload display and printing at desktop and mobile widths. Run the existing
Python suite after wording changes. Do not commit or push without another request.
