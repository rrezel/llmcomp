# bot author: Claude Opus 4.7
"""
HappyHexominos tournament bot.

Strategy:
- Catalog the 35 free hexominoes with all rotations/reflections.
- Place pieces by scanning for the topmost-leftmost empty cell ("scan-fill"),
  which guarantees coverage and avoids nondeterminism in placement order.
- Backtracking search that, at each step, tries placements from unused
  shapes first (random orientations/shape order), and falls back to used
  shapes if no unused placement leads to a complete tiling.
- Run multiple randomized attempts until time runs out, retain the best
  (highest-inventory) full tiling found. As a safety net, the bot first
  computes a guaranteed-valid baseline so it always has SOMETHING to
  submit even if the inventory search is starved for time.
"""

import os
import socket
import sys
import time
import random


# ----------------------------------------------------------------------------
# Catalog of the 35 free hexominoes (cells given as (row, col), top-left at 0,0)
# ----------------------------------------------------------------------------

CATALOG = [
    [(0,0),(0,1),(0,2),(0,3),(0,4),(0,5)],                  # 0  1x6
    [(0,0),(0,1),(0,2),(0,3),(0,4),(1,0)],                  # 1
    [(0,0),(0,1),(0,2),(0,3),(0,4),(1,1)],                  # 2
    [(0,0),(0,1),(0,2),(0,3),(0,4),(1,2)],                  # 3
    [(0,0),(0,1),(0,2),(0,3),(1,0),(1,1)],                  # 4
    [(0,0),(0,1),(0,2),(0,3),(1,0),(1,2)],                  # 5
    [(0,0),(0,1),(0,2),(0,3),(1,0),(1,3)],                  # 6
    [(0,0),(0,1),(0,2),(0,3),(1,0),(2,0)],                  # 7
    [(0,0),(0,1),(0,2),(0,3),(1,1),(1,2)],                  # 8
    [(0,0),(0,1),(0,2),(0,3),(1,1),(2,1)],                  # 9
    [(0,0),(0,1),(0,2),(0,3),(1,3),(1,4)],                  # 10
    [(0,0),(0,1),(0,2),(1,0),(1,1),(1,2)],                  # 11 2x3
    [(0,0),(0,1),(0,2),(1,0),(1,1),(2,0)],                  # 12
    [(0,0),(0,1),(0,2),(1,0),(1,1),(2,1)],                  # 13
    [(0,0),(0,1),(0,2),(1,0),(1,2),(1,3)],                  # 14
    [(0,0),(0,1),(0,2),(1,0),(1,2),(2,0)],                  # 15
    [(0,0),(0,1),(0,2),(1,1),(1,2),(1,3)],                  # 16
    [(0,0),(0,1),(0,2),(1,1),(2,0),(2,1)],                  # 17
    [(0,0),(0,1),(0,2),(1,1),(2,1),(3,1)],                  # 18
    [(0,0),(0,1),(0,2),(1,2),(1,3),(1,4)],                  # 19
    [(0,0),(0,1),(0,2),(1,2),(1,3),(2,2)],                  # 20
    [(0,0),(0,1),(0,2),(1,2),(1,3),(2,3)],                  # 21
    [(0,0),(0,1),(0,2),(1,2),(2,2),(2,3)],                  # 22
    [(0,0),(0,1),(1,0),(1,1),(1,2),(2,1)],                  # 23
    [(0,0),(0,1),(1,0),(1,1),(1,2),(2,2)],                  # 24
    [(0,0),(0,1),(1,1),(1,2),(1,3),(2,1)],                  # 25
    [(0,0),(0,1),(1,1),(1,2),(1,3),(2,2)],                  # 26
    [(0,0),(0,1),(1,1),(1,2),(1,3),(2,3)],                  # 27
    [(0,0),(0,1),(1,1),(1,2),(2,0),(2,1)],                  # 28
    [(0,0),(0,1),(1,1),(1,2),(2,1),(3,1)],                  # 29
    [(0,0),(0,1),(1,1),(1,2),(2,2),(2,3)],                  # 30
    [(0,0),(0,1),(1,1),(2,1),(2,2),(3,1)],                  # 31
    [(0,0),(0,1),(1,1),(2,1),(3,1),(3,2)],                  # 32
    [(0,1),(1,0),(1,1),(1,2),(1,3),(2,1)],                  # 33
    [(0,1),(1,0),(1,1),(1,2),(1,3),(2,2)],                  # 34
]


def _normalize(cells):
    minr = min(r for r, _ in cells)
    minc = min(c for _, c in cells)
    return tuple(sorted((r - minr, c - minc) for r, c in cells))


def _rotate(cells):
    return [(c, -r) for r, c in cells]


def _reflect(cells):
    return [(r, -c) for r, c in cells]


def _all_orientations(cells):
    seen = set()
    cur = list(cells)
    for _ in range(4):
        seen.add(_normalize(cur))
        seen.add(_normalize(_reflect(cur)))
        cur = _rotate(cur)
    return [list(o) for o in seen]


def _scan_anchor_normalize(cells):
    """
    Translate so that the FIRST cell in scan order (top-to-bottom,
    left-to-right) sits at (0, 0). All other cells then have either
    dr >= 0 with dc >= 0, or dr > 0 with any dc.
    """
    sorted_cells = sorted(cells)
    r0, c0 = sorted_cells[0]
    return tuple((r - r0, c - c0) for r, c in sorted_cells)


SHAPE_ORIENTS = []
for shape in CATALOG:
    seen = set()
    orients = []
    for o in _all_orientations(shape):
        t = _scan_anchor_normalize(o)
        if t not in seen:
            seen.add(t)
            orients.append(t)
    SHAPE_ORIENTS.append(orients)


_VALID_SHAPE_KEYS = set(
    _normalize(_all_orientations(s)[0])  # any normalized form is in the set
    for s in CATALOG
)


# ----------------------------------------------------------------------------
# Solver
# ----------------------------------------------------------------------------


def _first_empty(grid, w, h):
    for r in range(h):
        row = grid[r]
        for c in range(w):
            if row[c] == -1:
                return r, c
    return None


def _can_place(grid, w, h, orient, r0, c0):
    cells = []
    for dr, dc in orient:
        rr = r0 + dr
        cc = c0 + dc
        if rr < 0 or rr >= h or cc < 0 or cc >= w:
            return None
        if grid[rr][cc] != -1:
            return None
        cells.append((rr, cc))
    return cells


def _place(grid, cells, pid):
    for r, c in cells:
        grid[r][c] = pid


def _unplace(grid, cells):
    for r, c in cells:
        grid[r][c] = -1


def _has_dead_holes(grid, w, h):
    """
    Quick coverage feasibility check: scan flood-fill from each empty
    cell; if any connected empty region has size not divisible by 6,
    or smaller than 6, the board is unfillable.
    """
    visited = [[False] * w for _ in range(h)]
    for r in range(h):
        for c in range(w):
            if grid[r][c] != -1 or visited[r][c]:
                continue
            stack = [(r, c)]
            visited[r][c] = True
            size = 0
            while stack:
                rr, cc = stack.pop()
                size += 1
                if rr + 1 < h and not visited[rr + 1][cc] and grid[rr + 1][cc] == -1:
                    visited[rr + 1][cc] = True
                    stack.append((rr + 1, cc))
                if rr - 1 >= 0 and not visited[rr - 1][cc] and grid[rr - 1][cc] == -1:
                    visited[rr - 1][cc] = True
                    stack.append((rr - 1, cc))
                if cc + 1 < w and not visited[rr][cc + 1] and grid[rr][cc + 1] == -1:
                    visited[rr][cc + 1] = True
                    stack.append((rr, cc + 1))
                if cc - 1 >= 0 and not visited[rr][cc - 1] and grid[rr][cc - 1] == -1:
                    visited[rr][cc - 1] = True
                    stack.append((rr, cc - 1))
            if size < 6 or size % 6 != 0:
                return True
    return False


# Order shapes by how rectangle-friendly they are. Used as the fallback
# placement order when we need to place ANY shape.
_RECTANGLE_FRIENDLY_ORDER = [
    11,  # 2x3
    4,   # P-ish
    7,   # L
    8,   # T-bar
    9,   # T
    0,   # 1x6
    1, 2, 3, 5, 6, 10, 16, 14, 19,
    12, 13, 15, 17, 18, 20, 21, 22, 23, 24, 25,
    26, 27, 28, 29, 30, 31, 32, 33, 34,
]


def _solve_inventory(w, h, deadline, rng, start_used=None):
    """
    Backtracking solver that prefers placing unused shapes first.
    Records the BEST complete tiling (highest inventory) seen during the
    search. Returns (grid_or_None, inventory).
    """
    grid = [[-1] * w for _ in range(h)]
    used = set(start_used) if start_used else set()
    pid_counter = [0]
    nodes = [0]
    timed_out = [False]

    best_grid = [None]
    best_inv = [0]

    def step():
        if timed_out[0]:
            return False
        nodes[0] += 1
        if (nodes[0] & 1023) == 0:
            if time.monotonic() > deadline:
                timed_out[0] = True
                return False

        pos = _first_empty(grid, w, h)
        if pos is None:
            inv = len(used)
            if inv > best_inv[0]:
                best_inv[0] = inv
                best_grid[0] = [row[:] for row in grid]
            return True
        r, c = pos

        unused_shapes = [s for s in range(35) if s not in used]
        rng.shuffle(unused_shapes)
        used_shapes = [s for s in _RECTANGLE_FRIENDLY_ORDER if s in used]
        candidates = unused_shapes + used_shapes

        for si in candidates:
            for orient in SHAPE_ORIENTS[si]:
                cells = _can_place(grid, w, h, orient, r, c)
                if cells is None:
                    continue
                pid = pid_counter[0]
                pid_counter[0] += 1
                _place(grid, cells, pid)
                added = si not in used
                if added:
                    used.add(si)
                if not _has_dead_holes(grid, w, h):
                    if step():
                        if added:
                            used.discard(si)
                        _unplace(grid, cells)
                        pid_counter[0] -= 1
                        return True
                if added:
                    used.discard(si)
                _unplace(grid, cells)
                pid_counter[0] -= 1
                if timed_out[0]:
                    return False
        return False

    step()
    return best_grid[0], best_inv[0]


def _baseline_tile(w, h, deadline):
    """Find SOME valid tiling, fast. Deterministic backtracker."""
    grid = [[-1] * w for _ in range(h)]
    pid_counter = [0]
    nodes = [0]
    timed_out = [False]

    def step():
        if timed_out[0]:
            return False
        nodes[0] += 1
        if (nodes[0] & 1023) == 0:
            if time.monotonic() > deadline:
                timed_out[0] = True
                return False

        pos = _first_empty(grid, w, h)
        if pos is None:
            return True
        r, c = pos
        for si in _RECTANGLE_FRIENDLY_ORDER:
            for orient in SHAPE_ORIENTS[si]:
                cells = _can_place(grid, w, h, orient, r, c)
                if cells is None:
                    continue
                pid = pid_counter[0]
                pid_counter[0] += 1
                _place(grid, cells, pid)
                if not _has_dead_holes(grid, w, h):
                    if step():
                        return True
                _unplace(grid, cells)
                pid_counter[0] -= 1
                if timed_out[0]:
                    return False
        return False

    if step():
        return grid
    return None


def _canonical_shape(cells):
    forms = []
    cur = list(cells)
    for _ in range(4):
        forms.append(_normalize(cur))
        forms.append(_normalize(_reflect(cur)))
        cur = _rotate(cur)
    return min(forms)


def _count_inventory(grid):
    h = len(grid)
    w = len(grid[0])
    by_pid = {}
    for r in range(h):
        for c in range(w):
            by_pid.setdefault(grid[r][c], []).append((r, c))
    seen = set()
    for cells in by_pid.values():
        seen.add(_canonical_shape(cells))
    return len(seen)


def solve(w, h, time_budget):
    start = time.monotonic()
    deadline = start + time_budget
    rng = random.Random(0xA1CC ^ (w * 1000 + h))

    best_grid = None
    best_inv = 0

    # Phase 1: get any valid tiling fast (safety net).
    safety_deadline = min(start + max(1.5, time_budget * 0.1), deadline - 0.5)
    g = _baseline_tile(w, h, safety_deadline)
    if g is not None:
        best_grid = g
        best_inv = _count_inventory(g)

    # Phase 2: repeatedly run inventory-maximizing search until time expires.
    while True:
        now = time.monotonic()
        remaining = deadline - now - 0.5
        if remaining < 1.0:
            break
        per_budget = max(0.8, remaining * 0.4)
        attempt_deadline = min(now + per_budget, deadline - 0.5)
        g, inv = _solve_inventory(w, h, attempt_deadline, rng)
        if g is not None and inv > best_inv:
            best_grid = g
            best_inv = inv

    return best_grid, best_inv


# ----------------------------------------------------------------------------
# Wire format
# ----------------------------------------------------------------------------


def _format_grid(grid):
    parts = []
    for row in grid:
        parts.append("".join(f"[{pid}]" for pid in row))
    parts.append("END")
    return "\n".join(parts) + "\n"


# ----------------------------------------------------------------------------
# Network I/O
# ----------------------------------------------------------------------------


class _LineReader:
    def __init__(self, sock):
        self.sock = sock
        self.buf = b""

    def readline(self):
        while b"\n" not in self.buf:
            chunk = self.sock.recv(8192)
            if not chunk:
                return None
            self.buf += chunk
        line, _, rest = self.buf.partition(b"\n")
        self.buf = rest
        return line.decode("ascii", errors="replace")


def main():
    botname = os.environ.get("BOTNAME", "")
    botname = botname.rstrip("\n")
    if not botname:
        sys.stderr.write("BOTNAME env var missing or empty\n")
        sys.exit(1)

    sock = socket.create_connection(("localhost", 7474))
    sock.sendall((botname + "\n").encode("ascii"))

    reader = _LineReader(sock)

    while True:
        line = reader.readline()
        if line is None:
            return
        line = line.rstrip("\r")
        if not line:
            continue

        if line.startswith("ROUND "):
            parts = line.split()
            try:
                w = int(parts[2])
                h = int(parts[3])
            except (IndexError, ValueError):
                continue

            # Reserve a transmission/safety margin: spec says 30 s for the
            # full round-trip (compute + transmit). 27 s of compute leaves
            # ~3 s for sending.
            grid, _inv = solve(w, h, 27.0)
            if grid is None:
                grid = [[0] * w for _ in range(h)]
            payload = _format_grid(grid)
            sock.sendall(payload.encode("ascii"))

        elif line.startswith("OK ") or line.startswith("INVALID "):
            pass
        elif line.startswith("END_ROUND"):
            pass
        elif line.startswith("TOURNAMENT_END"):
            try:
                sock.close()
            except Exception:
                pass
            return
        else:
            pass


if __name__ == "__main__":
    main()