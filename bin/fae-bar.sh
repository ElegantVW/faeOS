#!/usr/bin/env bash
set -u
exec 2>/dev/null
pink="#E879A0"
hot="#FF2D55"
lilac="#C44D7A"
plum="#9D5C75"
cream="#FFE3EE"

song() {
python3 -c '
import json,os,socket
try:
    s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    s.settimeout(0.2)
    s.connect("/tmp/siren-mpv.sock")
    s.sendall(b"{\"command\":[\"get_property\",\"path\"]}\n")
    d=b""
    while True:
        c=s.recv(4096)
        if not c: break
        d+=c
        if b"\n" in d: break
    s.close()
    p=json.loads(d.decode().split("\n",1)[0]).get("data") or ""
    print(os.path.basename(p))
except Exception:
    print("")
'
}

bulk() {
python3 -c '
import re,subprocess
try:
    out=subprocess.run([os.path.expanduser("~/bin/bulwark"),"status"],
                       capture_output=True,text=True,timeout=2,stdin=subprocess.DEVNULL).stdout
    bad=any(int(n)>0 for n in re.findall(r"(\d+) finding",out))
except Exception:
    bad=False
print("bad" if bad else "ok")
'
}

wins() {
python3 -c '
import json,subprocess,sys
t=json.loads(subprocess.run(["i3-msg","-t","get_tree"],capture_output=True,text=True).stdout)
ws=None
def find(n):
    if n.get("focused"):
        while n.get("type") != "workspace" and n.get("parent"):
            n = n["parent"]
        return n if n.get("type") == "workspace" else None
    for c in n.get("nodes",[])+n.get("floating_nodes",[]):
        r=find(c)
        if r: return r
    return None
def first_ws(n):
    if n.get("type")=="workspace": return n
    for c in n.get("nodes",[])+n.get("floating_nodes",[]):
        r=first_ws(c)
        if r and not r["name"].startswith("__i3_"): return r
    return None
def allwin(n):
    for c in n.get("nodes",[])+n.get("floating_nodes",[]):
        yield from allwin(c)
    if n.get("window"): yield n
ws=find(t) or first_ws(t)
if not ws: raise SystemExit
pink="#E879A0"; cream="#FFE3EE"
for n in [w for w in allwin(ws)][:8]:
    wp=n.get("window_properties") or {}
    label=(wp.get("title") or wp.get("class") or "?").strip()
    if len(label)>10: label=label[:9]+"…"
    if n.get("focused"): label="• "+label
    sys.stdout.write(label + "\x1f" + (pink if n.get("focused") else cream) + "\x1fwin:" + str(n["id"]) + "\x1f1\x00")
'
}

emit() {
python3 -c '
import json,sys
blocks=[]
for p in sys.stdin.buffer.read().split(b"\x00"):
    if not p: continue
    t,c,name,sep=p.rsplit(b"\x1f",3)
    blocks.append({"full_text":t.decode("utf-8","replace"),
                   "color":c.decode("ascii"),
                   "name":name.decode("ascii"),
                   "separator":sep==b"1"})
fixed=294
for b in blocks:
    if b["name"]=="about":
        fixed=294+7.22*(len(b["full_text"])-12)
winw=sum(9+7.2*len(b["full_text"]) for b in blocks if b["name"].startswith("win:"))
total=fixed+winw
minw=int(951-total/2)
if minw>0:
    blocks.append({"full_text":" ","min_width":minw,"separator":False})
sys.stdout.write(json.dumps(blocks,ensure_ascii=False,separators=(",",":")))'
}

clk() {
  while IFS= read -r line; do
    name=$(printf '%s' "${line#,}" | python3 -c 'import json,sys
try:
    print(json.loads(sys.stdin.readline()).get("name",""))
except Exception:
    print("")' 2>/dev/null)
    case "$name" in
      win_min)  setsid i3-msg move scratchpad >/dev/null 2>&1 & ;;
      win_restore) setsid i3-msg scratchpad show >/dev/null 2>&1 & ;;
      win_max)  setsid i3-msg fullscreen toggle >/dev/null 2>&1 & ;;
      win_close) setsid i3-msg kill >/dev/null 2>&1 & ;;
      win:*)    setsid sh -c "$HOME/bin/fae-win ${name#win:}" >/dev/null 2>&1 & ;;
      about|siren|ether|sys|pwr|date|bulwark)
        setsid sh -c "$HOME/bin/fae-panel $name" >/dev/null 2>&1 & ;;
    esac
  done
}
exec 3<&0
clk <&3 &

echo '{"version":1,"click_events":true}'
echo '['
first=true
while :; do
  if $first; then
    first=false
  else
    printf ','
  fi
  bw=$(bulk)
  if [ "$bw" = "bad" ]; then shield_color=$hot; else shield_color=$cream; fi
  {
    wins
    printf '%s\x1f%s\x1fwin_min\x1f0\x00' "−" "$pink"
    printf '%s\x1f%s\x1fwin_max\x1f0\x00' "□" "$pink"
    printf '%s\x1f%s\x1fwin_close\x1f1\x00' "×" "$pink"
    printf '%s\x1f%s\x1fwin_restore\x1f1\x00' "⌂" "$pink"
    printf '%s\x1f%s\x1fabout\x1f1\x00' "♥ $USER" "$pink"
    printf '%s\x1f%s\x1fsiren\x1f1\x00' "♫" "$cream"
    printf '%s\x1f%s\x1fether\x1f1\x00' "✈" "$lilac"
    printf '%s\x1f%s\x1fsys\x1f1\x00' "✧" "$hot"
    printf '%s\x1f%s\x1fpwr\x1f1\x00' "⚡" "$plum"
    printf '%s\x1f%s\x1fdate\x1f1\x00' "✪" "$cream"
    printf '%s\x1f%s\x1fbulwark\x1f1\x00' "🛡" "$shield_color"
  } | emit
  printf '\n'
  sleep 1
done
