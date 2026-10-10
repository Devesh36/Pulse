# Product history

For every task that changes Pulse, update the public history in
`apps/web/src/lib/product-history.ts` in the same patch. Record the UTC date, a
short title, and the concrete effect on the product. Group the entry under the
appropriate phase; do not invent a new numbered phase for a small change.

Backfill the preceding entry's exact commit SHA when it is available. The entry
being authored can omit `commit` and will display “This update”; never invent a
SHA or try to embed a commit's own hash in its contents. Include separate entries
for subsequent commits, including merges, explaining when they only integrate
existing work. Preserve earlier entries and distinguish superseded designs from
the current product.

Summarize product changes from chats; do not publish raw conversations, private
information, credentials, or unverified capabilities. A no-change discussion
needs no shipped-work entry. Read `docs/product-history.md` and follow the
existing build/validation instructions in `CONTRIBUTING.md` and nested AGENTS files.
