# Abacus — calculator

**Role:** Quick arithmetic. Safe AST evaluator — no `eval()`, no names beyond math helpers.

**Status:** new (v1)

## Current
- `abacus` — TUI: expression line, result tape, ↑↓ history
- `abacus "expr"` — one-shot print result
- Ops: `+ - * / // % **` (also `^` → `**`), unary ±
- Fns: abs round min max sqrt sin cos tan log log10 log2 exp floor ceil
- Const: pi e tau
- Chrome: `╭─ ✦ Abacus ✦ calc ✦ ─╮` + Runes footer

## Next
- [ ] Ans / last-result variable
- [ ] Unit helpers (optional)

## Notes
- Rejects attribute access, comprehensions, and unknown names.
