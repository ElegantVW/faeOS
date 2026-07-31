# pixie.zsh — shell integration for pixie-kit
# Source from ~/.zshrc:  source ~/pixie-kit/shell/pixie.zsh
# Or after install:      source ~/.config/pixie/pixie.zsh
#
# Does NOT include personal plugins (autosuggestions), grok paths, or secrets.

# ── PATH ──────────────────────────────────────────────────────
export PATH="$HOME/bin:$HOME/.local/bin:$PATH"

# ── Palette / colors ──────────────────────────────────────────
[[ -r "$HOME/.config/palette.env" ]] && source "$HOME/.config/palette.env"
unset NO_COLOR
export FORCE_COLOR=1
export CLICOLOR=1
export LS_COLORS="${LS_COLORS:-di=38;2;232;121;160:ln=38;2;240;180;200:ex=38;2;61;214;140}"
export GREP_COLORS="${GREP_COLORS:-ms=1;38;2;232;121;160:mc=1;38;2;232;121;160}"
export FZF_DEFAULT_OPTS="${FZF_DEFAULT_OPTS:---color=fg:#c0c0c8,bg:#1a0a12,hl:#e879a0,fg+:#ffebf2,bg+:#2a1520,hl+:#ff2d55,info:#9d5c75,prompt:#e879a0,pointer:#ffb020,marker:#3dd68c,spinner:#c44d7a,header:#c44d7a}"

alias ll="${aliases[ll]:-ls -lah --color=auto}"
alias ls="${aliases[ls]:-ls --color=auto}"
alias grep="${aliases[grep]:-grep --color=auto}"
alias myhelp='cmds'
# optional: alias mail='aerc'  # if you use aerc

# ── Starship (prompt box) ─────────────────────────────────────
if command -v starship >/dev/null 2>&1; then
  eval "$(starship init zsh)"
fi

# ── Music (mpv IPC) ───────────────────────────────────────────
_MPV_SOCK="${XDG_RUNTIME_DIR:-/tmp}/mpv-music.sock"
_play_label() {
  local base="$1" artist song
  if [[ "$base" =~ '([0-9]{2})[[:space:]]+(.+)[[:space:]]+-[[:space:]]+(.+)$' ]]; then
    artist="${match[2]}"
    song="${match[3]}"
  elif [[ "$base" == *" - "* ]]; then
    artist="${base%-*}"
    song="${base##*- }"
    artist="${artist%"${artist##*[![:space:]]}"}"
  else
    artist="Unknown"
    song="$base"
  fi
  print -r -- "Now playing ${artist} - ${song}"
}
_mpv_cmd() {
  [[ -S $_MPV_SOCK ]] || { echo "Nothing playing. Run: play"; return 1; }
  MPV_SOCK="$_MPV_SOCK" MPV_JSON="$1" python3 - <<'PY'
import json, os, socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
try:
    s.settimeout(2)
    s.connect(os.environ["MPV_SOCK"])
    s.sendall((os.environ["MPV_JSON"].strip() + "\n").encode())
    data = b""
    while True:
        chunk = s.recv(4096)
        if not chunk:
            break
        data += chunk
        if b"\n" in data:
            break
    sys.stdout.write(data.decode(errors="replace"))
except Exception as e:
    print(f"mpv IPC failed: {e}", file=sys.stderr)
    sys.exit(1)
finally:
    s.close()
PY
}
_now_playing() {
  local raw path base meta_a meta_t
  raw=$(_mpv_cmd '{ "command": ["get_property", "filename/no-ext"] }') || return 1
  base=$(print -r -- "$raw" | python3 -c 'import sys,json
try:
 d=json.load(sys.stdin); print(d.get("data") or "")
except Exception: print("")')
  meta_a=$(_mpv_cmd '{ "command": ["get_property", "metadata/by-key/artist"] }' 2>/dev/null | python3 -c 'import sys,json
try:
 d=json.load(sys.stdin); v=d.get("data"); print(v if isinstance(v,str) else "")
except Exception: print("")')
  meta_t=$(_mpv_cmd '{ "command": ["get_property", "metadata/by-key/title"] }' 2>/dev/null | python3 -c 'import sys,json
try:
 d=json.load(sys.stdin); v=d.get("data"); print(v if isinstance(v,str) else "")
except Exception: print("")')
  if [[ -n $meta_a && -n $meta_t ]]; then
    print -r -- "Now playing ${meta_a} - ${meta_t}"
  else
    _play_label "$base"
  fi
}
play() {
  local files=("$HOME"/Music/*.(wav|mp3|flac|ogg|m4a)(N))
  (( ${#files} )) || { echo "No audio files in ~/Music"; return 1; }
  [[ -S $_MPV_SOCK ]] && _mpv_cmd '{ "command": ["quit"] }' >/dev/null 2>&1
  pkill -x mpv 2>/dev/null
  rm -f "$_MPV_SOCK"
  mpv --no-video --shuffle \
    --really-quiet \
    --audio-display=no \
    --cover-art-auto=no \
    --input-ipc-server="$_MPV_SOCK" \
    -- "${files[@]}" >/dev/null 2>&1 &!
}
next() {
  _mpv_cmd '{ "command": ["playlist-next"] }' >/dev/null 2>&1 || return 1
  sleep 0.15
  _TICK_LAST_SONG=$(_tick_song_id 2>/dev/null)
  _TICK_LAST_TS=$EPOCHSECONDS
  clear
}
prev() {
  _mpv_cmd '{ "command": ["playlist-prev"] }' >/dev/null 2>&1 || return 1
  sleep 0.15
  _TICK_LAST_SONG=$(_tick_song_id 2>/dev/null)
  _TICK_LAST_TS=$EPOCHSECONDS
  clear
}
now() { _now_playing; }
alias stop='pkill -x mpv; rm -f "${XDG_RUNTIME_DIR:-/tmp}/mpv-music.sock" 2>/dev/null'
alias play-next=next
alias play-prev=prev
alias play-now=now

volume() {
  if ! command -v wpctl >/dev/null 2>&1; then
    echo "volume needs wpctl (PipeWire)"
    return 1
  fi
  if [[ -z "$1" ]]; then
    wpctl get-volume @DEFAULT_AUDIO_SINK@
    return
  fi
  if [[ ! "$1" =~ '^[0-9]+$' ]] || (( $1 > 150 )); then
    echo "Usage: volume <0-150>"
    return 1
  fi
  wpctl set-volume @DEFAULT_AUDIO_SINK@ "${1}%"
  wpctl get-volume @DEFAULT_AUDIO_SINK@
}

# optional yt helper (needs yt-dlp + fzf + mpv)
yt() {
  command -v yt-dlp >/dev/null || { echo "need yt-dlp"; return 1; }
  command -v fzf >/dev/null || { echo "need fzf"; return 1; }
  yt-dlp --get-id --get-title "ytsearch10:$*" 2>/dev/null | paste - - | fzf | awk '{print $NF}' | xargs -I{} mpv "ytdl://{}"
}

# ── Tick + grace + up ─────────────────────────────────────────
_TICK_CFG="${XDG_CONFIG_HOME:-$HOME/.config}/pixie/tick"
_TICK_LAST_SONG=""
_TICK_LAST_TS=0
_TICK_POLL=2

_tick_enabled() {
  [[ -f "$_TICK_CFG" ]] || return 0
  ! grep -qiE '^(off|0|false|no)\b' "$_TICK_CFG" 2>/dev/null
}
_tick_seconds() {
  local s=10 line
  if [[ -f "$_TICK_CFG" ]]; then
    line=$(head -1 "$_TICK_CFG" 2>/dev/null)
    if [[ "$line" =~ '^(on|1)?[[:space:]]*([0-9]+)$' ]]; then
      s="${match[2]}"
    elif [[ "$line" =~ '^([0-9]+)$' ]]; then
      s="${match[1]}"
    fi
  fi
  (( s >= 2 && s <= 120 )) || s=10
  print -r -- "$s"
}
_tick_song_id() {
  if [[ ! -S ${_MPV_SOCK:-/dev/null} ]]; then
    print -r -- "idle"
    return
  fi
  local id
  id=$(MPV_SOCK="$_MPV_SOCK" python3 -c '
import json,os,socket
sock=os.environ.get("MPV_SOCK","")
try:
 s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); s.settimeout(0.2); s.connect(sock)
 s.sendall(b"{\"command\":[\"get_property\",\"path\"]}\n")
 d=b""
 while True:
  c=s.recv(4096)
  if not c: break
  d+=c
  if b"\n" in d: break
 s.close()
 o=json.loads(d.decode().split("\n",1)[0])
 print(o.get("data") or "playing")
except Exception:
 print("playing")
' 2>/dev/null)
  print -r -- "${id:-playing}"
}
_pixie_busy() {
  local d="${XDG_RUNTIME_DIR:-/tmp}" f pid
  local busy=0
  for f in "$d"/pixie-busy.*(N); do
    [[ -e $f ]] || continue
    pid=${f##*.}
    if [[ $pid == <1-> ]] && kill -0 "$pid" 2>/dev/null; then
      busy=1
    else
      rm -f -- "$f" 2>/dev/null
    fi
  done
  (( busy ))
}
_pixie_in_grace() {
  "$HOME/bin/pixie-session" in-grace 2>/dev/null
}
_pixie_end_grace() {
  "$HOME/bin/pixie-session" grace-clear 2>/dev/null || true
}
_pixie_accept_line() {
  _pixie_end_grace
  zle .accept-line
}
zle -N accept-line _pixie_accept_line

_tick_refresh() {
  clear
  if zle; then
    zle reset-prompt
    zle -R
  fi
  _TICK_LAST_TS=$EPOCHSECONDS
}
_precmd_clear() {
  _pixie_busy && return 0
  _pixie_in_grace && return 0
  clear
}
typeset -ga precmd_functions
precmd_functions=(_precmd_clear ${precmd_functions:#_precmd_clear})

tick() {
  local sub="${1:-status}" n="${2:-}"
  mkdir -p "${_TICK_CFG:h}" 2>/dev/null
  case "$sub" in
    on)
      local sec="${n:-10}"
      (( sec >= 2 && sec <= 120 )) || sec=10
      print -r -- "on $sec" >"$_TICK_CFG"
      PERIOD=$_TICK_POLL
      print "tick: on (every ${sec}s + song change; idle only)"
      ;;
    off)
      print -r -- "off" >"$_TICK_CFG"
      PERIOD=0
      print "tick: off"
      ;;
    status)
      if _tick_enabled; then
        print "tick: on — every $(_tick_seconds)s + song change"
        if _pixie_in_grace; then
          print "  read-grace: $("$HOME/bin/pixie-session" grace-left)s left (up to re-read)"
        fi
      else
        print "tick: off"
      fi
      ;;
    *)
      print "Usage: tick {on [seconds]|off|status}"
      return 1
      ;;
  esac
}
up() {
  local arg="${1:-message}"
  _TICK_LAST_TS=$EPOCHSECONDS
  "$HOME/bin/pixie-session" up "$arg"
  "$HOME/bin/pixie-session" grace >/dev/null 2>&1 || true
}
periodic() {
  _tick_enabled || return 0
  _pixie_busy && return 0
  _pixie_in_grace && return 0
  local song need_clear=0
  song=$(_tick_song_id)
  if [[ "$song" != "$_TICK_LAST_SONG" ]]; then
    _TICK_LAST_SONG=$song
    need_clear=1
  fi
  local now=$EPOCHSECONDS
  local interval=$(_tick_seconds)
  if (( now - _TICK_LAST_TS >= interval )); then
    need_clear=1
  fi
  (( need_clear )) || return 0
  _pixie_busy && return 0
  _pixie_in_grace && return 0
  _tick_refresh
}
if _tick_enabled; then
  PERIOD=$_TICK_POLL
  _TICK_LAST_TS=$EPOCHSECONDS
  _TICK_LAST_SONG=$(_tick_song_id)
else
  PERIOD=0
fi
