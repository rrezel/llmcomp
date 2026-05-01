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
N = 24
MOVE_RE = re.compile(r"^MOVE [0-3],[0-5](( -> [0-3],[0-5]){1,12})$")

WIN_SCORE = 1_000_000
INF = 10**9

def idx(r, i):
    return r * 6 + (i % 6)

def rc(p):
    return divmod(p, 6)

NEIGH = [[] for _ in range(N)]
JUMPS = [[] for _ in range(N)]  # from -> [(landing, middle), ...]

for r in range(4):
    for i in range(6):
        p = idx(r, i)

        NEIGH[p].append(idx(r, i + 1))
        NEIGH[p].append(idx(r, i - 1))

        if r > 0:
            NEIGH[p].append(idx(r - 1, i))
        if r < 3:
            NEIGH[p].append(idx(r + 1, i))

        JUMPS[p].append((idx(r, i + 2), idx(r, i + 1)))
        JUMPS[p].append((idx(r, i - 2), idx(r, i - 1)))

        if r + 2 <= 3:
            JUMPS[p].append((idx(r + 2, i), idx(r + 1, i)))
        if r - 2 >= 0:
            JUMPS[p].append((idx(r - 2, i), idx(r - 1, i)))

POS_WEIGHT = [
    8, 8, 8, 8, 8, 8,
    6, 6, 6, 6, 6, 6,
    2, 2, 2, 2, 2, 2,
    0, 0, 0, 0, 0, 0,
]

START_BOARD = tuple(". . . . . . . . . . . . A B A B A B A B A B A B".split())

def other(c):
    return "B" if c == "A" else "A"

class Timeout(Exception):
    pass

class Move:
    __slots__ = ("path", "captures")

    def __init__(self, path, captures):
        self.path = tuple(path)
        self.captures = captures

    def line(self):
        coords = []
        for p in self.path:
            r, i = rc(p)
            coords.append(f"{r},{i}")
        return "MOVE " + " -> ".join(coords)

def parse_board(line):
    parts = line.split()
    if len(parts) == 25 and parts[0] == "BOARD":
        return tuple(parts[1:])
    return START_BOARD

def parse_move_line(line):
    if line.startswith("OPP "):
        line = line[4:]
    rest = line[5:]
    pts = []
    for token in rest.split(" -> "):
        r_s, i_s = token.split(",")
        pts.append(idx(int(r_s), int(i_s)))
    return pts

def is_jump_segment(a, b):
    ar, ai = rc(a)
    br, bi = rc(b)

    if ar == br and ((bi - ai) % 6 == 2):
        return idx(ar, ai + 1)
    if ar == br and ((ai - bi) % 6 == 2):
        return idx(ar, ai - 1)
    if ai == bi and abs(ar - br) == 2:
        return idx((ar + br) // 2, ai)

    return None

def can_capture_from(board, p, color):
    enemy = other(color)
    for landing, mid in JUMPS[p]:
        if board[mid] == enemy and board[landing] == ".":
            return True
    return False

def gen_capture_chains_from(board, color, start):
    enemy = other(color)
    results = []

    def rec(b, cur, path, caps, visited_landings):
        found = False

        for landing, mid in JUMPS[cur]:
            if b[mid] == enemy and b[landing] == ".":
                if landing != start and landing in visited_landings:
                    continue

                found = True
                nb = list(b)
                nb[cur] = "."
                nb[mid] = "."
                nb[landing] = color

                rec(
                    tuple(nb),
                    landing,
                    path + [landing],
                    caps + 1,
                    visited_landings | ({landing} if landing != start else set()),
                )

        if not found and caps > 0:
            results.append(Move(path, caps))

    rec(board, start, [start], 0, set())
    return results

@lru_cache(maxsize=200000)
def legal_moves_cached(board, color):
    board = tuple(board)

    captures = []
    for p, v in enumerate(board):
        if v == color:
            captures.extend(gen_capture_chains_from(board, color, p))

    if captures:
        return tuple(captures)

    slides = []
    for p, v in enumerate(board):
        if v == color:
            for q in NEIGH[p]:
                if board[q] == ".":
                    slides.append(Move((p, q), 0))

    return tuple(slides)

def legal_moves(board, color):
    return list(legal_moves_cached(tuple(board), color))

def apply_move(board, color, move):
    b = list(board)
    path = move.path if isinstance(move, Move) else tuple(move)

    start = path[0]
    b[start] = "."

    captures = 0
    cur = start

    for nxt in path[1:]:
        mid = is_jump_segment(cur, nxt)
        if mid is not None:
            b[mid] = "."
            captures += 1
        cur = nxt

    b[path[-1]] = color
    return tuple(b), captures

def count_pieces(board, color):
    return sum(1 for x in board if x == color)

def immediate_capture_count(board, color):
    n = 0
    for p, v in enumerate(board):
        if v == color:
            for landing, mid in JUMPS[p]:
                if board[mid] == other(color) and board[landing] == ".":
                    n += 1
    return n

def static_eval(board, me):
    opp = other(me)

    my_count = count_pieces(board, me)
    op_count = count_pieces(board, opp)

    if op_count == 0:
        return WIN_SCORE
    if my_count == 0:
        return -WIN_SCORE

    my_moves = len(legal_moves(board, me))
    op_moves = len(legal_moves(board, opp))

    if op_moves == 0:
        return WIN_SCORE - 1000
    if my_moves == 0:
        return -WIN_SCORE + 1000

    material = 1200 * (my_count - op_count)
    mobility = 10 * (my_moves - op_moves)

    position = 0
    for p, v in enumerate(board):
        if v == me:
            position += POS_WEIGHT[p]
        elif v == opp:
            position -= POS_WEIGHT[p]

    threats = 65 * (
        immediate_capture_count(board, me)
        - immediate_capture_count(board, opp)
    )

    my_spokes = len({rc(p)[1] for p, v in enumerate(board) if v == me})
    op_spokes = len({rc(p)[1] for p, v in enumerate(board) if v == opp})
    spread = 8 * (my_spokes - op_spokes)

    return material + mobility + position + threats + spread

def terminal_score(board, side, me, ply):
    if count_pieces(board, me) == 0:
        return -WIN_SCORE + ply
    if count_pieces(board, other(me)) == 0:
        return WIN_SCORE - ply

    moves = legal_moves(board, side)

    if not moves:
        return (-WIN_SCORE + ply) if side == me else (WIN_SCORE - ply)

    return None

def order_moves(board, side, moves, me):
    def key(m):
        nb, _ = apply_move(board, side, m)
        val = static_eval(nb, me)
        return (m.captures, val if side == me else -val)

    return sorted(moves, key=key, reverse=True)

def alphabeta(board, side, depth, alpha, beta, me, deadline, ply=0):
    if time.perf_counter() > deadline:
        raise Timeout

    ts = terminal_score(board, side, me, ply)
    if ts is not None:
        return ts

    if depth <= 0:
        return static_eval(board, me)

    moves = order_moves(board, side, legal_moves(board, side), me)

    if side == me:
        best = -INF
        for m in moves:
            nb, _ = apply_move(board, side, m)
            score = alphabeta(
                nb, other(side), depth - 1, alpha, beta, me, deadline, ply + 1
            )
            best = max(best, score)
            alpha = max(alpha, best)
            if alpha >= beta:
                break
        return best

    best = INF
    for m in moves:
        nb, _ = apply_move(board, side, m)
        score = alphabeta(
            nb, other(side), depth - 1, alpha, beta, me, deadline, ply + 1
        )
        best = min(best, score)
        beta = min(beta, best)
        if alpha >= beta:
            break

    return best

def choose_move(board, color, game_start_time):
    moves = legal_moves(board, color)

    if not moves:
        return None

    if len(moves) == 1:
        return moves[0]

    elapsed = time.perf_counter() - game_start_time
    remaining = max(0.05, 29.6 - elapsed)

    per_move = min(1.20, max(0.06, remaining / 16.0))

    if remaining < 3:
        per_move = min(per_move, 0.12)

    deadline = time.perf_counter() + per_move

    ordered = order_moves(board, color, moves, color)
    best = ordered[0]
    best_score = -INF

    max_depth = 9
    depth = 1

    try:
        while depth <= max_depth:
            current_best = best
            current_score = -INF
            alpha = -INF
            beta = INF

            for m in ordered:
                if time.perf_counter() > deadline:
                    raise Timeout

                nb, _ = apply_move(board, color, m)
                score = alphabeta(
                    nb, other(color), depth - 1, alpha, beta, color, deadline, 1
                )

                if score > current_score:
                    current_score = score
                    current_best = m

                alpha = max(alpha, score)

            best = current_best
            best_score = current_score
            ordered = [best] + [m for m in ordered if m is not best]

            if best_score > WIN_SCORE // 2:
                break

            depth += 1

    except Timeout:
        pass

    return best

def validate_botname(name):
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{1,32}", name))

def main():
    if "BOTNAME" not in os.environ:
        print("BOTNAME environment variable is required", file=sys.stderr)
        sys.exit(2)

    botname = os.environ["BOTNAME"].rstrip("\n")

    if not validate_botname(botname):
        print("Invalid BOTNAME; must match [A-Za-z0-9_-]{1,32}", file=sys.stderr)
        sys.exit(2)

    board = START_BOARD
    color = None
    pending_move = None
    game_start_time = time.perf_counter()

    with socket.create_connection((HOST, PORT)) as sock:
        sock.sendall((botname + "\n").encode("ascii"))
        f = sock.makefile("r", encoding="ascii", newline="\n")

        for raw in f:
            line = raw.rstrip("\n")

            if not line:
                continue

            if line.startswith("MATCH "):
                continue

            if line.startswith("GAME "):
                parts = line.split()
                color = parts[2]
                pending_move = None
                game_start_time = time.perf_counter()
                continue

            if line.startswith("BOARD "):
                board = parse_board(line)
                legal_moves_cached.cache_clear()
                continue

            if line == "TURN":
                mv = choose_move(board, color, game_start_time)

                if mv is None:
                    fallback = "MOVE 0,0 -> 0,1"
                    sock.sendall((fallback + "\n").encode("ascii"))
                    pending_move = None
                else:
                    out = mv.line()
                    sock.sendall((out + "\n").encode("ascii"))
                    pending_move = mv

                continue

            if line.startswith("OK "):
                if pending_move is not None:
                    board, _ = apply_move(board, color, pending_move)
                    legal_moves_cached.cache_clear()
                    pending_move = None
                continue

            if line.startswith("OPP MOVE "):
                pts = parse_move_line(line[4:])
                board, _ = apply_move(board, other(color), Move(pts, 0))
                legal_moves_cached.cache_clear()
                continue

            if line.startswith("DQ "):
                pending_move = None
                continue

            if line.startswith("GAME_END "):
                pending_move = None
                continue

            if line.startswith("MATCH_END "):
                continue

            if line == "TOURNAMENT_END":
                break

if __name__ == "__main__":
    main()