"""Generate a self-contained, browser-playable HTML from a stones-format level JSON.

Works EVERYWHERE (incl. claude.ai web sandbox) — unlike the tkinter PlayWindow which
needs a display. Sandbox writes the .html, user downloads + opens in any browser.

Faithful to game rules (normal match-3):
  - pickable = no ACTIVE tile in a HIGHER layer overlaps (|dx|<1 and |dy|<1)
  - pick -> tray; 3 same type in tray auto-clears
  - game over: tray length >= 7 AND no type has count >= 3
  - win: all tiles cleared
  - display label = tile_id + 1

SPECIAL tiles (auto-detected — match the simulator's solve_v3_special model):
  - BONUS (i=1001) / MISSION (i=1002): NON-match-3 covers. Never enter the tray; AUTO-CLEAR
    for free (cascading) the instant nothing in a higher layer covers them.
  - MYSTERY (o:[0], or legacy m:true) / CLOUD (o:[1]): a NORMAL match-3 tile shown under the mystery
    cover art. Reveal timing differs — MYSTERY stays covered on the board EVEN when pickable (picked
    BLIND; its real colour shows only in the TRAY once picked); CLOUD reveals on the board the instant
    it is uncovered (pickable). Both then play as normal match-3 tiles.

REAL ART (play-test only — the level JSON is NOT changed):
  If the bundled assets are present (../assets/tile_faces from Group_1, ../assets/tilebase), each
  tile renders as ONE randomly-chosen tilebase plate for the whole level with a Group_1 tile face on
  top; mystery uses tile_cover_mystery. Faces are mapped per distinct tile-TYPE (display only — the
  `i` values in the JSON are untouched). Only the images actually used are embedded (base64), so the
  file stays small. Falls back to coloured squares + unicode symbols if the assets are missing.

Usage: python make_play_html.py <level.json> [out.html]
"""
import sys, os, json, glob, base64, zlib, random

LEVEL = sys.argv[1] if len(sys.argv) > 1 else None
if not LEVEL:
    raise SystemExit("Usage: python make_play_html.py <level.json> [out.html]")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(os.path.basename(LEVEL))[0] + "_play.html"

with open(LEVEL, encoding="utf-8") as f:
    data = json.load(f)

# ---- flatten stones -> [{id,x,y,layer,tid,special,mystery,cloud}] ----
# MYSTERY (`o:[0]`, legacy `m:true`) and CLOUD (`o:[1]`) are NORMAL tiles under the tile_cover_mystery
# art. MYSTERY stays covered on the board until PICKED (blind pick, colour shown in the tray); CLOUD
# reveals on the board when uncovered (pickable).
tiles = []
tid_seq = 0
n_special = n_mystery = n_cloud = 0
for layer in sorted(data["layers"], key=lambda l: l["index"]):
    li = layer["index"]
    for s in layer["stones"]:
        i = int(s.get("i", 0))
        is_special = i >= 1001
        _o = s.get("o") or []
        mystery = ((0 in _o) or bool(s.get("m"))) and not is_special   # o:[0] new format / m:true legacy
        cloud = (1 in _o) and not is_special                           # o:[1] = cloud
        if is_special:
            n_special += 1
        if mystery:
            n_mystery += 1
        if cloud:
            n_cloud += 1
        tiles.append({"id": tid_seq, "x": float(s["x"]), "y": float(s["y"]), "layer": li,
                      "tid": (0 if is_special else i - 1),
                      "special": (i if is_special else 0), "mystery": mystery, "cloud": cloud,
                      "s": float(s.get("s", 0))})
        tid_seq += 1

# ---- REAL ART: bundle a random tilebase + a Group_1 face per distinct type (display-only) ----
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
FACE_DIR = os.path.join(ASSETS, "tile_faces")
BASE_DIR = os.path.join(ASSETS, "tilebase")


def _datauri(path):
    with open(path, "rb") as fh:
        return "data:image/png;base64," + base64.b64encode(fh.read()).decode()


def _face_key(p):
    b = os.path.splitext(os.path.basename(p))[0]
    return (0, int(b)) if b.isdigit() else (1, b)


art = {"base": None, "mystery": None, "cloud": None, "faces": {}}   # faces: {str(tid): datauri}
face_files = sorted(glob.glob(os.path.join(FACE_DIR, "*.png")), key=_face_key)
# random tilebase pool = the named plates (tile_base_1..9 + water); stable-random per level name
base_pool = sorted(glob.glob(os.path.join(BASE_DIR, "tile_base_*.png")))
# MYSTERY cover = the blue "?" plate; CLOUD cover = the bandaged tile_cover_mystery plate (distinct arts)
mystery_png = os.path.join(BASE_DIR, "tile_cover_question.png")
cloud_png = os.path.join(BASE_DIR, "tile_cover_mystery.png")
if face_files and base_pool:
    rng = random.Random(zlib.crc32(os.path.basename(LEVEL).encode()))
    art["base"] = _datauri(rng.choice(base_pool))
    if os.path.exists(mystery_png):
        art["mystery"] = _datauri(mystery_png)
    if os.path.exists(cloud_png):
        art["cloud"] = _datauri(cloud_png)
    # Map each distinct tile-TYPE to a DISTINCT face sprite (INJECTIVE — two different types must NEVER
    # share a sprite, or they'd look identical yet never match). Prefer the EXACT sprite when the tile's
    # raw id (tid+1) matches a Group_1 filename (real reference levels use ids 85,142-170 → render true);
    # every other type takes an UNUSED shuffled sprite so no sprite is reused (until types > sprites).
    face_by_id = {int(os.path.splitext(os.path.basename(p))[0]): p
                  for p in face_files if os.path.splitext(os.path.basename(p))[0].isdigit()}
    distinct = sorted({t["tid"] for t in tiles if not t["special"]})
    pool = face_files[:]
    rng.shuffle(pool)
    assigned = {}
    used = set()
    for tid in distinct:                       # pass 1: exact-id sprites, claim them
        p = face_by_id.get(tid + 1)
        if p is not None and p not in used:
            assigned[tid] = p
            used.add(p)
    avail = [p for p in pool if p not in used]
    ai = 0
    for tid in distinct:                        # pass 2: remaining types get an UNUSED sprite each
        if tid in assigned:
            continue
        if ai < len(avail):
            p = avail[ai]; ai += 1
        else:                                   # more types than sprites — reuse is unavoidable, cycle
            p = pool[len(assigned) % len(pool)]
        assigned[tid] = p
    for tid, p in assigned.items():
        art["faces"][str(tid)] = _datauri(p)

HAS_ART = bool(art["base"] and art["faces"])

meta = data.get("metadata", {})
extra = []
if n_special:
    extra.append(f"{n_special} special")
if n_mystery:
    extra.append(f"{n_mystery} mystery")
if n_cloud:
    extra.append(f"{n_cloud} cloud")
suffix = ("  ·  " + " · ".join(extra)) if extra else ""
title = f"{meta.get('layout','Level')} · {len(tiles)} tiles{suffix}"

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
 .tile{position:absolute;display:flex;align-items:center;justify-content:center;
   background-size:100% 100%;background-repeat:no-repeat;background-position:center;
   transition:opacity .12s,transform .12s;cursor:default}
 .tile.noart{border-radius:6px;border:2px solid rgba(0,0,0,.35);font-size:18px;font-weight:bold;
   color:#fff;box-shadow:1px 1px 3px rgba(0,0,0,.4)}
 .tile.pick{cursor:pointer}
 .tile.pick:hover{transform:scale(1.06);filter:brightness(1.12)}
 .tile.cover{filter:brightness(.5)}
 .face{width:78%;height:78%;background-size:contain;background-repeat:no-repeat;background-position:center;
   display:flex;align-items:center;justify-content:center;font-size:17px}
 .badge{font-size:1em;filter:drop-shadow(0 1px 1px rgba(0,0,0,.5))}
 #tray{margin:10px auto;display:flex;gap:6px;justify-content:center;min-height:52px;align-items:center}
 .slot{width:44px;height:48px;border-radius:6px;background:#222;border:1px dashed #555;
   display:flex;align-items:center;justify-content:center;background-size:contain;background-repeat:no-repeat;
   background-position:center;font-size:18px;font-weight:bold;color:#fff}
 #bar{padding:6px}#msg{font-size:18px;height:24px;font-weight:600}
 button{background:#444;color:#eee;border:0;padding:8px 14px;border-radius:6px;margin:3px;cursor:pointer;font-size:13px}
 button:hover{background:#555}button:disabled{opacity:.4;cursor:default}
 #stats{font-size:12px;color:#aaa}
 #legend{font-size:11px;color:#999;padding:2px 8px 8px}
 #legend b{color:#ccc}
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
<div id="legend"></div>
<script>
const TILES = __TILES__;
const SYMBOLS = __SYMBOLS__;
const PALETTE = __PALETTE__;
const ART = __ART__;              // {base, mystery, faces:{tid:datauri}} or nulls
const HAS_ART = __HASART__;
const TRAY_MAX_BASE = 7;
let state, traySize, buffs, history, tray;

function faceOf(tid){ return ART.faces[tid] || null; }

function init(){
  state = TILES.map(t=>({...t, active:true}));
  traySize = TRAY_MAX_BASE;
  buffs = {shuffle:3, undo:3, slot:1};
  history = [];
  tray = [];
  autoClearSpecials();
  render();
  setMsg("");
}

// Collision half-extent (grid units): a NORMAL tile is 1x1 (half 0.5). A SPECIAL is a 2x2 (half 1.0)
// OR 3x3 (half 1.5) object, read from its render size `s`: MISSION 0.7=2x2 / 1.0=3x3 (s>=0.85 -> 3x3);
// BONUS 0.9=2x2 / 1.4=3x3 (s>=1.15 -> 3x3). A special covers / is covered by its WHOLE footprint, so it
// only auto-clears when that whole footprint is clear on top. Footprints overlap iff |dx| < ha+hb.
function specHalf(t){
  const s = t.s || 0;
  if(t.special===1001) return s >= 1.15 ? 1.5 : 1.0;   // bonus coin
  return s >= 0.85 ? 1.5 : 1.0;                         // mission tile (1002)
}
function halfOf(t){ return t.special ? specHalf(t) : 0.5; }
function overlaps(a,b){ const h=halfOf(a)+halfOf(b); return Math.abs(a.x-b.x)<h && Math.abs(a.y-b.y)<h; }
function isPickable(t){
  if(!t.active) return false;
  for(const o of state){ if(o.active && o.layer>t.layer && overlaps(o,t)) return false; }
  return true;
}
function autoClearSpecials(){
  let changed=true;
  while(changed){ changed=false;
    for(const t of state){ if(t.active && t.special && isPickable(t)){ t.active=false; changed=true; } }
  }
}
function setMsg(m,c){ const e=document.getElementById('msg'); e.textContent=m; e.style.color=c||'#eee'; }

function styleTile(d, t, pick){
  const face=document.createElement('div'); face.className='face';
  // SPECIALS: same mechanic (big cover + auto-clear), differ only in SHAPE — bonus ROUND, mission square.
  if(t.special){
    const gold='radial-gradient(circle at 40% 34%, #ffe58a, #f2b301 68%, #b07d05)';
    const pink='radial-gradient(circle at 40% 34%, #ffa6d2, #e84393 68%, #a2286a)';
    d.style.background = t.special===1001 ? gold : pink;
    d.style.borderRadius = t.special===1001 ? '50%' : '20%';   // 1001 bonus = circle, 1002 mission = rounded square
    d.style.border='2px solid rgba(0,0,0,.28)';
    d.style.boxShadow='0 0 9px 2px rgba(255,255,255,.28)';
    face.innerHTML='<span class="badge">'+(t.special===1001?'🎁':'🎯')+'</span>';
    d.title=(t.special===1001?'BONUS (tròn)':'MISSION (vuông)')+' — auto-clear khi hết ô che, L'+t.layer;
    d.appendChild(face); return;
  }
  // Cover art fills the WHOLE tile (no base plate, no small inner face). Reveal timing differs:
  //   MYSTERY (o:[0]/m) stays covered on the board EVEN when pickable — picked BLIND, real colour shows
  //     only in the tray once picked.  CLOUD (o:[1]) reveals on the board the instant it is uncovered.
  const covered = t.mystery ? true : (t.cloud && !pick);
  if(covered){
    const coverArt = t.cloud ? ART.cloud : ART.mystery;   // CLOUD = bandaged plate; MYSTERY = blue "?"
    if(HAS_ART && coverArt){ d.style.backgroundImage='url('+coverArt+')'; }
    else { d.classList.add('noart'); d.style.background='#5a5a5a'; face.textContent='?'; d.appendChild(face); }
    d.title=(t.cloud?'CLOUD (dọn ô trên để lộ)':'MYSTERY (pick mù → lộ màu trong khay)')+' L'+t.layer;
    return;
  }
  // NORMAL / revealed: tilebase plate under a Group_1 face
  if(HAS_ART && ART.base){ d.style.backgroundImage='url('+ART.base+')'; }
  else { d.classList.add('noart'); d.style.background=PALETTE[t.tid%PALETTE.length]; }
  const f=faceOf(t.tid);
  if(HAS_ART && f){ face.style.backgroundImage='url('+f+')'; }
  else { face.textContent=SYMBOLS[t.tid%SYMBOLS.length]||(t.tid+1); }
  d.title=((t.mystery||t.cloud)?(t.cloud?'cloud → ':'mystery → '):'')+'type '+(t.tid+1)+'  L'+t.layer;
  d.appendChild(face);
}

function render(){
  const xs=TILES.map(t=>t.x), ys=TILES.map(t=>t.y);
  const minX=Math.min(...xs), maxX=Math.max(...xs), minY=Math.min(...ys), maxY=Math.max(...ys);
  // SQUARE cells (pitch == tile size, touching) so a special's 2x2 footprint renders as a true 2x2
  // (bonus = a real circle, not an ellipse) and VISUAL == LOGIC.
  const TW=56, TH=56, SX=TW, SY=TH, pad=22;
  const W=(maxX-minX)*SX+pad*2+TW, H=(maxY-minY)*SY+pad*2+TH;
  const board=document.getElementById('board');
  board.style.width=W+'px'; board.style.height=H+'px'; board.innerHTML='';
  const ordered=[...state].sort((a,b)=>a.layer-b.layer);
  for(const t of ordered){
    if(!t.active) continue;
    const d=document.createElement('div');
    d.className='tile';
    const pick = isPickable(t);
    d.classList.add(pick?'pick':'cover');
    // specials render EXACTLY their collision footprint (2x2 or 3x3, units = 2*half) centred on (x,y)
    // so the frame == what it blocks (no decorative overhang) and auto-clear reads correctly.
    let w=TW, h=TH, lx=((t.x-minX)*SX+pad), ty=((maxY-t.y)*SY+pad);
    if(t.special){
      const u = 2*halfOf(t);          // 2 units (2x2) or 3 units (3x3)
      w=u*TW; h=u*TH; lx-=(w-TW)/2; ty-=(h-TH)/2;
    }
    d.style.left=lx+'px'; d.style.top=ty+'px';
    d.style.width=w+'px'; d.style.height=h+'px';
    // z by TRUE layer: a special covers lower tiles but higher-layer tiles render ON TOP of it (cover it at start)
    d.style.zIndex=t.layer+1;
    if(t.special){
      d.style.fontSize=(h*0.5)+'px';       // scale the 🎁/🎯 badge with the big tile
      d.style.pointerEvents='none';        // never clicked (auto-clear only) -> don't eat clicks on tiles under/beside it
    }
    styleTile(d, t, pick);
    if(pick && !t.special) d.onclick=()=>pick_tile(t);
    board.appendChild(d);
  }
  const tr=document.getElementById('tray'); tr.innerHTML='';
  for(let i=0;i<traySize;i++){
    const s=document.createElement('div'); s.className='slot';
    if(tray[i]!==undefined){
      const f=faceOf(tray[i]);
      if(HAS_ART && ART.base){ s.style.backgroundImage='url('+ART.base+')'; }
      else { s.style.background=PALETTE[tray[i]%PALETTE.length]; }
      const fc=document.createElement('div'); fc.className='face';
      if(HAS_ART && f){ fc.style.backgroundImage='url('+f+')'; }
      else { fc.textContent=SYMBOLS[tray[i]%SYMBOLS.length]||(tray[i]+1); }
      s.appendChild(fc);
    }
    tr.appendChild(s);
  }
  const left=state.filter(t=>t.active).length;
  const spLeft=state.filter(t=>t.active&&t.special).length;
  document.getElementById('stats').textContent=
    `Còn ${left} tiles`+(spLeft?` (${spLeft} special)`:``)+` · tray ${tray.length}/${traySize}`;
  document.getElementById('legend').innerHTML=
    `<b>🎁</b> bonus &nbsp; <b>🎯</b> mission — tự biến mất khi không còn ô che &nbsp;|&nbsp; ô úp: <b>mystery</b> (o:[0], pick mù → lộ trong khay) · <b>cloud</b> (o:[1], lộ khi hết ô che)`;
  document.getElementById('shuffleBtn').disabled=buffs.shuffle<=0;
  document.getElementById('undoBtn').disabled=buffs.undo<=0||history.length===0;
  document.getElementById('slotBtn').disabled=buffs.slot<=0;
}

function snapshot(){ return {active:state.map(t=>t.active), tray:[...tray]}; }
function restore(h){ state.forEach((t,i)=>t.active=h.active[i]); tray=[...h.tray]; }

function pick_tile(t){
  if(t.special || !isPickable(t)) return;
  history.push(snapshot());
  t.active=false;
  tray.push(t.tid);
  const counts={}; tray.forEach(x=>counts[x]=(counts[x]||0)+1);
  for(const k in counts){
    while(counts[k]>=3){
      let removed=0;
      for(let i=tray.length-1;i>=0&&removed<3;i--){ if(tray[i]==k){tray.splice(i,1);removed++;} }
      counts[k]-=3;
    }
  }
  autoClearSpecials();
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
  if(buffs.undo>0 && history.length){ restore(history.pop()); buffs.undo--; render(); setMsg(""); }
};
document.getElementById('shuffleBtn').onclick=()=>{
  if(buffs.shuffle<=0) return; buffs.shuffle--;
  const act=state.filter(t=>t.active && !t.special);
  const ids=act.map(t=>t.tid);
  for(let i=ids.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[ids[i],ids[j]]=[ids[j],ids[i]];}
  act.forEach((t,i)=>t.tid=ids[i]); render();
};
init();
</script></body></html>"""

html = (html.replace("__TITLE__", title)
            .replace("__TILES__", json.dumps(tiles))
            .replace("__SYMBOLS__", json.dumps(SYMBOLS))
            .replace("__PALETTE__", json.dumps(PALETTE))
            .replace("__ART__", json.dumps(art))
            .replace("__HASART__", "true" if HAS_ART else "false"))

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)

print(f"SAVED {OUT}  ({os.path.getsize(OUT)} bytes)")
print(f"  {len(tiles)} tiles, {len(set(t['tid'] for t in tiles if not t['special']))} normal types"
      f"{f', {n_special} special' if n_special else ''}{f', {n_mystery} mystery' if n_mystery else ''}"
      f"{f', {n_cloud} cloud' if n_cloud else ''}")
print(f"  real art: {'YES' if HAS_ART else 'NO (fallback colours)'}"
      f"{' — tilebase + '+str(len(art['faces']))+' faces embedded' if HAS_ART else ''}")
print(f"  Open in any browser to play. Shareable single file.")
