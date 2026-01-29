# tmux Cheat Sheet

Default prefix: `Ctrl+b` (press first, then the command key)

## Sessions
| Shortcut | Action |
|----------|--------|
| `tmux new -s name` | New session (shell) |
| `tmux ls` | List sessions (shell) |
| `tmux a -t name` | Attach to session (shell) |
| `d` | Detach from session |
| `$` | Rename session |
| `s` | List/switch sessions |

## Windows (tabs)
| Shortcut | Action |
|----------|--------|
| `c` | Create window |
| `n` | Next window c|
| `p` | Previous window |
| `0-9` | Go to window # |
| `,` | Rename window |
| `&` | Kill window |
| `w` | List windows |

## Panes (splits)
| Shortcut | Action |
|----------|--------|
| `%` | Split vertical |
| `"` | Split horizontal |
| `arrow` | Move between panes |
| `x` | Kill pane |
| `z` | Toggle pane zoom |
| `{` / `}` | Swap pane left/right |
| `Ctrl+arrow` | Resize pane |
| `Space` | Cycle layouts |
| `q` | Show pane numbers |

## Copy Mode
| Shortcut | Action |
|----------|--------|
| `[` | Enter copy mode |
| `q` | Exit copy mode |
| `Space` | Start selection (in copy mode) |
| `Enter` | Copy selection (in copy mode) |
| `]` | Paste buffer |

## Other
| Shortcut | Action |
|----------|--------|
| `?` | List all keybindings |
| `:` | Command prompt |
| `t` | Show clock |
