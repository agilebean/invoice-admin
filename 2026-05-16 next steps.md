# Next steps — 2026-05-16

After shared-migration: llm/litellm → LLMProvider wired to agentkit.

## Issues found during smoke testing

1. **`invoice googleads` subcommands broken** — CLI was on an earlier state before refactoring. Subcommands need update to match current implementation.

2. **`save-commission-pdf` → rename to `save`** — keep consistent with other subcommands.

3. **`invoice googleads send --test-run` wrong recipient** — currently sends to `chaehan.so@virtualfriend.chat` instead of the real invoice email. Should use the configured billing email from the handler config.
