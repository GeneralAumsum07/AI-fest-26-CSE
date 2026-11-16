# UI refresh implementation plan

Spec: ../specs/2026-11-16-ui-refresh-design.md

1. Update wording expectations in tests/test_wording.py; confirm they fail for
   the existing first-person summaries and overly certain voice guidance.
2. Replace static/index.html and static/style.css with the professional layout
   and local typography. Keep current IDs and API boundaries intact.
3. Update static/app.js presentation and control feedback, and replace first-person
   copy in wording/templates.py and app.py. Keep model and risk logic unchanged.
4. Exercise the browser workflow with controlled report fixtures, including file
   selection, mobile layout, failure, progress, report, feedback and print isolation.
   Use the already measured synthetic real-model report as a UI fixture only.
5. Run the full Python suite, inspect screenshots, correct actual defects, and
   report the local preview and any remaining limitation. Preserve the unrelated
   pending slide-deck changes.
