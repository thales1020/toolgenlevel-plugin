"""Generate all 9 pattern levels in parallel, save + print board dicts for play."""
import sys, os, random, json, time, subprocess, multiprocessing
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))

SCRIPTS = [
    ("python find_l20_17.py 99", "l20_cc17_candidate.json", "P1 Trap An"),
    ("python find_hybrid_custom_fast.py 99 60 85", "hybrid_fast_s99.json", "P3 Hybrid Random"),
    ("python find_hybrid_priority_v2.py 99", "hybrid_priority_verified.json", "P4 Hybrid Priority"),
    ("python find_hybrid_cascade_L21.py 99", "cascade_L21_verified.json", "P5 Cascade L21"),
    ("python find_trap_70_90.py 99", "trap_70_90_candidate.json", "P6 90pct Fail"),
    ("python find_guided_trap_L21.py 99", "guided_trap_L21_s99.json", "P7 Guided Trap"),
    ("python find_clear50_trap.py 99 NewLayout_L74.json 30 60", "clear50_NewLayout_L74_s99.json", "P9 Clear 50pct"),
]

def gen_p2():
    """P2 Top Easy - inline, fastest"""
    from tile_level_simulator import TEEngine, DifficultyScorer, load_board_from_file, load_scoring_weights
    from verify_smart_v3 import solve_v3
    random.seed(99); weights = load_scoring_weights()
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sample_layouts/NewLayout_L20.json')
    for _ in range(30000):
        board = load_board_from_file(path)
        for c in board.all_cells(): c.tile_id = -1
        eng = TEEngine(); eng.validate = False; eng.color_count = random.choice([6,7,8])
        eng.top3_easy = True; eng.less_type = True
        if eng.color_count > 5: eng.style_mode = 7
        eng.generate(board)
        nt = len({c.tile_id for c in board.all_cells()})
        if not (5 <= nt <= 10): continue
        s = DifficultyScorer.compute_full_score(board, weights=weights)
        f = s['final_score']
        if not (25 <= f <= 55): continue
        r, _, _ = solve_v3(board, max_expansions=2000000, verbose=False)
        if r is not True: continue
        out = {'name': 'P2 Top Easy', 'layers': [{'id': li, 'cells': [{'x': c.x, 'y': c.y, 'tile_id': c.tile_id} for c in l.cells]} for li, l in enumerate(board.layers)], 'total_cells': board.total_cells(), 'score': f, 'n_types': nt}
        with open('_9_p2.json', 'w') as fp: json.dump(out, fp)
        return

def gen_p8():
    """P8 = find_80fail variant - inline"""
    from tile_level_simulator import TEEngine, DifficultyScorer, load_board_from_file, load_scoring_weights
    from verify_smart_v3 import solve_v3
    random.seed(99); weights = load_scoring_weights()
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sample_layouts/NewLayout_L20.json')
    TRAY = 7
    for _ in range(30000):
        board = load_board_from_file(path)
        for c in board.all_cells(): c.tile_id = -1
        eng = TEEngine(); eng.validate = False
        eng.color_count = random.choice([10,11,12,13])
        eng.hard_code = random.choice([0,1,2])
        eng.distance = random.choice([0,3,5])
        if eng.color_count > 6: eng.style_mode = 3; eng.extended = True
        elif eng.color_count > 5: eng.style_mode = 7
        eng.generate(board)
        cells = board.all_cells(); n = len(cells)
        tids = [c.tile_id for c in cells]; nt = len(set(tids))
        if not (8 <= nt <= 14): continue
        s = DifficultyScorer.compute_full_score(board, weights=weights)
        f = s['final_score']
        if not (40 <= f <= 70): continue
        r, _, _ = solve_v3(board, max_expansions=2000000, verbose=False)
        if r is not True: continue
        # Quick greedy
        bb = [0]*n
        for i in range(n):
            ci = cells[i]
            for j in range(n):
                if i == j: continue
                cj = cells[j]
                if cj.layer_idx > ci.layer_idx and abs(cj.x-ci.x)<1.0 and abs(cj.y-ci.y)<1.0:
                    bb[i] |= 1<<j
        fails = 0
        for _ in range(100):
            active = (1<<n)-1; tray = {}
            while True:
                if active == 0: break
                pk = []
                a = active
                while a:
                    low = a & -a; ii = low.bit_length()-1; a ^= low
                    if not (bb[ii] & active): pk.append(ii)
                if not pk: fails += 1; break
                if random.random()<0.1: ii = random.choice(pk)
                else:
                    tr = [k for k in pk if tray.get(tids[k],0)==2]
                    if tr: ii = random.choice(tr)
                    else:
                        pr = [k for k in pk if tray.get(tids[k],0)==1]
                        ii = random.choice(pr) if pr else random.choice(pk)
                tid = tids[ii]; active ^= 1<<ii
                tray[tid] = tray.get(tid,0)+1
                if tray[tid]>=3: tray[tid]-=3
                if tray[tid]==0 and tid in tray: del tray[tid]
                if sum(tray.values())>=TRAY and not any(v>=3 for v in tray.values()):
                    fails += 1; break
        if fails/100 < 0.80: continue
        out = {'name': 'P8 80pct Fail', 'layers': [{'id': li, 'cells': [{'x': c.x, 'y': c.y, 'tile_id': c.tile_id} for c in l.cells]} for li, l in enumerate(board.layers)], 'total_cells': board.total_cells(), 'score': f, 'n_types': nt, 'fail_rate': fails/100}
        with open('_9_p8.json', 'w') as fp: json.dump(out, fp)
        return

if __name__ == '__main__':
    t0 = time.time()

    # Launch external scripts
    procs = []
    for cmd, _, label in SCRIPTS:
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append((p, label))

    # Run P2 and P8 inline (fastest)
    gen_p2()
    gen_p8()

    # Wait for all
    for p, _ in procs:
        p.wait()

    elapsed = time.time() - t0

    # Collect results
    all_files = [
        ("l20_cc17_candidate.json", "P1 Trap An"),
        ("_9_p2.json", "P2 Top Easy"),
        ("hybrid_fast_s99.json", "P3 Hybrid Random"),
        ("hybrid_priority_verified.json", "P4 Hybrid Priority"),
        ("cascade_L21_verified.json", "P5 Cascade L21"),
        ("trap_70_90_candidate.json", "P6 90pct Fail"),
        ("guided_trap_L21_s99.json", "P7 Guided Trap"),
        ("_9_p8.json", "P8 80pct Fail"),
        ("clear50_NewLayout_L74_s99.json", "P9 Clear 50pct"),
    ]

    boards = []
    for fname, label in all_files:
        try:
            with open(fname) as f:
                d = json.load(f)
            b = {'name': label, 'layers': d['layers'], 'total_cells': d.get('total_cells', sum(len(l['cells']) for l in d['layers']))}
            boards.append(b)
            s = d.get('score', '?')
            if isinstance(s, dict): s = s.get('final_score', '?')
            if isinstance(s, float): s = f'{s:.1f}'
            nt = d.get('n_types', '?')
            fr = d.get('fail_rate', '?')
            if isinstance(fr, float): fr = f'{fr*100:.0f}%'
            print(f'  {label:22s} score={s:>5} types={nt} fail={fr}')
        except Exception as e:
            print(f'  {label:22s} ERROR: {e}')

    # Save all boards to single file for easy loading
    with open('all_9_boards.json', 'w') as f:
        json.dump(boards, f)

    print(f'\n=== {len(boards)}/9 levels in {elapsed:.1f}s ===')
    print(f'Boards saved to all_9_boards.json')
