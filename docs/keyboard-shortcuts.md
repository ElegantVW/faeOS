# Grove keyboard shortcuts

Grove owns the canonical vocabulary and default bindings for actions shared
across its apps. The versioned source is
[`config/keyboard-shortcuts.json`](../config/keyboard-shortcuts.json).

## Shared actions, v1

| Action | Default | Meaning |
|--------|---------|---------|
| `cycle_next` | Tab | Move forward in the active app's ordered navigation context. |
| `cycle_previous` | Shift+Tab | Move backward in that same context. |

The context remains app-local: a view carousel, page sequence, or mode cycle
can each use the shared action without sharing their contents. Use the same
combination for the same conceptual action; do not force Tab onto unrelated
actions.

## Boundaries

- System-level **Alt+Tab** switches applications and is not in-app cycling.
- Shell line-editor widgets (ZLE, including `summon` and `print -z`) belong to
  the shell context, not an application's TUI.
- An app may define a context-specific exception only when the shared action
  is unavailable or conflicts with a stronger interaction. Document the
  exception beside the app's help and test it.

## Generated Rust adapters

`config/keyboard-shortcuts.json` is the source of truth. Run
`python3 tools/sync-keyboard-shortcuts.py` from the Grove checkout to refresh
the generated `src/grove_keys.rs` adapters in Codex, Pixie, Siren, Scroll, and
Wisp.
`python3 tools/sync-keyboard-shortcuts.py --check` detects drift. The
generator validates the catalog version before producing adapters.

The first pilot keeps the existing Tab / Shift+Tab behavior in all five
apps. The adapters normalize terminal differences such as `BackTab` versus
`Tab` with a Shift modifier, and reject Ctrl/Alt/Super-modified variants.

## Rollout

1. Pilot this contract in Pixie (Rune cycle), Siren (view cycle), Scroll
   (page cycle), Codex (window cycle), and Wisp (face cycle).
2. Update the app help, Scroll curriculum, and tests in the same change as any
   binding revision.
3. Extend the catalog and adapters to other shared actions only after their
   semantics and context are agreed.
