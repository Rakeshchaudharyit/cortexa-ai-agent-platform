# Long-Term Memory

Cortexa includes user-controlled long-term memory for durable preferences, project context and instructions that should persist across conversations.

## Principles

- memory is scoped to the owning user;
- users can review and manage stored items;
- conversation memory settings can inherit account defaults;
- bounded memory context may be injected into chat;
- memory activity is represented with safe metadata rather than hidden reasoning.

## User controls

The `/memories` experience supports reviewing, confirming, archiving and deleting memory items plus memory-related settings.

## Privacy

Memory retrieval and mutation require authenticated ownership checks. Admin visibility is controlled through protected administration routes and should be used only for legitimate operational purposes.

Long-term memory is not a substitute for document RAG: documents remain the authoritative grounded knowledge source, while memory is intended for concise user-specific context.
