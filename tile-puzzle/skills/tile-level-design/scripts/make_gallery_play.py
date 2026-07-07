"""Build ONE self-contained HTML gallery from a folder of stones-format level JSONs.

Grid of cards (mini top-down thumbnail + layout/score/tier). Click a card -> play that
level in an overlay using the SAME faithful engine as make_play_html.py
(pickable = no higher active overlap; tray triple auto-clear; game-over tray>=7 & no triple;
win = cleared; buffs Shuffle/Undo/+1Slot; Restart).

Usage: python make_gallery_play.py <levels_dir> [out.html]
"""
import sys, os, json, glob

SRC = sys.argv[1] if len(sys.argv) > 1 else None
if not SRC:
    raise SystemExit("Usage: python make_gallery_play.py <levels_dir> [out.html]")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SRC, "gallery.html")

SYMBOLS = "★♥♦♣♠✿❀☀☂☃⚓⚡✈✚✪❄✦❁♛♞♫✓✶❖♨①②③④⑤⑥⑦⑧⑨⑩"
PALETTE = ["#e74c3c","#3498db","#2ecc71","#f39c12","#9b59b6","#1abc9c","#e67e22",
           "#34495e","#16a085","#c0392b","#2980b9","#27ae60","#d35400","#8e44ad",
           "#f1c40f","#7f8c8d","#e84393","#00cec9","#6c5ce7","#fd79a8","#fab1a0",
           "#55efc4","#74b9ff","#a29bfe","#ffeaa7","#fdcb6e","#e17055","#00b894"]

TIER_COLOR = {"Very Easy": "#2ecc71", "Easy": "#27ae60", "Normal": "#f39c12",
              "Hard": "#e67e22", "Very Hard": "#e74c3c", "Extreme": "#c0392b"}

levels = []
for fp in sorted(glob.glob(os.path.join(SRC, "*.json"))):
    if os.path.basename(fp) in ("manifest.json", "gallery.json"):
        continue
    with open(fp, encoding="utf-8") as f:
        data = json.load(f)
    if "layers" not in data:
        continue
    tiles = []
    for layer in sorted(data["layers"], key=lambda l: l["index"]):
        li = layer["index"]
        for s in layer["stones"]:
            tiles.append({"x": float(s["x"]), "y": float(s["y"]),
                          "layer": li, "tid": int(s.get("i", 0))})
    m = data.get("metadata", {})
    levels.append({
        "file": os.path.basename(fp),
        "layout": m.get("layout", os.path.splitext(os.path.basename(fp))[0]),
        "score": m.get("difficulty", "?"),
        "tier": m.get("tier", "?"),
        "cells": m.get("total_tiles", len(tiles)),
        "types": m.get("n_types", len({t["tid"] for t in tiles})),
        "tiles": tiles,
    })

# sort by score ascending (None/'?' last)
def skey(l):
    s = l["score"]
    return s if isinstance(s, (int, float)) else 1e9
levels.sort(key=skey)

HTML = """<!DOCTYPE html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Test Set · __N__ màn</title>
<style>
 :root{--bg:#1b1b1d;--card:#2b2b2e;--ink:#eee}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--ink);font-family:'Segoe UI',sans-serif}
 header{padding:14px 18px;background:#121213;position:sticky;top:0;z-index:50;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
 header h1{font-size:17px;margin:0;font-weight:600}
 header .sub{font-size:12px;color:#999}
 #filters button{background:#333;color:#ccc;border:0;padding:5px 10px;border-radius:14px;margin:2px;cursor:pointer;font-size:12px}
 #filters button.on{background:#3498db;color:#fff}
 #grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px;padding:18px}
 .card{background:var(--card);border-radius:10px;overflow:hidden;cursor:pointer;border:1px solid #383838;
   transition:transform .1s,border-color .1s}
 .card:hover{transform:translateY(-3px);border-color:#3498db}
 .thumb{position:relative;height:150px;background:#202022;overflow:hidden}
 .thumb .t{position:absolute;border-radius:2px}
 .meta{padding:9px 11px}
 .meta .top{display:flex;justify-content:space-between;align-items:center}
 .meta .lay{font-weight:600;font-size:14px}
 .badge{font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px;color:#111}
 .meta .row{font-size:11px;color:#9a9a9a;margin-top:4px;display:flex;justify-content:space-between}
 .score{font-size:12px;color:#ddd;font-weight:600}
 /* overlay player */
 #ov{position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:100;display:none;overflow:auto;text-align:center}
 #ov.show{display:block}
 #pTitle{font-size:15px;font-weight:600;padding:10px;background:#1e1e1e;position:sticky;top:0}
 #closeBtn{position:absolute;right:12px;top:7px;background:#c0392b}
 #board{position:relative;margin:10px auto;background:#3a3a3a;border-radius:8px}
 .tile{position:absolute;border-radius:6px;border:2px solid rgba(0,0,0,.35);display:flex;align-items:center;
   justify-content:center;font-size:18px;font-weight:bold;color:#fff;box-shadow:1px 1px 3px rgba(0,0,0,.4);
   transition:opacity .12s,transform .12s;cursor:default}
 .tile.pick{cursor:pointer}.tile.pick:hover{transform:scale(1.06);filter:brightness(1.15)}
 .tile.cover{filter:brightness(.45)}
 #tray{margin:10px auto;display:flex;gap:6px;justify-content:center;min-height:46px;align-items:center}
 .slot{width:40px;height:40px;border-radius:6px;background:#222;border:1px dashed #555;display:flex;
   align-items:center;justify-content:center;font-size:18px;font-weight:bold;color:#fff}
 #bar{padding:6px}#msg{font-size:18px;height:24px;font-weight:600}
 #ov button{background:#444;color:#eee;border:0;padding:8px 14px;border-radius:6px;margin:3px;cursor:pointer;font-size:13px}
 #ov button:hover{background:#555}#ov button:disabled{opacity:.4;cursor:default}
 #stats{font-size:12px;color:#aaa;padding-bottom:30px}
</style></head><body>
<header>
 <h1>🎮 Test Set</h1><span class="sub">__N__ màn · bấm để chơi · luật chuẩn (tray 7, không buff = bar khó nhất)</span>
 <span id="filters" style="margin-left:auto"></span>
</header>
<div id="grid"></div>

<div id="ov">
 <div id="pTitle"><span id="pName"></span> <button id="closeBtn">✕ Đóng</button></div>
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
</div>

<script>
const LEVELS = __LEVELS__;
const SYMBOLS = __SYMBOLS__;
const PALETTE = __PALETTE__;
const TIER_COLOR = __TIERCOLOR__;
const TRAY_MAX_BASE = 7;

/* ---------- gallery grid ---------- */
function thumb(el, tiles){
  const xs=tiles.map(t=>t.x), ys=tiles.map(t=>t.y);
  const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
  const w=190,h=150,pad=10;
  const sx=(w-2*pad)/((maxX-minX)||1), sy=(h-2*pad)/((maxY-minY)||1);
  const s=Math.min(sx,sy,16), cs=Math.max(4,s*0.8);
  const ox=(w-(maxX-minX)*s)/2, oy=(h-(maxY-minY)*s)/2;
  [...tiles].sort((a,b)=>a.layer-b.layer).forEach(t=>{
    const d=document.createElement('div'); d.className='t';
    d.style.left=((t.x-minX)*s+ox-cs/2)+'px';
    d.style.top=((maxY-t.y)*s+oy-cs/2)+'px';
    d.style.width=cs+'px'; d.style.height=cs+'px';
    d.style.background=PALETTE[t.tid%PALETTE.length];
    d.style.filter='brightness('+(0.55+0.12*t.layer)+')';
    d.style.zIndex=t.layer;
    el.appendChild(d);
  });
}
let curFilter='all';
function buildGrid(){
  const grid=document.getElementById('grid'); grid.innerHTML='';
  LEVELS.forEach((lv,idx)=>{
    if(curFilter!=='all' && lv.tier!==curFilter) return;
    const card=document.createElement('div'); card.className='card'; card.onclick=()=>openLevel(idx);
    const th=document.createElement('div'); th.className='thumb'; thumb(th,lv.tiles);
    const meta=document.createElement('div'); meta.className='meta';
    const tc=TIER_COLOR[lv.tier]||'#888';
    meta.innerHTML=`<div class="top"><span class="lay">${lv.layout}</span>
      <span class="badge" style="background:${tc}">${lv.tier}</span></div>
      <div class="row"><span class="score">◆ ${lv.score}</span><span>${lv.cells} ô · ${lv.types} loại</span></div>`;
    card.appendChild(th); card.appendChild(meta); grid.appendChild(card);
  });
}
function buildFilters(){
  const tiers=['all',...[...new Set(LEVELS.map(l=>l.tier))]];
  const f=document.getElementById('filters'); f.innerHTML='';
  tiers.forEach(t=>{const b=document.createElement('button');b.textContent=(t==='all'?'Tất cả':t);
    if(t===curFilter)b.className='on';
    b.onclick=()=>{curFilter=t;buildFilters();buildGrid();};f.appendChild(b);});
}

/* ---------- player (same engine as make_play_html) ---------- */
let TILES=[], state, traySize, buffs, history, tray=[];
function openLevel(idx){
  const lv=LEVELS[idx];
  TILES=lv.tiles.map((t,i)=>({...t,id:i}));
  document.getElementById('pName').textContent=`${lv.layout} · diff ${lv.score} · ${lv.tier} · ${lv.cells} tiles`;
  document.getElementById('ov').classList.add('show');
  initGame();
}
function closeLevel(){ document.getElementById('ov').classList.remove('show'); }
function initGame(){
  state=TILES.map(t=>({...t,active:true})); traySize=TRAY_MAX_BASE;
  buffs={shuffle:3,undo:3,slot:1}; history=[]; tray=[]; render(); setMsg("");
}
function overlaps(a,b){return Math.abs(a.x-b.x)<1.0&&Math.abs(a.y-b.y)<1.0;}
function isPickable(t){ if(!t.active)return false;
  for(const o of state){if(o.active&&o.layer>t.layer&&overlaps(o,t))return false;} return true; }
function setMsg(m,c){const e=document.getElementById('msg');e.textContent=m;e.style.color=c||'#eee';}
function render(){
  const xs=TILES.map(t=>t.x),ys=TILES.map(t=>t.y);
  const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
  const S=46,pad=30,W=(maxX-minX)*S+pad*2+S,H=(maxY-minY)*S+pad*2+S;
  const board=document.getElementById('board');
  board.style.width=W+'px';board.style.height=H+'px';board.innerHTML='';
  [...state].sort((a,b)=>a.layer-b.layer).forEach(t=>{
    if(!t.active)return; const d=document.createElement('div'); d.className='tile';
    const pick=isPickable(t); d.classList.add(pick?'pick':'cover');
    d.style.left=((t.x-minX)*S+pad)+'px'; d.style.top=((maxY-t.y)*S+pad)+'px';
    d.style.width=(S-6)+'px'; d.style.height=(S-6)+'px'; d.style.zIndex=t.layer+1;
    d.style.background=PALETTE[t.tid%PALETTE.length];
    d.textContent=SYMBOLS[t.tid%SYMBOLS.length]||(t.tid+1);
    d.title='type '+(t.tid+1)+'  L'+t.layer;
    if(pick)d.onclick=()=>pick_tile(t); board.appendChild(d);
  });
  const tr=document.getElementById('tray'); tr.innerHTML='';
  for(let i=0;i<traySize;i++){const s=document.createElement('div');s.className='slot';
    if(tray[i]!==undefined){s.style.background=PALETTE[tray[i]%PALETTE.length];
      s.textContent=SYMBOLS[tray[i]%SYMBOLS.length]||(tray[i]+1);} tr.appendChild(s);}
  const left=state.filter(t=>t.active).length;
  document.getElementById('stats').textContent=`Còn ${left} tiles · tray ${tray.length}/${traySize}`;
  document.getElementById('shuffleBtn').disabled=buffs.shuffle<=0;
  document.getElementById('undoBtn').disabled=buffs.undo<=0||history.length===0;
  document.getElementById('slotBtn').disabled=buffs.slot<=0;
}
function pick_tile(t){
  if(!isPickable(t))return; history.push({tileId:t.id,traySnapshot:[...tray]});
  t.active=false; tray.push(t.tid);
  const counts={}; tray.forEach(x=>counts[x]=(counts[x]||0)+1);
  for(const k in counts){while(counts[k]>=3){let removed=0;
    for(let i=tray.length-1;i>=0&&removed<3;i--){if(tray[i]==k){tray.splice(i,1);removed++;}} counts[k]-=3;}}
  render(); checkEnd();
}
function checkEnd(){
  const left=state.filter(t=>t.active).length;
  if(left===0&&tray.length===0){setMsg("🎉 THẮNG!","#2ecc71");document.querySelectorAll('.tile').forEach(e=>e.onclick=null);return;}
  const counts={};tray.forEach(x=>counts[x]=(counts[x]||0)+1);
  if(tray.length>=traySize&&!Object.values(counts).some(c=>c>=3))setMsg("💀 GAME OVER (tray đầy, không có bộ ba)","#e74c3c");
}
document.getElementById('closeBtn').onclick=closeLevel;
document.getElementById('restartBtn').onclick=initGame;
document.getElementById('slotBtn').onclick=()=>{if(buffs.slot>0){buffs.slot--;traySize++;render();}};
document.getElementById('undoBtn').onclick=()=>{
  if(buffs.undo>0&&history.length){const h=history.pop();const t=state.find(s=>s.id===h.tileId);
    t.active=true;tray=h.traySnapshot;buffs.undo--;render();setMsg("");}};
document.getElementById('shuffleBtn').onclick=()=>{
  if(buffs.shuffle<=0)return; buffs.shuffle--;
  const act=state.filter(t=>t.active),ids=act.map(t=>t.tid);
  for(let i=ids.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[ids[i],ids[j]]=[ids[j],ids[i]];}
  act.forEach((t,i)=>t.tid=ids[i]); render();};
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeLevel();});
buildFilters(); buildGrid();
</script></body></html>"""

html = (HTML.replace("__N__", str(len(levels)))
            .replace("__LEVELS__", json.dumps(levels, ensure_ascii=False))
            .replace("__SYMBOLS__", json.dumps(SYMBOLS))
            .replace("__PALETTE__", json.dumps(PALETTE))
            .replace("__TIERCOLOR__", json.dumps(TIER_COLOR, ensure_ascii=False)))

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)

print(f"SAVED {OUT}  ({os.path.getsize(OUT)} bytes)")
print(f"  {len(levels)} levels embedded")
print(f"  Open in any browser: grid of cards, click to play. Single shareable file.")
