# bot author: DeepSeek V4-Pro (deepseek/deepseek-v4-pro via OpenRouter)
# bot author: o1-pro
import os
import socket
import sys
import time

# 35 free hexomino canonical cells (row, col) as given in spec
SHAPES = [
    [(0,0),(0,1),(0,2),(0,3),(0,4),(0,5)],  # 0
    [(0,0),(0,1),(0,2),(0,3),(0,4),(1,0)],  # 1
    [(0,0),(0,1),(0,2),(0,3),(0,4),(1,1)],  # 2
    [(0,0),(0,1),(0,2),(0,3),(0,4),(1,2)],  # 3
    [(0,0),(0,1),(0,2),(0,3),(1,0),(1,1)],  # 4
    [(0,0),(0,1),(0,2),(0,3),(1,0),(1,2)],  # 5
    [(0,0),(0,1),(0,2),(0,3),(1,0),(1,3)],  # 6
    [(0,0),(0,1),(0,2),(0,3),(1,0),(2,0)],  # 7
    [(0,0),(0,1),(0,2),(0,3),(1,1),(1,2)],  # 8
    [(0,0),(0,1),(0,2),(0,3),(1,1),(2,1)],  # 9
    [(0,0),(0,1),(0,2),(0,3),(1,3),(1,4)],  # 10
    [(0,0),(0,1),(0,2),(1,0),(1,1),(1,2)],  # 11
    [(0,0),(0,1),(0,2),(1,0),(1,1),(2,0)],  # 12
    [(0,0),(0,1),(0,2),(1,0),(1,1),(2,1)],  # 13
    [(0,0),(0,1),(0,2),(1,0),(1,2),(1,3)],  # 14
    [(0,0),(0,1),(0,2),(1,0),(1,2),(2,0)],  # 15
    [(0,0),(0,1),(0,2),(1,1),(1,2),(1,3)],  # 16
    [(0,0),(0,1),(0,2),(1,1),(2,0),(2,1)],  # 17
    [(0,0),(0,1),(0,2),(1,1),(2,1),(3,1)],  # 18
    [(0,0),(0,1),(0,2),(1,2),(1,3),(1,4)],  # 19
    [(0,0),(0,1),(0,2),(1,2),(1,3),(2,2)],  # 20
    [(0,0),(0,1),(0,2),(1,2),(1,3),(2,3)],  # 21
    [(0,0),(0,1),(0,2),(1,2),(2,2),(2,3)],  # 22
    [(0,0),(0,1),(1,0),(1,1),(1,2),(2,1)],  # 23
    [(0,0),(0,1),(1,0),(1,1),(1,2),(2,2)],  # 24
    [(0,0),(0,1),(1,1),(1,2),(1,3),(2,1)],  # 25
    [(0,0),(0,1),(1,1),(1,2),(1,3),(2,2)],  # 26
    [(0,0),(0,1),(1,1),(1,2),(1,3),(2,3)],  # 27
    [(0,0),(0,1),(1,1),(1,2),(2,0),(2,1)],  # 28
    [(0,0),(0,1),(1,1),(1,2),(2,1),(3,1)],  # 29
    [(0,0),(0,1),(1,1),(1,2),(2,2),(2,3)],  # 30
    [(0,0),(0,1),(1,1),(2,1),(2,2),(3,1)],  # 31
    [(0,0),(0,1),(1,1),(2,1),(3,1),(3,2)],  # 32
    [(0,1),(1,0),(1,1),(1,2),(1,3),(2,1)],  # 33
    [(0,1),(1,0),(1,1),(1,2),(1,3),(2,2)],  # 34
]

def generate_orientations(cells):
    """Return all unique free-hexomino orientations (as lists of (r,c) offsets)."""
    transforms = [
        lambda r,c: (r, c),
        lambda r,c: (r, -c),
        lambda r,c: (-r, c),
        lambda r,c: (-r, -c),
        lambda r,c: (c, r),
        lambda r,c: (c, -r),
        lambda r,c: (-c, r),
        lambda r,c: (-c, -r),
    ]
    orients = set()
    for t in transforms:
        transformed = [t(r,c) for r,c in cells]
        min_r = min(r for r,c in transformed)
        min_c = min(c for r,c in transformed)
        norm = tuple(sorted((r - min_r, c - min_c) for r,c in transformed))
        orients.add(frozenset(norm))
    # convert to list of sorted lists (offsets relative to top-left)
    return [sorted(list(o)) for o in orients]

# precompute all orientations for each shape
ALL_ORIENTATIONS = [generate_orientations(cells) for cells in SHAPES]

class Timeout(Exception):
    pass

def select(X, Y, r):
    """Cover all columns of row r and remove conflicting rows."""
    cols = Y[r]
    removed = []
    for j in cols:
        # Remove all rows i that cover j (except j itself will be removed from X later)
        # iterate over a copy of X[j]
        for i in list(X[j]):
            if i == r:
                continue
            for k in Y[i]:
                if k != j:
                    X[k].discard(i)
        # remove column j from X
        removed.append((j, X.pop(j)))
    return removed

def deselect(X, Y, r, removed):
    """Undo select."""
    for j, row_set in reversed(removed):
        X[j] = row_set
        for i in row_set:
            for k in Y[i]:
                if k != j:
                    X[k].add(i)

def search(X, Y, solution, start_time, time_limit):
    if time.time() - start_time > time_limit:
        raise Timeout()
    if not X:
        return solution
    # MRV: choose column with fewest rows
    c = min(X.keys(), key=lambda c: len(X[c]))
    if not X[c]:
        return None
    # sort rows by degree (fewest columns first)
    rows = sorted(X[c], key=lambda r: len(Y[r]))
    for r in rows:
        solution.append(r)
        covered = select(X, Y, r)
        try:
            res = search(X, Y, solution, start_time, time_limit)
            if res is not None:
                return res
        except Timeout:
            raise
        finally:
            deselect(X, Y, r, covered)
            solution.pop()
    return None

def build_matrix(w, h, required_shapes):
    """Build exact-cover matrix for a rectangle w x h, optionally forcing some shapes."""
    cells_count = w * h
    required_map = {s: i for i, s in enumerate(required_shapes)}
    required_set = set(required_shapes)
    X = {col: set() for col in range(cells_count + len(required_shapes))}
    Y = {}
    row_info = []   # (shape_index, ori_idx, r0, c0)
    for s in range(35):
        for ori_idx, offsets in enumerate(ALL_ORIENTATIONS[s]):
            max_r = max(dr for dr, dc in offsets)
            max_c = max(dc for dr, dc in offsets)
            oh = max_r + 1
            ow = max_c + 1
            for r0 in range(h - oh + 1):
                for c0 in range(w - ow + 1):
                    cells = [(r0 + dr) * w + (c0 + dc) for dr, dc in offsets]
                    # optional row (covers only cells)
                    rid = len(row_info)
                    row_info.append((s, ori_idx, r0, c0))
                    Y[rid] = set(cells)
                    for col in cells:
                        X[col].add(rid)
                    # required row if shape is required
                    if s in required_set:
                        shape_col = cells_count + required_map[s]
                        rid2 = len(row_info)
                        row_info.append((s, ori_idx, r0, c0))
                        Y[rid2] = set(cells) | {shape_col}
                        for col in Y[rid2]:
                            X[col].add(rid2)
    return X, Y, row_info

def try_tiling(w, h, required_shapes, time_limit):
    cells_count = w * h
    X, Y, row_info = build_matrix(w, h, required_shapes)
    start = time.time()
    try:
        sol_rows = search(X, Y, [], start, time_limit)
    except Timeout:
        return None
    if sol_rows is None:
        return None
    # reconstruct grid
    grid = [[-1] * w for _ in range(h)]
    piece_id = 0
    shapes_used = set()
    for r in sol_rows:
        s, ori_idx, r0, c0 = row_info[r]
        offsets = ALL_ORIENTATIONS[s][ori_idx]
        for dr, dc in offsets:
            rr, cc = r0 + dr, c0 + dc
            # safety assert
            if grid[rr][cc] != -1:
                raise RuntimeError("overlapping placement in solution")
            grid[rr][cc] = piece_id
        shapes_used.add(s)
        piece_id += 1
    # double-check coverage
    for row in grid:
        for v in row:
            if v == -1:
                raise RuntimeError("incomplete tiling")
    return grid, len(shapes_used)

def find_best_tiling(w, h, max_time):
    start = time.time()
    # attempt 1: use all 35 shapes
    remaining = max_time - (time.time() - start)
    if remaining > 2:
        res = try_tiling(w, h, list(range(35)), min(remaining, 15))
        if res is not None:
            return res
    # attempt 2: any tiling (no required shapes)
    remaining = max_time - (time.time() - start)
    if remaining > 2:
        res = try_tiling(w, h, [], min(remaining, 10))
        if res is not None:
            return res
    # last resort: retry with longer time
    remaining = max_time - (time.time() - start)
    if remaining > 1:
        res = try_tiling(w, h, [], remaining)
        if res is not None:
            return res
    raise RuntimeError("failed to find any tiling within time")

def main():
    botname = os.environ.get('BOTNAME', '').strip()
    if not botname:
        print("BOTNAME not set", file=sys.stderr)
        sys.exit(1)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect(('localhost', 7474))
        sock_file = sock.makefile('r', buffering=1)
        # send BOTNAME
        sock.sendall((botname + '\n').encode())
        while True:
            line = sock_file.readline()
            if not line:
                break
            line = line.rstrip('\n')
            if line.startswith('ROUND'):
                parts = line.split()
                n = int(parts[1])
                w = int(parts[2])
                h = int(parts[3])
                grid, inventory = find_best_tiling(w, h, 28)   # 28s budget
                # send rows
                for row in grid:
                    out = ''.join(f'[{v}]' for v in row) + '\n'
                    sock.sendall(out.encode())
                sock.sendall(b'END\n')
                # read OK/INVALID, then END_ROUND
                resp = sock_file.readline().rstrip('\n')
                end_round = sock_file.readline().rstrip('\n')
                # continue to next ROUND
            elif line == 'TOURNAMENT_END':
                break

if __name__ == '__main__':
    main()
