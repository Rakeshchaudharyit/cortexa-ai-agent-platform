# Portfolio Launch 1 — Group 3

## Chat + Knowledge/Documents Production Polish

This milestone improves the two primary user workflows without changing backend behavior or API contracts.

### Chat
- Stronger product-oriented empty state and conversation entry experience.
- More refined Chat header and conversation navigation.
- Cleaner conversation sidebar, search, archived control, and active state.
- Reworked composer hierarchy with clearer General Agent / Document Knowledge modes.
- Improved source selection for Document Knowledge.
- Cleaner message width, spacing, loading state, streaming state, and feedback presentation.
- Citation cards now read as enterprise knowledge-source references rather than raw debug metadata.
- Existing editing, regeneration, feedback, memory, tools, streaming, and citations remain intact.

### Knowledge library
- Reframed the existing document lifecycle UI as a governed Knowledge Library.
- Added real summary metrics for active sources, folders, and active background jobs.
- Improved folder organization and empty states.
- Improved upload/version publishing experience while keeping background ingestion unchanged.
- Improved document rows, lifecycle/status hierarchy, tags, progress indicators, and action grouping.
- Improved grounded knowledge test area and citation/result presentation.
- Reworked version-history modal with clearer active-version state, comparisons, and lifecycle timeline.
- Existing upload, versioning, archive/restore, re-index, metadata, deletion, and RAG behavior is preserved.

### Validation
Changed TS/TSX files were syntax checked through the TypeScript transpiler. Full dependency-aware frontend validation should run in the local Docker environment.

### Portfolio screenshot candidates
1. Document Knowledge chat with a grounded answer and citations.
2. Knowledge Library with ready documents, lifecycle badges, folders, and tags.
3. Knowledge Library while a background indexing job is progressing.
4. Version History modal with active/superseded versions and lifecycle timeline.
