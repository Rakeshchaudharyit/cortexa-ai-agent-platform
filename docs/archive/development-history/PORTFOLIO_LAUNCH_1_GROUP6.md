# Portfolio Launch 1 — Group 6

## Responsive, Accessibility & Final UI QA

This final Portfolio Launch 1 pass focuses on cross-product usability rather than new features.

### Responsive safeguards

- Removed page-level horizontal overflow risk from shared shells.
- Kept wide admin tables locally scrollable with a consistent thin scrollbar.
- Made home-page and Knowledge Library KPI groups stack safely on narrow screens.
- Added a mobile conversation drawer so Chat remains fully usable on phone/tablet widths.
- Reduced mobile Chat header pressure by hiding secondary navigation actions below `sm`.
- Constrained mobile admin navigation to the viewport and added dialog semantics.

### Accessibility

- Added a global Skip to main content link and main-content targets on primary application routes.
- Strengthened focus-visible behavior across links, buttons and form controls.
- Added reduced-motion support for users who request it.
- Added polite live-region feedback to document/job success states and alert semantics to errors.
- Added accessible labeling to the document version-history dialog.
- Preserved keyboard-accessible conversation items and named icon actions.

### Product-language cleanup

- Removed the remaining visible Phase 9 wording.
- Replaced the homepage portfolio-build status with product-facing language.
- Reframed built-in agent-tool wording as general AI tool capabilities.
- Removed multi-agent orchestration from the promoted capabilities summary and replaced it with stable RAG evaluation and durable background-processing capabilities.

### Browser QA targets

Validate these widths before public launch:

- 1440px desktop
- 1280px laptop
- 768px tablet
- ~390px mobile

Primary screenshot routes:

1. `/admin`
2. `/admin/analytics`
3. `/chat`
4. `/#documents`
5. `/admin/evaluations`
6. `/admin/feedback`
7. `/admin/jobs`

### Out of scope

This pass does not change backend APIs, RAG behavior, queue semantics, database schema, evaluation scoring, feedback workflows, or knowledge lifecycle behavior.
