#!/usr/bin/env python3
# bot author: Claude Opus 4.7
"""
HexQuerQues tournament bot.

Board: 4 concentric hexagonal rings (r=0..3) x 6 vertices (i=0..5) = 24 cells.
- Same-ring neighbors: (r,i) <-> (r,(i+/-1)%6)
- Radial neighbors: (r,i) <-> (r+/-1,i)  [if on board]
- Same-ring jump: (r,i) over (r,(i+/-1)%6) to (r,(i+/-2)%6)
- Radial jump: (r,i) over (r+/-1,i) to (r+/-2,i) [requires r+/-2 in 0..3]

Strategy: Alpha-beta minimax with iterative deepening and chess-clock time
management. Forced captures are required by rules, so branching is often small.
"""

import os
import socket
import sys
import time
import re

# ---------- Board encoding ----------
# 24 cells indexed by idx = r*6 + i.
# Cell values: 0 empty, 1 player A, 2 player B.
EMPTY = 0
A = 1
B = 2

def idx(r, i):
    return r * 6 + i

def rc(k):
    return divmod(k, 6)

def opp(p):
    return 3 - p  # 1<->2

# Precompute neighbor lists (line-adjacency) and jump triples (jumper, jumped, landing).
NEIGHBORS = [[] for _ in range(24)]
# JUMPS[k] = list of (jumped_idx, landing_idx) reachable from k by one jump segment.
JUMPS = [[] for _ in range(24)]

for r in range(4):
    for i in range(6):
        k = idx(r, i)
        # same-ring neighbors
        NEIGHBORS[k].append(idx(r, (i + 1) % 6))
        NEIGHBORS[k].append(idx(r, (i - 1) % 6))
        # radial neighbors
        if r - 1 >= 0:
            NEIGHBORS[k].append(idx(r - 1, i))
        if r + 1 <= 3:
            NEIGHBORS[k].append(idx(r + 1, i))
        # same-ring jumps
        JUMPS[k].append((idx(r, (i + 1) % 6), idx(r, (i + 2) % 6)))
        JUMPS[k].append((idx(r, (i - 1) % 6), idx(r, (i - 2) % 6)))
        # radial jumps
        if r + 2 <= 3:
            JUMPS[k].append((idx(r + 1, i), idx(r + 2, i)))
        if r - 2 >= 0:
            JUMPS[k].append((idx(r - 1, i), idx(r - 2, i)))


def initial_board():
    board = [EMPTY] * 24
    # A on (3,0),(3,2),(3,4),(2,0),(2,2),(2,4)
    # B on (3,1),(3,3),(3,5),(2,1),(2,3),(2,5)
    for i in range(6):
        if i % 2 == 0:
            board[idx(2, i)] = A
            board[idx(3, i)] = A
        else:
            board[idx(2, i)] = B
            board[idx(3, i)] = B
    return board


def parse_board(tokens):
    """Tokens are the 24 cell strings 'A','B','.'"""
    b = [EMPTY] * 24
    for k, t in enumerate(tokens):
        if t == 'A':
            b[k] = A
        elif t == 'B':
            b[k] = B
        else:
            b[k] = EMPTY
    return b


# ---------- Move generation ----------
# A move is represented as a list of cell indices: [start, step1, step2, ...]
# Slide: length 2, distance == 1 line-neighbor.
# Capture: length >= 2, each segment is a jump.

def piece_can_capture(board, player, k):
    """Quick check: can the piece at k capture something right now?"""
    enemy = opp(player)
    for jumped, landing in JUMPS[k]:
        if board[jumped] == enemy and board[landing] == EMPTY:
            return True
    return False


def any_capture_available(board, player):
    for k in range(24):
        if board[k] == player:
            if piece_can_capture(board, player, k):
                return True
    return False


def gen_chains_from(board, player, start, current, visited_landings):
    """
    Recursively generate all maximal capture chains starting from `start`,
    where `current` is the piece's current position, and `visited_landings`
    is the set of cells the piece has stood on after jumps in this chain
    (excluding the start cell which is empty after the first jump).

    Yields (path, captured_set) where path is list of indices
    [start, land1, land2, ...] and captured_set is the set of jumped enemies.
    """
    enemy = opp(player)
    extensions = []
    for jumped, landing in JUMPS[current]:
        if board[jumped] != enemy:
            continue
        # Landing must be empty OR the original start (which is empty after departure).
        # But may NOT be a previously-visited landing in this chain.
        if landing != start and board[landing] != EMPTY:
            continue
        if landing in visited_landings:
            continue
        # Cannot jump same enemy twice — but since we remove and won't re-add,
        # we just track captured. Use the board mutation approach.
        extensions.append((jumped, landing))

    if not extensions:
        # End of chain; only valid if at least one jump was made.
        return

    for jumped, landing in extensions:
        # Apply this jump: remove enemy, move piece from current to landing.
        board[current] = EMPTY
        board[jumped] = EMPTY
        board[landing] = player

        any_continued = False
        new_visited = visited_landings | {landing}
        for sub_path, sub_caps in gen_chains_from(board, player, start, landing, new_visited):
            any_continued = True
            yield ([current] + sub_path, {jumped} | sub_caps) if False else None
            # We need to prepend `current` to a path that begins at `landing`
            # but our recursion convention: sub_path starts at `landing`. So full path
            # from this level is [current, *sub_path]. But the caller starts the path
            # with `current`, so we yield [landing, *sub_path[1:]] relative to caller.
            # Simpler: handle pathing iteratively below; redo this.

        # Undo
        board[landing] = EMPTY
        board[jumped] = enemy
        board[current] = player

    # The above attempt got tangled. Reimplement cleanly below.


def gen_capture_chains(board, player, start):
    """
    Generate all maximal capture chains starting from cell `start`.
    Returns list of (path, captured_indices) where path = [start, land1, land2, ...].
    Uses DFS with board mutation/restoration.
    """
    enemy = opp(player)
    results = []

    def dfs(current, path, captured, visited_landings):
        # Try every possible jump from `current`.
        any_jump = False
        for jumped, landing in JUMPS[current]:
            if board[jumped] != enemy:
                continue
            if jumped in captured:
                continue  # already captured (shouldn't happen, board[jumped] would be EMPTY)
            # landing must be empty OR the start cell (which is empty since piece left)
            if landing != start and board[landing] != EMPTY:
                continue
            if landing in visited_landings:
                continue
            any_jump = True
            # Apply
            board[current] = EMPTY
            board[jumped] = EMPTY
            board[landing] = player
            captured.add(jumped)
            path.append(landing)
            visited_landings.add(landing)

            dfs(landing, path, captured, visited_landings)

            # Undo
            visited_landings.discard(landing)
            path.pop()
            captured.discard(jumped)
            board[landing] = EMPTY
            board[jumped] = enemy
            board[current] = player

        if not any_jump and len(path) >= 2:
            # Maximal chain reached; record it.
            results.append((list(path), set(captured)))

    if board[start] != player:
        return results
    # quick check
    can = False
    for jumped, landing in JUMPS[start]:
        if board[jumped] == enemy and board[landing] == EMPTY:
            can = True
            break
    if not can:
        return results

    dfs(start, [start], set(), set())
    return results


def generate_moves(board, player):
    """
    Returns a list of moves. Each move is a tuple (path, captured_set).
    For slides, captured_set is empty.
    If any capture is available anywhere, only capture moves are returned (forced).
    """
    capture_moves = []
    for k in range(24):
        if board[k] == player:
            chains = gen_capture_chains(board, player, k)
            capture_moves.extend(chains)

    if capture_moves:
        return capture_moves

    # Slides
    slide_moves = []
    for k in range(24):
        if board[k] == player:
            for n in NEIGHBORS[k]:
                if board[n] == EMPTY:
                    slide_moves.append(([k, n], set()))
    return slide_moves


def apply_move(board, move, player):
    """
    Apply move to board in-place. Returns undo info.
    move = (path, captured_set)
    """
    path, captured = move
    start = path[0]
    end = path[-1]
    # Save state
    # We need to restore: piece at start, captured pieces back, end cell empty.
    enemy = opp(player)
    # Apply
    board[start] = EMPTY
    for c in captured:
        board[c] = EMPTY
    board[end] = player
    return (start, end, captured)  # undo info


def undo_move(board, undo, player):
    start, end, captured = undo
    enemy = opp(player)
    board[end] = EMPTY
    for c in captured:
        board[c] = enemy
    board[start] = player


# ---------- Move serialization ----------
def move_to_str(path):
    parts = [f"{rc(k)[0]},{rc(k)[1]}" for k in path]
    return "MOVE " + " -> ".join(parts)


def parse_move_line(line):
    """
    Parse 'MOVE r,i -> r,i [-> ...]' into a list of cell indices.
    Returns list[int].
    """
    # Strip 'MOVE ' prefix
    body = line[5:].strip()
    parts = body.split(" -> ")
    path = []
    for p in parts:
        rs, is_ = p.split(",")
        path.append(idx(int(rs), int(is_)))
    return path


def reconstruct_move(board, player, path):
    """
    Given an opponent's move path (list of cell indices), determine the captured set
    by simulating it on the current board. Returns (path, captured_set) or None if invalid.
    """
    if len(path) < 2:
        return None
    start = path[0]
    if board[start] != player:
        return None
    enemy = opp(player)

    if len(path) == 2:
        a, b = path[0], path[1]
        # Slide?
        if b in NEIGHBORS[a] and board[b] == EMPTY:
            # check distance: line-neighbor implies distance 1, so it's a slide
            # But could also be a jump? No — line-neighbor means adjacent; a jump
            # spans 2 cells. So len-2 with b in NEIGHBORS[a] is a slide.
            # However a jump path of length 2 has b NOT in NEIGHBORS[a] (it's 2 away).
            return (list(path), set())
        # Otherwise treat as a single-jump capture
        captured = set()
        for jumped, landing in JUMPS[a]:
            if landing == b and board[jumped] == enemy:
                captured.add(jumped)
                return (list(path), captured)
        return None

    # Multi-step: must be all jumps
    captured = set()
    # Simulate
    cur = start
    sim_board = board[:]
    sim_board[start] = EMPTY
    for nxt in path[1:]:
        # find matching jump
        found = None
        for jumped, landing in JUMPS[cur]:
            if landing == nxt and sim_board[jumped] == enemy and (landing == start or sim_board[landing] == EMPTY):
                found = (jumped, landing)
                break
        if found is None:
            return None
        jumped, landing = found
        sim_board[jumped] = EMPTY
        captured.add(jumped)
        cur = landing
    sim_board[cur] = player
    return (list(path), captured)


# ---------- Evaluation ----------
def evaluate(board, player):
    """
    Static evaluation from `player`'s perspective.
    Higher is better for `player`.
    """
    enemy = opp(player)
    my_count = 0
    en_count = 0
    my_score = 0.0
    en_score = 0.0

    # Material is dominant. Mobility and positional bonuses are secondary.
    # Pieces in inner rings are slightly more mobile/central.
    # Position weights by ring: outer rings have fewer line-neighbors.
    ring_weight = [1.05, 1.10, 1.00, 0.95]

    for k in range(24):
        v = board[k]
        if v == EMPTY:
            continue
        r, i = rc(k)
        w = ring_weight[r]
        if v == player:
            my_count += 1
            my_score += w
        else:
            en_count += 1
            en_score += w

    if en_count == 0:
        return 100000  # win
    if my_count == 0:
        return -100000  # loss

    # Material is the heavy term.
    material = (my_count - en_count) * 100.0
    pos = (my_score - en_score) * 2.0

    # Pieces threatened (can be captured by opponent next turn) — small penalty.
    # Cheap proxy: count of own pieces that are part of a (enemy_jumper, my_piece, empty) triple.
    threat_pen = 0
    my_threat = 0
    en_threat = 0
    for k in range(24):
        v = board[k]
        if v == EMPTY:
            continue
        # Is this piece threatened?
        # It's threatened if some enemy adjacent on a line could jump over it to an empty cell.
        # Equivalent: there exist (j_idx, land_idx) such that the triple (j_idx, k, land_idx)
        # is collinear, j_idx has enemy of v, land_idx is empty.
        # Use JUMPS from neighbor: a piece at k is threatened if some neighbor n has v_enemy
        # AND there's a jump from some cell c such that JUMPS[c] contains (k, land).
        # Easier: iterate neighbors of k; for each neighbor n that is enemy, check if there's
        # an empty cell on the far side from n through k.
        attacker = opp(v)
        is_threatened = False
        for n in NEIGHBORS[k]:
            if board[n] != attacker:
                continue
            # We need a cell `far` such that (n, k, far) is collinear AND far is empty.
            # Same-ring: if n and k are on same ring r, then (n,k,far) collinear means
            # far is on same ring at i+(i-n.i) mod 6 step.
            rn, in_ = rc(n)
            rk, ik = rc(k)
            if rn == rk:
                # same ring; step direction
                step = (ik - in_) % 6
                if step == 5:
                    step = -1
                if step in (1, -1):
                    far_i = (ik + step) % 6
                    far = idx(rk, far_i)
                    if board[far] == EMPTY:
                        is_threatened = True
                        break
            elif in_ == ik:
                # radial
                if rk - rn == 1 and rk + 1 <= 3:
                    far = idx(rk + 1, ik)
                    if board[far] == EMPTY:
                        is_threatened = True
                        break
                elif rn - rk == 1 and rk - 1 >= 0:
                    far = idx(rk - 1, ik)
                    if board[far] == EMPTY:
                        is_threatened = True
                        break
        if is_threatened:
            if v == player:
                my_threat += 1
            else:
                en_threat += 1

    threat_term = (en_threat - my_threat) * 8.0

    # Mobility: count of moves available; cheap small term.
    # Skip: too expensive to compute every leaf. material dominates.

    return material + pos + threat_term


# ---------- Search ----------
class TimeUp(Exception):
    pass


class Searcher:
    def __init__(self, time_budget):
        self.deadline = time.monotonic() + time_budget
        self.nodes = 0

    def time_left(self):
        return self.deadline - time.monotonic()

    def check_time(self):
        # Cheap periodic check; raise if out.
        if (self.nodes & 1023) == 0:
            if time.monotonic() >= self.deadline:
                raise TimeUp()

    def negamax(self, board, player, depth, alpha, beta, root_player):
        self.nodes += 1
        self.check_time()

        # Terminal checks
        my_count = sum(1 for x in board if x == player)
        en_count = sum(1 for x in board if x == opp(player))
        if en_count == 0:
            return 100000 - (1000 - depth)  # prefer faster wins
        if my_count == 0:
            return -100000 + (1000 - depth)

        moves = generate_moves(board, player)
        if not moves:
            # Stalemated -> loss for `player`
            return -100000 + (1000 - depth)

        if depth <= 0:
            # quiescence: keep searching while captures are forced
            if moves and len(moves[0][1]) > 0:
                # captures available; extend by one ply (cheap)
                pass
            else:
                return evaluate(board, player) if player == root_player else -evaluate(board, opp(player))

        # Move ordering: captures first by capture count desc, then slides
        moves.sort(key=lambda m: -len(m[1]))

        best = -10**9
        for m in moves:
            undo = apply_move(board, m, player)
            try:
                val = -self.negamax(board, opp(player), depth - 1, -beta, -alpha, root_player)
            finally:
                undo_move(board, undo, player)
            if val > best:
                best = val
            if best > alpha:
                alpha = best
            if alpha >= beta:
                break
        return best

    def search_root(self, board, player, depth):
        moves = generate_moves(board, player)
        if not moves:
            return None, 0
        moves.sort(key=lambda m: -len(m[1]))
        best_move = moves[0]
        best_val = -10**9
        alpha = -10**9
        beta = 10**9
        for m in moves:
            undo = apply_move(board, m, player)
            try:
                val = -self.negamax(board, opp(player), depth - 1, -beta, -alpha, player)
            finally:
                undo_move(board, undo, player)
            if val > best_val:
                best_val = val
                best_move = m
            if best_val > alpha:
                alpha = best_val
        return best_move, best_val


def choose_move(board, player, time_budget):
    """
    Iterative deepening within a time budget. Returns a move (path, captured).
    """
    moves = generate_moves(board, player)
    if not moves:
        return None
    if len(moves) == 1:
        return moves[0]

    # If only captures and only one capture, just play it (already handled above).
    s = Searcher(time_budget)
    best_move = moves[0]
    # Quick heuristic baseline: best by captures, then by eval after move.
    moves_scored = []
    for m in moves:
        undo = apply_move(board, m, player)
        sc = -evaluate(board, opp(player))  # from player's perspective after move
        undo_move(board, undo, player)
        moves_scored.append((sc, m))
    moves_scored.sort(key=lambda x: -x[0])
    best_move = moves_scored[0][1]

    # Iterative deepening
    try:
        for depth in range(2, 20):
            if s.time_left() < 0.02:
                break
            mv, val = s.search_root(board, player, depth)
            if mv is not None:
                best_move = mv
            # If we found a winning line, no need to search deeper.
            if val >= 50000:
                break
            # Safety: if more than 70% of budget used, stop.
            if s.time_left() < 0.05:
                break
    except TimeUp:
        pass

    return best_move


# ---------- Network / protocol ----------
class BotClient:
    def __init__(self, host="localhost", port=7474):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))
        self.rfile = self.sock.makefile("r", encoding="ascii", newline="\n")
        self.botname = os.environ.get("BOTNAME", "").rstrip("\n")
        self.board = initial_board()
        self.my_color = None  # 1 (A) or 2 (B)
        self.time_left = 30.0  # game clock in seconds

    def send_line(self, s):
        self.sock.sendall((s + "\n").encode("ascii"))

    def recv_line(self):
        line = self.rfile.readline()
        if not line:
            return None
        return line.rstrip("\n")

    def reset_for_game(self, color_letter):
        self.board = initial_board()
        self.my_color = A if color_letter == "A" else B
        self.time_left = 30.0

    def handle_turn(self):
        # We have self.time_left seconds for entire game. Allocate carefully.
        # Simple allocation: use ~ time_left / max(8, estimated_remaining_moves).
        # Keep a safety buffer.
        budget = max(0.05, min(self.time_left * 0.15, self.time_left - 0.5))
        if self.time_left < 1.0:
            budget = max(0.02, self.time_left - 0.2)
        if self.time_left < 0.3:
            budget = 0.02

        t0 = time.monotonic()
        move = choose_move(self.board, self.my_color, budget)
        elapsed = time.monotonic() - t0
        # We don't actually update self.time_left from our own clock — the server
        # is authoritative. But we'll subtract our local elapsed as an approximation
        # for budgeting future moves.
        self.time_left -= elapsed

        if move is None:
            # No legal move — we'll send something that will DQ but server should
            # have stalemated us before sending TURN. Defensive: send a slide that
            # doesn't exist; will get DQ malformed -> just close.
            # Better: pick any of our pieces and try a non-move; but we have none.
            # Just send a noop that fails gracefully.
            self.send_line("MOVE 0,0 -> 0,1")
            return
        path, _ = move
        self.send_line(move_to_str(path))

    def apply_opp_move(self, line):
        # line is 'OPP MOVE r,i -> r,i ...'
        move_line = line[4:]  # strip 'OPP '
        try:
            path = parse_move_line(move_line)
        except Exception:
            return
        opp_color = opp(self.my_color)
        result = reconstruct_move(self.board, opp_color, path)
        if result is None:
            return
        apply_move(self.board, result, opp_color)

    def apply_own_move_after_ok(self, move):
        if move is None:
            return
        apply_move(self.board, move, self.my_color)

    def run(self):
        # Send botname
        self.send_line(self.botname)

        last_own_move = None  # the move we just sent, to apply on OK

        while True:
            line = self.recv_line()
            if line is None:
                return

            if line.startswith("MATCH "):
                # New matchup
                last_own_move = None
                continue

            if line.startswith("GAME "):
                # GAME <g> <color>
                parts = line.split()
                color_letter = parts[2]
                self.reset_for_game(color_letter)
                last_own_move = None
                continue

            if line.startswith("BOARD "):
                tokens = line.split()[1:]
                self.board = parse_board(tokens)
                continue

            if line == "TURN":
                # Compute and send move; remember it to apply on OK.
                budget = max(0.05, min(self.time_left * 0.15, self.time_left - 0.5))
                if self.time_left < 1.0:
                    budget = max(0.02, self.time_left - 0.2)
                if self.time_left < 0.3:
                    budget = 0.02
                t0 = time.monotonic()
                move = choose_move(self.board, self.my_color, budget)
                elapsed = time.monotonic() - t0
                self.time_left -= elapsed
                if move is None:
                    # shouldn't happen — server would have stalemated us
                    self.send_line("MOVE 0,0 -> 0,1")
                    last_own_move = None
                else:
                    self.send_line(move_to_str(move[0]))
                    last_own_move = move
                continue

            if line.startswith("OK "):
                # Apply our move to the board
                if last_own_move is not None:
                    apply_move(self.board, last_own_move, self.my_color)
                    last_own_move = None
                continue

            if line.startswith("DQ "):
                # Our move was rejected; don't apply. Game will end shortly.
                last_own_move = None
                continue

            if line.startswith("OPP "):
                self.apply_opp_move(line)
                continue

            if line.startswith("GAME_END "):
                last_own_move = None
                continue

            if line.startswith("MATCH_END "):
                continue

            if line == "TOURNAMENT_END":
                return

            # Unknown line — ignore.


def main():
    try:
        client = BotClient()
        client.run()
    except (BrokenPipeError, ConnectionResetError):
        pass
    except Exception as e:
        # Last-resort: don't crash silently in a way that hangs; log to stderr.
        try:
            sys.stderr.write(f"bot error: {e}\n")
        except Exception:
            pass


if __name__ == "__main__":
    main()