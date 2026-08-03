# Goblin — mail

**Role:** Mail spirit. aerc IMAP → local text mail; interactive TUI; instant push (IDLE) + timer safety net; squeaks on new mail.

**Status:** stable

## Current
- `goblin` TUI: boxes unread/read/trash, j/k move, enter open (marks read), s sync, m read, t trash, 1/2/3 box
- `goblin list|show|sync|bundle|move|sound`
- `~/.cache/goblin/mail/{unread,read,trash}/*.txt`; state in `~/.cache/goblin/state.json`
- systemd: `goblin-idle.service` (IDLE push) + `goblin-sync.{service,timer}` (5-min safety net)
- Notify sound: `~/.config/goblin/notify.{mp3,wav,ogg,m4a}`; `goblin sound --set`
- Runs on shared `tui_*` layer

## Next
- [ ] Compose/send from TUI
- [ ] Search across boxes (fzf)
- [ ] Attachments (open/save from reader)
- [ ] Mailbox aliases / multiple accounts

## Notes
- Secrets: mail URLs with passwords never committed; aerc config local.
