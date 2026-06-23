"""Launch PlayWindow on a given level JSON (stones format)."""
import json, sys, os, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
# Engine lives in the skill bundle (engine/), legacy fallback to live project
for _d in (os.path.join(SKILL_ROOT, 'engine'),
           'c:/Users/PC1150/Downloads/GD_Test'):
    if os.path.isfile(os.path.join(_d, 'tile_level_simulator.py')):
        GAME_DIR = _d
        break
else:
    raise FileNotFoundError('tile_level_simulator.py not found in skill engine/ or GD_Test')

if len(sys.argv) > 1:
    LEVEL = sys.argv[1]
else:
    raise SystemExit("Usage: python open_any_level.py <path-to-level.json>")

with open(LEVEL, encoding='utf-8') as f:
    data = json.load(f)

# Convert stones -> internal board_dict layout
internal_layers = []
for ly in data['layers']:
    cells = [{'x': float(s['x']), 'y': float(s['y']), 'tile_id': s.get('i', 0)} for s in ly['stones']]
    internal_layers.append({'id': ly['index'], 'cells': cells})

board_name = os.path.basename(LEVEL).replace('.json', '')
board_dict = {'name': board_name, 'layers': internal_layers}

tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8')
tmp.write(f"""import sys, json, os
sys.path.insert(0, {repr(GAME_DIR)})
import tkinter as tk
from tile_level_simulator import PlayWindow, Board, Layer, Cell

data = {repr(board_dict)}

board = Board(data['name'])
for ld in data['layers']:
    layer = Layer(ld['id'])
    for cd in ld['cells']:
        c = Cell(cd['x'], cd['y'], ld['id'])
        c.tile_id = cd['tile_id']
        layer.cells.append(c)
    board.layers.append(layer)

root = tk.Tk()
root.withdraw()
pw = PlayWindow(root, board)
pw.protocol("WM_DELETE_WINDOW", lambda: (pw.destroy(), root.destroy()))
pw.update_idletasks()
sw = pw.winfo_screenwidth()
sh = pw.winfo_screenheight()
w, h = 750, 700
pw.geometry(f"{{w}}x{{h}}+{{(sw-w)//2}}+{{(sh-h)//2}}")
root.mainloop()
try:
    os.unlink(__file__)
except:
    pass
""")
tmp.close()

subprocess.Popen(['cmd', '/c', 'start', '', sys.executable, tmp.name], shell=False)
print(f'PlayWindow launched for: {board_name}')
print(f'Source: {LEVEL}')
print(f'Temp launcher: {tmp.name}')
