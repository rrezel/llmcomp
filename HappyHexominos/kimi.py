# bot author: Kimi K2.6 (moonshotai/kimi-k2.6 via OpenRouter)
# bot author: GPT-4o

import os
import socket
import time
import random
from functools import lru_cache

# --- 1. Definitions of the 35 free hexominoes ---
RAW_SHAPES = [
    [(0,0),(0,1),(0,2),(0,3),(0,4),(0,5)], # 0  1x6
    [(0,0),(0,1),(0,2),(0,3),(0,4),(1,0)], # 1
    [(0,0),(0,1),(0,2),(0,3),(0,4),(1,1)], # 2
    [(0,0),(0,1),(0,2),(0,3),(0,4),(1,2)], # 3
    [(0,0),(0,1),(0,2),(0,3),(1,0),(1,1)], # 4
    [(0,0),(0,1),(0,2),(0,3),(1,0),(1,2)], # 5
    [(0,0),(0,1),(0,2),(0,3),(1,0),(1,3)], # 6
    [(0,0),(0,1),(0,2),(0,3),(1,0),(2,0)], # 7
    [(0,0),(0,1),(0,2),(0,3),(1,1),(1,2)], # 8
    [(0,0),(0,1),(0,2),(0,3),(1,1),(2,1)], # 9
    [(0,0),(0,1),(0,2),(0,3),(1,3),(1,4)], # 10
    [(0,0),(0,1),(0,2),(1,0),(1,1),(1,2)], # 11  2x3
    [(0,0),(0,1),(0,2),(1,0),(1,1),(2,0)], # 12
    [(0,0),(0,1),(0,2),(1,0),(1,1),(2,1)], # 13
    [(0,0),(0,1),(0,2),(1,0),(1,2),(1,3)], # 14
    [(0,0),(0,1),(0,2),(1,0),(1,2),(2,0)], # 15
    [(0,0),(0,1),(0,2),(1,1),(1,2),(1,3)], # 16
    [(0,0),(0,1),(0,2),(1,1),(2,0),(2,1)], # 17
    [(0,0),(0,1),(0,2),(1,1),(2,1),(3,1)], # 18
    [(0,0),(0,1),(0,2),(1,2),(1,3),(1,4)], # 19
    [(0,0),(0,1),(0,2),(1,2),(1,3),(2,2)], # 20
    [(0,0),(0,1),(0,2),(1,2),(1,3),(2,3)], # 21
    [(0,0),(0,1),(0,2),(1,2),(2,2),(2,3)], # 22
    [(0,0),(0,1),(1,0),(1,1),(1,2),(2,1)], # 23
    [(0,0),(0,1),(1,0),(1,1),(1,2),(2,2)], # 24
    [(0,0),(0,1),(1,1),(1,2),(1,3),(2,1)], # 25
    [(0,0),(0,1),(1,1),(1,2),(1,3),(2,2)], # 26
    [(0,0),(0,1),(1,1),(1,2),(1,3),(2,3)], # 27
    [(0,0),(0,1),(1,1),(1,2),(2,0),(2,1)], # 28
    [(0,0),(0,1),(1,1),(1,2),(2,1),(3,1)], # 29
    [(0,0),(0,1),(1,1),(1,2),(2,2),(2,3)], # 30
    [(0,0),(0,1),(1,1),(2,1),(2,2),(3,1)], # 31
    [(0,0),(0,1),(1,1),(2,1),(3,1),(3,2)], # 32
    [(0,1),(1,0),(1,1),(1,2),(1,3),(2,1)], # 33
    [(0,1),(1,0),(1,1),(1,2),(1,3),(2,2)], # 34
]

def normalize(cells):
    min_r = min(r for r, c in cells)
    min_c = min(c for r, c in cells)
    return frozenset((r - min_r, c - min_c) for r, c in cells)

def all_orientations(cells):
    res = set()
    cur = cells[:]
    for _ in range(4):
        cur = [(c, -r) for r, c in cur]
        res.add(normalize(cur))
    cur = [(r, -c) for r, c in cells]
    for _ in range(4):
        cur = [(c, -r) for r, c in cur]
        res.add(normalize(cur))
    return res

SHAPE_ORIENTATIONS = [list(all_orientations(cells)) for cells in RAW_SHAPES]

# --- 2. Placement caches ---
@lru_cache(maxsize=None)
def generate_all_placements(bw, bh):
    placements = []
    for s_idx, orientations in enumerate(SHAPE_ORIENTATIONS):
        for oc in orientations:
            max_r = max(r for r, c in oc)
            max_c = max(c for r, c in oc)
            if max_r >= bh or max_c >= bw:
                continue
            for base_r in range(bh - max_r):
                for base_c in range(bw - max_c):
                    mask = 0
                    for r, c in oc:
                        pos = (base_r + r) * bw + (base_c + c)
                        mask |= 1 << pos
                    placements.append((s_idx, mask))
    return placements

@lru_cache(maxsize=None)
def get_solver_data(bw, bh, allowed_tuple):
    all_placements = generate_all_placements(bw, bh)
    allowed = set(allowed_tuple)
    valid_masks = []
    valid_shapes = []
    for s, m in all_placements:
        if s in allowed:
            valid_masks.append(m)
            valid_shapes.append(s)
    N = bw * bh
    cell_to_placements = [[] for _ in range(N)]
    for idx, m in enumerate(valid_masks):
        temp = m
        while temp:
            lsb = temp & -temp
            cell = (lsb.bit_length() - 1)
            cell_to_placements[cell].append(idx)
            temp ^= lsb
    return valid_masks, valid_shapes, cell_to_placements

# --- 3. Exact-cover solver for a sub-rectangle ---
def solve_subproblem(bw, bh, allowed_shape_set, preplaced_mask, deadline):
    if time.time() > deadline:
        return None
    N = bw * bh
    full_mask = (1 << N) - 1
    if preplaced_mask == full_mask:
        return []

    valid_masks, valid_shapes, cell_to_placements = get_solver_data(
        bw, bh, tuple(sorted(allowed_shape_set))
    )
    if not valid_masks:
        return None

    target = full_mask & ~preplaced_mask

    sol = []

    def search(covered_mask):
        if covered_mask == full_mask:
            return True
        if time.time() > deadline:
            return False
        uncovered = target & ~covered_mask
        best_opts = None
        temp = uncovered
        while temp:
            lsb = temp & -temp
            cell = (lsb.bit_length() - 1)
            opts = []
            for pidx in cell_to_placements[cell]:
                if valid_masks[pidx] & covered_mask == 0:
                    opts.append(pidx)
            if not opts:
                return False
            if best_opts is None or len(opts) < len(best_opts):
                best_opts = opts
                if len(opts) == 1:
                    break
            temp ^= lsb

        random.shuffle(best_opts)
        for pidx in best_opts:
            sol.append(pidx)
            if search(covered_mask | valid_masks[pidx]):
                return True
            sol.pop()
        return False

    if search(preplaced_mask):
        return [(valid_shapes[i], valid_masks[i]) for i in sol]
    return None

def solve_block(bw, bh, allowed_shape_set, deadline):
    res = solve_subproblem(bw, bh, allowed_shape_set, 0, deadline)
    if res is None:
        return None
    local_grid = [[-1] * bw for _ in range(bh)]
    piece_shapes = []
    for pid, (sidx, mask) in enumerate(res):
        piece_shapes.append(sidx)
        temp = mask
        while temp:
            lsb = temp & -temp
            cell = (lsb.bit_length() - 1)
            r = cell // bw
            c = cell % bw
            local_grid[r][c] = pid
            temp ^= lsb
    return local_grid, piece_shapes

def fallback_block(bw, bh):
    res = solve_subproblem(bw, bh, {0, 11}, 0, time.time() + 1.0)
    if res is None:
        res = solve_subproblem(bw, bh, set(range(35)), 0, time.time() + 2.0)
    local_grid = [[-1] * bw for _ in range(bh)]
    piece_shapes = []
    for pid, (sidx, mask) in enumerate(res):
        piece_shapes.append(sidx)
        temp = mask
        while temp:
            lsb = temp & -temp
            cell = (lsb.bit_length() - 1)
            r = cell // bw
            c = cell % bw
            local_grid[r][c] = pid
            temp ^= lsb
    return local_grid, piece_shapes

# --- 4. Board partitioner ---
@lru_cache(maxsize=None)
def partition_wh(w, h):
    if w * h <= 48:
        return [(0, 0, w, h)]
    best = None
    best_score = 10 ** 9
    for x in range(1, w):
        if (x * h) % 6 != 0:
            continue
        left = partition_wh(x, h)
        right = partition_wh(w - x, h)
        right = [(rx + x, ry, rw, rh) for (rx, ry, rw, rh) in right]
        cand = left + right
        score = 0
        for rx, ry, rw, rh in cand:
            score += 1
            if rw == 1 or rh == 1:
                score += 100
            if rw == 2 and rh % 3 != 0:
                score += 5
            if rh == 2 and rw % 3 != 0:
                score += 5
        if score < best_score:
            best_score = score
            best = cand
    for y in range(1, h):
        if (w * y) % 6 != 0:
            continue
        top = partition_wh(w, y)
        bottom = partition_wh(w, h - y)
        bottom = [(rx, ry + y, rw, rh) for (rx, ry, rw, rh) in bottom]
        cand = top + bottom
        score = 0
        for rx, ry, rw, rh in cand:
            score += 1
            if rw == 1 or rh == 1:
                score += 100
            if rw == 2 and rh % 3 != 0:
                score += 5
            if rh == 2 and rw % 3 != 0:
                score += 5
        if score < best_score:
            best_score = score
            best = cand
    if best is not None:
        return best
    return [(0, 0, w, h)]

# --- 5. Main tournament loop ---
def main():
    botname = os.environ.get('BOTNAME', '').strip()
    if not botname:
        return
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock.sendall((botname + '\n').encode())
    infile = sock.makefile('r')

    while True:
        line = infile.readline()
        if not line:
            break
        line = line.strip()
        if line.startswith('ROUND'):
            parts = line.split()
            w = int(parts[2])
            h = int(parts[3])
            round_deadline = time.time() + 28.0

            blocks = partition_wh(w, h)
            block_offsets = []
            next_pid = 0
            for bx, by, bw, bh in blocks:
                k = bw * bh // 6
                block_offsets.append(next_pid)
                next_pid += k

            block_solutions = []
            global_shapes = set()
            grid = [[-1] * w for _ in range(h)]

            for bidx, (bx, by, bw, bh) in enumerate(blocks):
                dl = min(round_deadline, time.time() + 1.5)
                sol = solve_block(bw, bh, set(range(35)), dl)
                if sol is None:
                    sol = fallback_block(bw, bh)
                local_grid, piece_shapes = sol
                block_solutions.append((local_grid, piece_shapes))
                global_shapes.update(piece_shapes)
                off = block_offsets[bidx]
                for r in range(bh):
                    for c in range(bw):
                        if local_grid[r][c] != -1:
                            grid[by + r][bx + c] = off + local_grid[r][c]

            # Improvement: try to inject missing shapes
            missing = list(set(range(35)) - global_shapes)
            random.shuffle(missing)
            for sidx in missing:
                if time.time() > round_deadline - 1.5:
                    break
                placed = False
                b_order = list(range(len(blocks)))
                random.shuffle(b_order)
                for bidx in b_order:
                    bx, by, bw, bh = blocks[bidx]
                    allp = generate_all_placements(bw, bh)
                    cands = [m for s, m in allp if s == sidx]
                    random.shuffle(cands)
                    for mask in cands:
                        if time.time() > round_deadline - 1.0:
                            break
                        dl = time.time() + 0.4
                        sub = solve_subproblem(bw, bh, set(range(35)), mask, dl)
                        if sub is not None:
                            total = [(sidx, mask)] + sub
                            local_grid = [[-1] * bw for _ in range(bh)]
                            piece_shapes = []
                            for pid, (sh, m) in enumerate(total):
                                piece_shapes.append(sh)
                                temp = m
                                while temp:
                                    lsb = temp & -temp
                                    cell = (lsb.bit_length() - 1)
                                    r = cell // bw
                                    c = cell % bw
                                    local_grid[r][c] = pid
                                    temp ^= lsb
                            block_solutions[bidx] = (local_grid, piece_shapes)
                            off = block_offsets[bidx]
                            for r in range(bh):
                                for c in range(bw):
                                    if local_grid[r][c] != -1:
                                        grid[by + r][bx + c] = off + local_grid[r][c]
                            global_shapes.add(sidx)
                            placed = True
                            break
                    if placed:
                        break

            out_lines = []
            for r in range(h):
                row = ''
                for c in range(w):
                    row += f'[{grid[r][c]}]'
                out_lines.append(row)
            out_lines.append('END')
            for line_out in out_lines:
                sock.sendall((line_out + '\n').encode())

        elif line.startswith('END_ROUND'):
            pass
        elif line == 'TOURNAMENT_END':
            break
        elif line.startswith('OK') or line.startswith('INVALID'):
            pass

if __name__ == '__main__':
    main()
