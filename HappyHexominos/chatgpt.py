#!/usr/bin/env python3
# bot author: GPT-5.5 Thinking

import os
import re
import socket
import sys
import time
from functools import lru_cache

HOST = "localhost"
PORT = 7474

# Catalog from the prompt: 35 free hexominoes.
SHAPES = [
    [(0,0),(0,1),(0,2),(0,3),(0,4),(0,5)],
    [(0,0),(0,1),(0,2),(0,3),(0,4),(1,0)],
    [(0,0),(0,1),(0,2),(0,3),(0,4),(1,1)],
    [(0,0),(0,1),(0,2),(0,3),(0,4),(1,2)],
    [(0,0),(0,1),(0,2),(0,3),(1,0),(1,1)],
    [(0,0),(0,1),(0,2),(0,3),(1,0),(1,2)],
    [(0,0),(0,1),(0,2),(0,3),(1,0),(1,3)],
    [(0,0),(0,1),(0,2),(0,3),(1,0),(2,0)],
    [(0,0),(0,1),(0,2),(0,3),(1,1),(1,2)],
    [(0,0),(0,1),(0,2),(0,3),(1,1),(2,1)],
    [(0,0),(0,1),(0,2),(0,3),(1,3),(1,4)],
    [(0,0),(0,1),(0,2),(1,0),(1,1),(1,2)],
    [(0,0),(0,1),(0,2),(1,0),(1,1),(2,0)],
    [(0,0),(0,1),(0,2),(1,0),(1,1),(2,1)],
    [(0,0),(0,1),(0,2),(1,0),(1,2),(1,3)],
    [(0,0),(0,1),(0,2),(1,0),(1,2),(2,0)],
    [(0,0),(0,1),(0,2),(1,1),(1,2),(1,3)],
    [(0,0),(0,1),(0,2),(1,1),(2,0),(2,1)],
    [(0,0),(0,1),(0,2),(1,1),(2,1),(3,1)],
    [(0,0),(0,1),(0,2),(1,2),(1,3),(1,4)],
    [(0,0),(0,1),(0,2),(1,2),(1,3),(2,2)],
    [(0,0),(0,1),(0,2),(1,2),(1,3),(2,3)],
    [(0,0),(0,1),(0,2),(1,2),(2,2),(2,3)],
    [(0,0),(0,1),(1,0),(1,1),(1,2),(2,1)],
    [(0,0),(0,1),(1,0),(1,1),(1,2),(2,2)],
    [(0,0),(0,1),(1,1),(1,2),(1,3),(2,1)],
    [(0,0),(0,1),(1,1),(1,2),(1,3),(2,2)],
    [(0,0),(0,1),(1,1),(1,2),(1,3),(2,3)],
    [(0,0),(0,1),(1,1),(1,2),(2,0),(2,1)],
    [(0,0),(0,1),(1,1),(1,2),(2,1),(3,1)],
    [(0,0),(0,1),(1,1),(1,2),(2,2),(2,3)],
    [(0,0),(0,1),(1,1),(2,1),(2,2),(3,1)],
    [(0,0),(0,1),(1,1),(2,1),(3,1),(3,2)],
    [(0,1),(1,0),(1,1),(1,2),(1,3),(2,1)],
    [(0,1),(1,0),(1,1),(1,2),(1,3),(2,2)],
]


def normalize(cells):
    mr = min(r for r, c in cells)
    mc = min(c for r, c in cells)
    return tuple(sorted((r - mr, c - mc) for r, c in cells))


def all_orientations(cells):
    """All rotations/reflections, normalized."""
    out = set()
    for mode in range(8):
        transformed = []
        for r, c in cells:
            x, y = c, r
            if mode == 0:
                nx, ny = x, y
            elif mode == 1:
                nx, ny = x, -y
            elif mode == 2:
                nx, ny = -x, y
            elif mode == 3:
                nx, ny = -x, -y
            elif mode == 4:
                nx, ny = y, x
            elif mode == 5:
                nx, ny = y, -x
            elif mode == 6:
                nx, ny = -y, x
            else:
                nx, ny = -y, -x
            transformed.append((ny, nx))
        out.add(normalize(transformed))
    return tuple(sorted(out))


ORIENTATIONS = [all_orientations(s) for s in SHAPES]


@lru_cache(maxsize=None)
def placements_for_block(w, h):
    """Return placements and cell-to-placement index lists for a small block."""
    placements = []
    by_cell = [[] for _ in range(w * h)]

    for shape_id, orientations in enumerate(ORIENTATIONS):
        for ori in orientations:
            max_r = max(r for r, c in ori)
            max_c = max(c for r, c in ori)
            for br in range(h - max_r):
                for bc in range(w - max_c):
                    cells = tuple((br + r) * w + (bc + c) for r, c in ori)
                    idx = len(placements)
                    placements.append((shape_id, cells))
                    for cell in cells:
                        by_cell[cell].append(idx)

    return placements, by_cell


def solve_exact_block(w, h, already_used, deadline):
    """
    Small exact-cover solver. Used mainly for 6x6 chunks.
    Objective: maximize new distinct shapes, then total distinct shapes.
    """
    placements, by_cell = placements_for_block(w, h)
    n = w * h
    covered = [False] * n
    chosen = []
    shape_counts = {}
    best = None
    best_score = (-1, -1)

    def score_now():
        shapes = set(shape_counts)
        return (len(shapes - already_used), len(shapes))

    def add_shape(s):
        shape_counts[s] = shape_counts.get(s, 0) + 1

    def remove_shape(s):
        cnt = shape_counts[s] - 1
        if cnt:
            shape_counts[s] = cnt
        else:
            del shape_counts[s]

    def rec(empty_cells):
        nonlocal best, best_score

        if time.monotonic() >= deadline:
            return True

        if empty_cells == 0:
            sc = score_now()
            if sc > best_score:
                best_score = sc
                best = list(chosen)
            return False

        # Branch-and-bound: each remaining piece can add at most one new shape.
        remaining_pieces = empty_cells // 6
        if score_now()[0] + remaining_pieces < best_score[0]:
            return False

        target_cell = -1
        target_options = None

        for cell in range(n):
            if covered[cell]:
                continue
            opts = []
            for pi in by_cell[cell]:
                sid, cells = placements[pi]
                ok = True
                for cc in cells:
                    if covered[cc]:
                        ok = False
                        break
                if ok:
                    opts.append(pi)
            if not opts:
                return False
            if target_options is None or len(opts) < len(target_options):
                target_cell = cell
                target_options = opts
                if len(opts) == 1:
                    break

        def placement_key(pi):
            sid, cells = placements[pi]
            is_new_global = sid not in already_used
            is_new_local = sid not in shape_counts
            # Prefer shapes not seen in the tournament tiling yet,
            # then shapes not already inside this block.
            return (not is_new_global, not is_new_local, sid)

        target_options.sort(key=placement_key)

        for pi in target_options:
            sid, cells = placements[pi]

            for cc in cells:
                covered[cc] = True
            chosen.append(pi)
            add_shape(sid)

            stop = rec(empty_cells - 6)

            remove_shape(sid)
            chosen.pop()
            for cc in cells:
                covered[cc] = False

            if stop:
                return True

        return False

    rec(n)

    if best is None:
        return None

    return [(placements[pi][0], placements[pi][1]) for pi in best]


def put_cells(grid, x0, y0, local_w, cells, piece_id):
    for cell in cells:
        r = cell // local_w
        c = cell % local_w
        grid[y0 + r][x0 + c] = piece_id


def fill_baseline(grid, x0, y0, w, h, next_id):
    """
    Guaranteed rectangle tiler for any w*h divisible by 6.
    Uses shape #0 strips or shape #11 rectangles.
    """
    if w <= 0 or h <= 0:
        return next_id

    area = w * h
    if area % 6 != 0:
        raise RuntimeError("baseline called on non-multiple-of-6 area")

    # Horizontal 1x6 strips.
    if w % 6 == 0:
        for r in range(h):
            for c in range(0, w, 6):
                pid = next_id
                next_id += 1
                for dc in range(6):
                    grid[y0 + r][x0 + c + dc] = pid
        return next_id

    # Vertical 6x1 strips.
    if h % 6 == 0:
        for c in range(w):
            for r in range(0, h, 6):
                pid = next_id
                next_id += 1
                for dr in range(6):
                    grid[y0 + r + dr][x0 + c] = pid
        return next_id

    # 2 rows x 3 cols rectangles.
    if w % 3 == 0 and h % 2 == 0:
        for r in range(0, h, 2):
            for c in range(0, w, 3):
                pid = next_id
                next_id += 1
                for dr in range(2):
                    for dc in range(3):
                        grid[y0 + r + dr][x0 + c + dc] = pid
        return next_id

    # 3 rows x 2 cols rectangles.
    if w % 2 == 0 and h % 3 == 0:
        for r in range(0, h, 3):
            for c in range(0, w, 2):
                pid = next_id
                next_id += 1
                for dr in range(3):
                    for dc in range(2):
                        grid[y0 + r + dr][x0 + c + dc] = pid
        return next_id

    raise RuntimeError(f"no baseline tiling rule for {w}x{h}")


def make_tiling(w, h):
    """
    Hybrid strategy:
    - Use exact cover on as many 6x6 chunks as practical, seeking new shapes.
    - Fill all remaining area with a mathematically safe baseline tiling.
    """
    grid = [[None for _ in range(w)] for _ in range(h)]
    next_id = 0
    used_shapes = set()

    # Keep enough margin under the 30s server limit.
    hard_deadline = time.monotonic() + 24.5

    patch_w = (w // 6) * 6
    patch_h = (h // 6) * 6

    # Exact-cover 6x6 chunks. More chunks means more opportunity for inventory,
    # but after 35 shapes no further inventory gain is possible.
    if patch_w >= 6 and patch_h >= 6:
        max_chunks = min((patch_w // 6) * (patch_h // 6), 8)
        done = 0

        for by in range(0, patch_h, 6):
            for bx in range(0, patch_w, 6):
                if done >= max_chunks or len(used_shapes) >= 35:
                    break

                now = time.monotonic()
                if now >= hard_deadline:
                    break

                per_block_deadline = min(hard_deadline, now + 0.55)
                solution = solve_exact_block(6, 6, used_shapes, per_block_deadline)

                if solution is None:
                    next_id = fill_baseline(grid, bx, by, 6, 6, next_id)
                    used_shapes.add(11)
                else:
                    for sid, cells in solution:
                        put_cells(grid, bx, by, 6, cells, next_id)
                        next_id += 1
                        used_shapes.add(sid)

                done += 1

            if done >= max_chunks or len(used_shapes) >= 35 or time.monotonic() >= hard_deadline:
                break

    # Fill any unfilled 6x6 patch area with baseline, block by block.
    for by in range(0, patch_h, 6):
        for bx in range(0, patch_w, 6):
            if grid[by][bx] is None:
                next_id = fill_baseline(grid, bx, by, 6, 6, next_id)

    # Right strip beside the 6x6 patch zone.
    if patch_w < w and patch_h > 0:
        next_id = fill_baseline(grid, patch_w, 0, w - patch_w, patch_h, next_id)

    # Bottom strip across the full width.
    if patch_h < h:
        next_id = fill_baseline(grid, 0, patch_h, w, h - patch_h, next_id)

    # If no 6x6 patching happened, the whole board may still be empty.
    # This also covers skinny cases like 1x36, 2x18, 3x12, 4x9, 5x6.
    if grid[0][0] is None:
        next_id = fill_baseline(grid, 0, 0, w, h, next_id)

    # Safety check: no unfilled cells.
    for r in range(h):
        for c in range(w):
            if grid[r][c] is None:
                raise RuntimeError(f"unfilled cell {r},{c}")

    return grid


def grid_to_lines(grid):
    return ["".join(f"[{v}]" for v in row) for row in grid]


def read_line(sock_file):
    line = sock_file.readline()
    if line == "":
        return None
    return line.rstrip("\n")


def valid_botname(name):
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{1,32}", name))


def main():
    botname = os.environ.get("BOTNAME", "").rstrip("\n")
    if not botname or not valid_botname(botname):
        print("BOTNAME missing or invalid", file=sys.stderr)
        return 2

    with socket.create_connection((HOST, PORT)) as sock:
        rf = sock.makefile("r", encoding="ascii", newline="\n")

        sock.sendall((botname + "\n").encode("ascii"))

        while True:
            line = read_line(rf)
            if line is None:
                break

            if line == "TOURNAMENT_END":
                break

            if not line.startswith("ROUND "):
                # OK, INVALID, END_ROUND, or any informational line.
                print(line, file=sys.stderr)
                continue

            parts = line.split()
            if len(parts) != 4:
                print(f"unexpected ROUND line: {line}", file=sys.stderr)
                continue

            try:
                _round_no = int(parts[1])
                w = int(parts[2])
                h = int(parts[3])
            except ValueError:
                print(f"bad ROUND numbers: {line}", file=sys.stderr)
                continue

            try:
                grid = make_tiling(w, h)
                out_lines = grid_to_lines(grid)
            except Exception as e:
                # Last-resort safety: try baseline only.
                print(f"strategy error, falling back: {e}", file=sys.stderr)
                grid = [[None for _ in range(w)] for _ in range(h)]
                fill_baseline(grid, 0, 0, w, h, 0)
                out_lines = grid_to_lines(grid)

            payload = "\n".join(out_lines) + "\nEND\n"
            sock.sendall(payload.encode("ascii"))


if __name__ == "__main__":
    raise SystemExit(main())