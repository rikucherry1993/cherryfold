# comprehensive cherryfold demo — split + live-follow + interactions (in tmux).
# render: vhs assets/demo.tape   (needs /tmp/cf.tmux.conf with a sanitized prompt)
Output assets/demo.gif

Set Shell "zsh"
Set FontSize 13
Set Width 1500
Set Height 760
Set Padding 16
Set Theme "Catppuccin Mocha"

Hide
Type "mkdir -p /tmp/cflive && head -n 6 assets/demo.jsonl > /tmp/cflive/demo.jsonl"
Enter
Type "tmux -f /tmp/cf.tmux.conf new-session"
Enter
Sleep 1.5s
Show

Type "cherryfold follow /tmp/cflive/demo.jsonl"
Enter
Sleep 4.5s

# append step 2 (the follow pane tails it in) and move focus into the viewer
Hide
Type "tail -n +7 assets/demo.jsonl >> /tmp/cflive/demo.jsonl && tmux select-pane -R && clear"
Enter
Show
Sleep 3s

# interact with the viewer pane: unfold, search, settings/theme
Type "e"
Sleep 2.5s
Type "/"
Sleep 400ms
Type "limiter"
Sleep 500ms
Enter
Sleep 1.5s
Type "n"
Sleep 1.5s
Escape
Sleep 800ms
Type "s"
Sleep 1.2s
Down@350ms 4
Sleep 700ms
Enter
Sleep 1.5s
Escape
Sleep 1.2s

Hide
Type "tmux kill-server"
Enter
Show
