# bot author: Grok (xAI) - greedy max-inventory with safe fallback to guaranteed inventory-1 tiling
import os
import socket
import sys

BASE_SHAPES = [
    [(0,0),(0,1),(0,2),(0,3),(0,4),(0,5)], # 0
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
    [(0,0),(0,1),(0,2),(1,0),(1,1),(1,2)], # 11
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

def get_orients(base_cells):
    """Return all unique orientations (rotations + reflections) as lists of (dr, dc)."""
    configs = set()

    def normalize(cs):
        min_r = min(r for r, c in cs)
        min_c = min(c for r, c in cs)
        return tuple(sorted((r - min_r, c - min_c) for r, c in cs))

    cs = base_cells
    for _ in range(4):
        # original
        configs.add(normalize(cs))
        # vertical reflection
        cs_ref = [(r, -c) for r, c in cs]
        configs.add(normalize(cs_ref))
        # rotate 90° CW
        cs = [(c, -r) for r, c in cs]
    return [list(t) for t in configs]

# Precompute orients once (optional optimisation)
ORIENTS = [get_orients(shape) for shape in BASE_SHAPES]

def create_easy_tiling(w, h):
    """Guaranteed valid tiling (inventory 1) using shape #0 or #11."""
    grid = [[-1] * w for _ in range(h)]
    pid = 0
    if w % 6 == 0:
        for r in range(h):
            for c in range(0, w, 6):
                for i in range(6):
                    grid[r][c + i] = pid
                pid += 1
    elif h % 6 == 0:
        for c in range(w):
            for r in range(0, h, 6):
                for i in range(6):
                    grid[r + i][c] = pid
                pid += 1
    elif w % 2 == 0 and h % 3 == 0:
        for r in range(0, h, 3):
            for c in range(0, w, 2):
                for dr in range(3):
                    for dc in range(2):
                        grid[r + dr][c + dc] = pid
                pid += 1
    else:
        for r in range(0, h, 2):
            for c in range(0, w, 3):
                for dr in range(2):
                    for dc in range(3):
                        grid[r + dr][c + dc] = pid
                pid += 1
    return grid

def build_tiling(w, h):
    """High-inventory tiling: place as many distinct shapes as possible, then fill remainder.
    Falls back to easy tiling if remainder cannot be filled."""
    total_cells = w * h
    if total_cells % 6 != 0 or total_cells < 36:
        return create_easy_tiling(w, h)

    grid = [[-1] * w for _ in range(h)]
    next_pid = 0
    used = set()

    # 1. Greedily place one instance of each distinct shape (row-major search)
    max_possible = total_cells // 6
    for s_idx in range(35):
        if len(used) >= max_possible:
            break
        placed = False
        for orient in ORIENTS[s_idx]:
            for r in range(h):
                for c in range(w):
                    positions = []
                    can_place = True
                    for dr, dc in orient:
                        nr, nc = r + dr, c + dc
                        if not (0 <= nr < h and 0 <= nc < w) or grid[nr][nc] != -1:
                            can_place = False
                            break
                        positions.append((nr, nc))
                    if can_place:
                        for pr, pc in positions:
                            grid[pr][pc] = next_pid
                        next_pid += 1
                        used.add(s_idx)
                        placed = True
                        break
                if placed:
                    break
            if placed:
                break

    # 2. Determine default filler shape (same logic as easy tiling)
    if w % 6 == 0 or h % 6 == 0:
        filler_idx = 0
    else:
        filler_idx = 11
    filler_orients = ORIENTS[filler_idx]

    # 3. Greedily fill any remaining cells with the default shape
    while True:
        remaining = sum(row.count(-1) for row in grid)
        if remaining == 0:
            break
        if remaining % 6 != 0:
            break  # safety - should never happen
        placed = False
        for orient in filler_orients:
            for r in range(h):
                for c in range(w):
                    positions = []
                    can_place = True
                    for dr, dc in orient:
                        nr, nc = r + dr, c + dc
                        if not (0 <= nr < h and 0 <= nc < w) or grid[nr][nc] != -1:
                            can_place = False
                            break
                        positions.append((nr, nc))
                    if can_place:
                        for pr, pc in positions:
                            grid[pr][pc] = next_pid
                        next_pid += 1
                        placed = True
                        break
                if placed:
                    break
            if placed:
                break
        if not placed:
            # Failed to cover remainder → fallback to guaranteed tiling
            return create_easy_tiling(w, h)

    return grid

def main():
    botname = os.environ.get('BOTNAME', '').strip()
    if not botname:
        sys.exit(1)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 7474))
    s.sendall((botname + '\n').encode('ascii'))

    f = s.makefile('r')

    while True:
        line = f.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue

        if line.startswith('ROUND '):
            parts = line.split()
            w = int(parts[2])
            h = int(parts[3])
            grid = build_tiling(w, h)
            for r in range(h):
                row_str = ''.join(f'[{grid[r][c]}]' for c in range(w))
                s.sendall((row_str + '\n').encode('ascii'))
            s.sendall(b'END\n')
        elif line == 'TOURNAMENT_END':
            break
        # Ignore OK/INVALID/END_ROUND

    f.close()
    s.close()

if __name__ == "__main__":
    main()