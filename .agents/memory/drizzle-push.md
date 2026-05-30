---
name: Drizzle Kit Push Interactive Block
description: drizzle-kit push is interactive and will hang start.sh if the schema has data-loss statements.
---

**Rule:** Never run `drizzle-kit push` inside `start.sh` or any startup script that must be non-interactive.

**Why:** If the schema diff involves dropping tables or columns with existing data, drizzle-kit prompts the user and blocks indefinitely — killing the workflow startup.

**How to apply:** Run migrations separately (manually or in a dedicated CI step). `start.sh` should only install deps and start the dev server.
