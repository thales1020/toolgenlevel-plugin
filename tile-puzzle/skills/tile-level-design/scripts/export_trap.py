"""Export trap_L20_candidate.json to game-compatible stones format with metadata."""
import json, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
for _d in (os.path.join(SKILL_ROOT, 'engine'),
           'c:/Users/PC1150/Downloads/GD_Test'):
    if os.path.isfile(os.path.join(_d, 'tile_level_simulator.py')):
        sys.path.insert(0, _d)
        break

from tile_level_simulator import Board, Layer, Cell, DifficultyScorer, load_scoring_weights
from verify_smart_v3 import solve_v3
from solve_path import solve_with_path

# Candidate path + output dir as args (defaults are illustrative)
CAND = sys.argv[1] if len(sys.argv) > 1 else 'trap_L20_candidate.json'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.abspath(os.path.join('levels', 'trap_an_L20_s1.json'))

with open(CAND) as f:
    cand = json.load(f)

b = Board('L20_trap')
for ly in cand['layers']:
    L = Layer(ly['id'])
    for c in ly['cells']:
        cell = Cell(c['x'], c['y'], ly['id'])
        cell.tile_id = c['tile_id']
        L.cells.append(cell)
    b.layers.append(L)

# Double-verify
res_v3, depth, exp = solve_v3(b, max_expansions=100_000, verbose=False)
res_p, picks, elapsed, _ = solve_with_path(b, max_expansions=200_000)
assert res_v3 is True and res_p is True, 'NOT solvable'

w = load_scoring_weights()
sc = DifficultyScorer.compute_full_score(b, weights=w)

# Stones format
stones_layers = []
for ly in b.layers:
    stones = [{'i': c.tile_id, 'x': c.x, 'y': c.y} for c in ly.cells]
    stones_layers.append({'index': ly.id, 'stones': stones})

# Type distribution
all_tids = [c.tile_id for ly in b.layers for c in ly.cells]
type_dist = {}
for t in all_tids:
    type_dist[str(t)] = type_dist.get(str(t), 0) + 1

out = {
    'group': 1,
    'tiles': '',
    'layers': stones_layers,
    'stacks': [],
    'sl': 20,
    'metadata': {
        'layout': 'L20',
        'pattern': 'trap_an',
        'n_layers': len(b.layers),
        'n_types': len(set(all_tids)),
        'total_tiles': len(all_tids),
        'difficulty': round(sc['final_score'], 2),
        'tier': 'Hard',
        'score_components': {
            'layout': round(sc['layout'], 2),
            'inter_group': round(sc['inter_group'], 2),
            'intra_group': round(sc['intra_group'], 2),
            'cover100': round(sc['cover100'], 2),
            'pickable_diversity': round(sc['pickable_diversity'], 2),
        },
        'type_distribution': type_dist,
        'v3_solvable': True,
        'v3_depth': depth,
        'v3_expansions': exp,
        'greedy_fail_rate': cand['fail_rate'],
        'avg_cleared_greedy': cand['avg_cleared'],
        'seed': 1,
    },
}

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, separators=(',', ':'), ensure_ascii=False)

print(f'SAVED {OUT}')
print(f'Size: {os.path.getsize(OUT)} bytes')
print(f'Total cells: {len(all_tids)}')
print(f'Types: {len(set(all_tids))} -> {dict(sorted(type_dist.items(), key=lambda x: -x[1]))}')

# Print first 20 picks (display labels = tile_id+1)
labels = [tid + 1 for tid in [b.all_cells()[i].tile_id for i in picks[:20]]]
print(f'First 20 picks (UI labels): {labels}')
print(f'Full path length: {len(picks)}')
