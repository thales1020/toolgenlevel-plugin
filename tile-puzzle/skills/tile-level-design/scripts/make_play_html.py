"""Generate a self-contained, browser-playable HTML from a stones-format level JSON.

Works EVERYWHERE (incl. claude.ai web sandbox) — unlike the tkinter PlayWindow which
needs a display. Sandbox writes the .html, user downloads + opens in any browser.

Faithful to game rules:
  - pickable = no ACTIVE tile in a HIGHER layer overlaps (|dx|<1 and |dy|<1)
  - pick -> tray; 3 same type in tray auto-clears
  - game over: tray length >= 7 AND no type has count >= 3
  - win: all tiles cleared
  - display label = tile_id + 1

Usage: python make_play_html.py <level.json> [out.html]
"""
import sys, os, json

LEVEL = sys.argv[1] if len(sys.argv) > 1 else None
if not LEVEL:
    raise SystemExit("Usage: python make_play_html.py <level.json> [out.html]")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(os.path.basename(LEVEL))[0] + "_play.html"

with open(LEVEL, encoding="utf-8") as f:
    data = json.load(f)

# Flatten stones -> [{id,x,y,layer,tid}]
tiles = []
tid_seq = 0
for layer in sorted(data["layers"], key=lambda l: l["index"]):
    li = layer["index"]
    for s in layer["stones"]:
        tiles.append({"id": tid_seq, "x": float(s["x"]), "y": float(s["y"]),
                      "layer": li, "tid": int(s.get("i", 0))})
        tid_seq += 1

meta = data.get("metadata", {})
title = f"{meta.get('layout','Level')} · diff {meta.get('difficulty','?')} · {len(tiles)} tiles"

SYMBOLS = "★♥♦♣♠✿❀☀☂☃⚓⚡✈✚✪❄✦❁♛♞♫✓✶❖♨①②③④⑤⑥⑦⑧⑨⑩"
PALETTE = ["#e74c3c","#3498db","#2ecc71","#f39c12","#9b59b6","#1abc9c","#e67e22",
           "#34495e","#16a085","#c0392b","#2980b9","#27ae60","#d35400","#8e44ad",
           "#f1c40f","#7f8c8d","#e84393","#00cec9","#6c5ce7","#fd79a8","#fab1a0",
           "#55efc4","#74b9ff","#a29bfe","#ffeaa7","#fdcb6e","#e17055","#00b894"]

html = """<!DOCTYPE html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
 body{margin:0;background:#2b2b2b;color:#eee;font-family:'Segoe UI',sans-serif;text-align:center}
 h1{font-size:15px;font-weight:500;padding:8px;margin:0;background:#1e1e1e}
 #board{position:relative;margin:10px auto;background:#3a3a3a;border-radius:8px}
 .tile{position:absolute;border-radius:6px;border:2px solid rgba(0,0,0,.35);
   display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:bold;
   color:#fff;box-shadow:1px 1px 3px rgba(0,0,0,.4);transition:opacity .12s,transform .12s;cursor:default}
 .tile.pick{cursor:pointer}
 .tile.pick:hover{transform:scale(1.06);filter:brightness(1.15)}
 .tile.cover{filter:brightness(.45)}
 #tray{margin:10px auto;display:flex;gap:6px;justify-content:center;min-height:46px;align-items:center}
 .slot{width:40px;height:40px;border-radius:6px;background:#222;border:1px dashed #555;
   display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:bold;color:#fff}
 #bar{padding:6px}#msg{font-size:18px;height:24px;font-weight:600}
 button{background:#444;color:#eee;border:0;padding:8px 14px;border-radius:6px;margin:3px;cursor:pointer;font-size:13px}
 button:hover{background:#555}button:disabled{opacity:.4;cursor:default}
 #stats{font-size:12px;color:#aaa}
</style></head><body>
<h1>__TITLE__</h1>
<div id="msg"></div>
<div id="board"></div>
<div id="tray"></div>
<div id="bar">
 <button id="shuffleBtn">🔀 Shuffle (3)</button>
 <button id="undoBtn">↩ Undo (3)</button>
 <button id="slotBtn">＋ Slot (1)</button>
 <button id="restartBtn">⟲ Restart</button>
</div>
<div id="stats"></div>
<script>
const TILES = __TILES__;
const SYMBOLS = __SYMBOLS__;
const PALETTE = __PALETTE__;
const TRAY_MAX_BASE = 7;
let state, traySize, buffs, history;

function init(){
  state = TILES.map(t=>({...t, active:true}));
  traySize = TRAY_MAX_BASE;
  buffs = {shuffle:3, undo:3, slot:1};
  history = [];
  tray = [];
  render();
  setMsg("");
}
let tray = [];

function overlaps(a,b){ return Math.abs(a.x-b.x)<1.0 && Math.abs(a.y-b.y)<1.0; }
function isPickable(t){
  if(!t.active) return false;
  for(const o of state){
    if(o.active && o.layer>t.layer && overlaps(o,t)) return false;
  }
  return true;
}
function setMsg(m,c){ const e=document.getElementById('msg'); e.textContent=m; e.style.color=c||'#eee'; }

function render(){
  const xs=TILES.map(t=>t.x), ys=TILES.map(t=>t.y);
  const minX=Math.min(...xs), maxX=Math.max(...xs), minY=Math.min(...ys), maxY=Math.max(...ys);
  const S=46, pad=30;
  const W=(maxX-minX)*S+pad*2+S, H=(maxY-minY)*S+pad*2+S;
  const board=document.getElementById('board');
  board.style.width=W+'px'; board.style.height=H+'px'; board.innerHTML='';
  const ordered=[...state].sort((a,b)=>a.layer-b.layer);
  for(const t of ordered){
    if(!t.active) continue;
    const d=document.createElement('div');
    d.className='tile';
    const pick=isPickable(t);
    d.classList.add(pick?'pick':'cover');
    d.style.left=((t.x-minX)*S+pad)+'px';
    d.style.top=((maxY-t.y)*S+pad)+'px';
    d.style.width=(S-6)+'px'; d.style.height=(S-6)+'px';
    d.style.zIndex=t.layer+1;
    d.style.background=PALETTE[t.tid%PALETTE.length];
    d.textContent=SYMBOLS[t.tid%SYMBOLS.length]||(t.tid+1);
    d.title='type '+(t.tid+1)+'  L'+t.layer;
    if(pick) d.onclick=()=>pick_tile(t);
    board.appendChild(d);
  }
  // tray
  const tr=document.getElementById('tray'); tr.innerHTML='';
  for(let i=0;i<traySize;i++){
    const s=document.createElement('div'); s.className='slot';
    if(tray[i]!==undefined){ s.style.background=PALETTE[tray[i]%PALETTE.length];
      s.textContent=SYMBOLS[tray[i]%SYMBOLS.length]||(tray[i]+1); }
    tr.appendChild(s);
  }
  const left=state.filter(t=>t.active).length;
  document.getElementById('stats').textContent=`Còn ${left} tiles · tray ${tray.length}/${traySize}`;
  document.getElementById('shuffleBtn').disabled=buffs.shuffle<=0;
  document.getElementById('undoBtn').disabled=buffs.undo<=0||history.length===0;
  document.getElementById('slotBtn').disabled=buffs.slot<=0;
}

function pick_tile(t){
  if(!isPickable(t)) return;
  history.push({tileId:t.id, traySnapshot:[...tray]});
  t.active=false;
  tray.push(t.tid);
  // auto-clear triples
  const counts={};
  tray.forEach(x=>counts[x]=(counts[x]||0)+1);
  for(const k in counts){
    while(counts[k]>=3){
      let removed=0;
      for(let i=tray.length-1;i>=0&&removed<3;i--){ if(tray[i]==k){tray.splice(i,1);removed++;} }
      counts[k]-=3;
    }
  }
  render();
  checkEnd();
}
function checkEnd(){
  const left=state.filter(t=>t.active).length;
  if(left===0 && tray.length===0){ setMsg("🎉 THẮNG!","#2ecc71"); disableAll(); return; }
  const counts={}; tray.forEach(x=>counts[x]=(counts[x]||0)+1);
  const hasTriple=Object.values(counts).some(c=>c>=3);
  if(tray.length>=traySize && !hasTriple){ setMsg("💀 GAME OVER (tray đầy, không có bộ ba)","#e74c3c"); }
}
function disableAll(){ document.querySelectorAll('.tile').forEach(e=>e.onclick=null); }

document.getElementById('restartBtn').onclick=init;
document.getElementById('slotBtn').onclick=()=>{ if(buffs.slot>0){buffs.slot--;traySize++;render();} };
document.getElementById('undoBtn').onclick=()=>{
  if(buffs.undo>0 && history.length){ const h=history.pop(); const t=state.find(s=>s.id===h.tileId);
    t.active=true; tray=h.traySnapshot; buffs.undo--; render(); setMsg(""); }
};
document.getElementById('shuffleBtn').onclick=()=>{
  if(buffs.shuffle<=0) return; buffs.shuffle--;
  const act=state.filter(t=>t.active); const ids=act.map(t=>t.tid);
  for(let i=ids.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[ids[i],ids[j]]=[ids[j],ids[i]];}
  act.forEach((t,i)=>t.tid=ids[i]); render();
};
init();
</script></body></html>"""

html = (html.replace("__TITLE__", title)
            .replace("__TILES__", json.dumps(tiles))
            .replace("__SYMBOLS__", json.dumps(SYMBOLS))
            .replace("__PALETTE__", json.dumps(PALETTE)))

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)

print(f"SAVED {OUT}  ({os.path.getsize(OUT)} bytes)")
print(f"  {len(tiles)} tiles, {len(set(t['tid'] for t in tiles))} types")
print(f"  Open in any browser to play. Shareable single file.")
