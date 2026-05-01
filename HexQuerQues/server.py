"""
HexQuerQues Tournament Server.

Two-player capture game on four concentric hexagons (24 vertices), classic
Alquerques rules: forced capture, mandatory chain, win on capture-all-six
or stalemate-opponent. Round-robin of 1v1 matchups; each matchup is 2
games with first-mover swapped between the games.

Per-bot per-game wall-clock budget: 30 s (chess-clock style).
"""
import os
import re
import socket
import threading
import time

# ── Tournament configuration ─────────────────────────────────────────────────
HOST = 'localhost'
PORT = 7474
REGISTRATION_WINDOW = 10.0
GAME_TIMER = 30.0           # chess-clock budget per side per game
GAMES_PER_MATCH = 2         # 2 games, first-mover swapped
MATCH_WIN_PTS = 3
MATCH_DRAW_PTS = 1
DRAW_PLY_LIMIT = 40         # 40 plies (half-moves) without capture → draw
THREEFOLD = 3               # same position 3× → draw
MAX_CHAIN_SEGMENTS = 12     # matches the regex bound in prompt §5
LOG_PATH = 'results.log'

# ── Board ────────────────────────────────────────────────────────────────────
# Vertex ordering: 24 cells in fixed (r, i) order, ring-major:
#   0,0  0,1  0,2  0,3  0,4  0,5  1,0 ... 3,5
N_RINGS = 4
N_VERTS = 6


def vid(r, i):
    """Flat vertex index from (ring, vertex)."""
    return r * N_VERTS + i


def coord(v):
    return v // N_VERTS, v % N_VERTS


def initial_board():
    """Empty rings 0,1; ring 2 alternating A/B starting A; ring 3 same."""
    board = ['.'] * (N_RINGS * N_VERTS)
    for ri in (2, 3):
        for ii in range(N_VERTS):
            board[vid(ri, ii)] = 'A' if ii % 2 == 0 else 'B'
    return board


def board_to_str(board):
    """Server BOARD line payload: 24 space-separated cells."""
    return ' '.join(board)


def neighbors(r, i):
    """Line neighbors of (r, i): same-ring ±1 mod 6, plus radial r±1."""
    out = []
    out.append((r, (i + 1) % N_VERTS))
    out.append((r, (i - 1) % N_VERTS))
    if r > 0:
        out.append((r - 1, i))
    if r < N_RINGS - 1:
        out.append((r + 1, i))
    return out


def jump_targets(r, i):
    """All (jumped, landing) pairs reachable from (r,i) along a board line.

    For each direction (same-ring CW/CCW; radial inward; radial outward),
    if the line has 3 collinear vertices on the board (start, middle,
    landing), return the (middle, landing) pair.
    """
    out = []
    # same-ring +2
    out.append(((r, (i + 1) % N_VERTS), (r, (i + 2) % N_VERTS)))
    out.append(((r, (i - 1) % N_VERTS), (r, (i - 2) % N_VERTS)))
    # radial outward (r → r+2)
    if r + 2 < N_RINGS:
        out.append(((r + 1, i), (r + 2, i)))
    # radial inward (r → r-2)
    if r - 2 >= 0:
        out.append(((r - 1, i), (r - 2, i)))
    return out


# ── Move parsing ─────────────────────────────────────────────────────────────

MOVE_RE = re.compile(
    r'^MOVE ([0-3]),([0-5])((?: -> [0-3],[0-5])+)$'
)
SEG_RE = re.compile(r' -> ([0-3]),([0-5])')


def parse_move(line):
    """Parse a MOVE line. Returns list of (r, i) cells (length ≥ 2) or None."""
    if not line.endswith('\n'):
        return None
    body = line[:-1]
    m = MOVE_RE.fullmatch(body)
    if not m:
        return None
    r0, i0 = int(m.group(1)), int(m.group(2))
    seq = [(r0, i0)]
    for sm in SEG_RE.finditer(m.group(3)):
        seq.append((int(sm.group(1)), int(sm.group(2))))
    if len(seq) < 2 or len(seq) > MAX_CHAIN_SEGMENTS + 1:
        return None
    return seq


# ── Capture availability + move validation ──────────────────────────────────

def piece_can_capture(board, r, i, my, enemy):
    """Does the piece at (r, i) have at least one legal capture against the
    current board? Considers all 4 jump directions (where on-board)."""
    for (mr, mi), (lr, li) in jump_targets(r, i):
        if board[vid(mr, mi)] == enemy and board[vid(lr, li)] == '.':
            return True
    return False


def any_capture_available(board, side):
    my = side
    enemy = 'B' if side == 'A' else 'A'
    for v in range(N_RINGS * N_VERTS):
        if board[v] == my:
            r, i = coord(v)
            if piece_can_capture(board, r, i, my, enemy):
                return True
    return False


def has_legal_move(board, side):
    """Either a capture exists, or some piece can slide to an adjacent empty."""
    if any_capture_available(board, side):
        return True
    my = side
    for v in range(N_RINGS * N_VERTS):
        if board[v] != my:
            continue
        r, i = coord(v)
        for nr, ni in neighbors(r, i):
            if board[vid(nr, ni)] == '.':
                return True
    return False


def validate_and_apply(board, seq, side):
    """Validate `seq` (list of (r,i) cells) as a move for `side`. If valid,
    apply it to `board` in place and return (True, n_captures, None). If
    invalid, return (False, 0, dq_reason). Board is NOT mutated on failure.
    """
    my = side
    enemy = 'B' if side == 'A' else 'A'
    r0, i0 = seq[0]

    # Owner check
    if board[vid(r0, i0)] != my:
        return False, 0, f"wrong_owner_{r0},{i0}"

    is_slide = (len(seq) == 2 and is_slide_segment(r0, i0, seq[1][0], seq[1][1]))

    # Forced capture: if a capture exists for the player, slides are illegal.
    if is_slide and any_capture_available(board, side):
        return False, 0, "must_capture"

    if is_slide:
        r1, i1 = seq[1]
        if not is_neighbor(r0, i0, r1, i1):
            return False, 0, f"illegal_slide_{r0},{i0}->_{r1},{i1}"
        if board[vid(r1, i1)] != '.':
            return False, 0, f"illegal_slide_{r0},{i0}->_{r1},{i1}"
        # Apply
        board[vid(r0, i0)] = '.'
        board[vid(r1, i1)] = my
        return True, 0, None

    # Otherwise: chain capture. Each segment must be a jump.
    sim = list(board)   # mutate copy; commit on success
    cap_count = 0
    cur_r, cur_i = r0, i0
    sim[vid(cur_r, cur_i)] = '.'   # piece leaves start

    for k in range(1, len(seq)):
        nr, ni = seq[k]
        seg = find_jump_segment(cur_r, cur_i, nr, ni)
        if seg is None:
            return False, 0, f"illegal_jump_{cur_r},{cur_i}->_{nr},{ni}"
        mr, mi = seg
        # Jumped cell must hold an enemy
        if sim[vid(mr, mi)] != enemy:
            return False, 0, f"illegal_jump_{cur_r},{cur_i}->_{nr},{ni}"
        # Landing cell must be empty
        if sim[vid(nr, ni)] != '.':
            return False, 0, f"illegal_jump_{cur_r},{cur_i}->_{nr},{ni}"
        # Apply jump in sim: remove jumped enemy, move piece
        sim[vid(mr, mi)] = '.'
        cap_count += 1
        cur_r, cur_i = nr, ni

    # Place piece at final landing
    sim[vid(cur_r, cur_i)] = my

    # Chain completeness: from final landing, no further capture must exist
    # for THIS piece.
    for (jr, ji), (lr, li) in jump_targets(cur_r, cur_i):
        if sim[vid(jr, ji)] == enemy and sim[vid(lr, li)] == '.':
            return False, 0, f"chain_unfinished_at_{cur_r},{cur_i}"

    # Commit
    for v, val in enumerate(sim):
        board[v] = val
    return True, cap_count, None


def is_slide_segment(r0, i0, r1, i1):
    """Treat as a slide candidate if (r1,i1) is a line-neighbor of (r0,i0)."""
    return is_neighbor(r0, i0, r1, i1)


def is_neighbor(r0, i0, r1, i1):
    if r0 == r1 and ((i1 - i0) % N_VERTS in (1, 5)):
        return True
    if i0 == i1 and abs(r1 - r0) == 1:
        return True
    return False


def find_jump_segment(r0, i0, r1, i1):
    """If (r0,i0)→(r1,i1) is a jump line on the board (start/middle/landing
    collinear with middle adjacent to start), return (mr, mi). Otherwise None."""
    # Same-ring jump: r unchanged, i differs by ±2 mod 6
    if r0 == r1:
        d = (i1 - i0) % N_VERTS
        if d == 2:
            return (r0, (i0 + 1) % N_VERTS)
        if d == 4:   # equivalent to -2 mod 6
            return (r0, (i0 - 1) % N_VERTS)
    # Radial jump: i unchanged, r differs by ±2 (and middle ring on board)
    if i0 == i1:
        if r1 - r0 == 2:
            return (r0 + 1, i0)
        if r1 - r0 == -2:
            return (r0 - 1, i0)
    return None


# ── Client wrapper ───────────────────────────────────────────────────────────

class Client:
    def __init__(self, sock, name, f=None):
        self.sock = sock
        self.name = name
        if f is None:
            f = sock.makefile('r', encoding='utf-8', errors='replace',
                              newline='')
        self.f = f
        # Tournament-tracking
        self.match_pts = 0
        self.match_w = 0
        self.match_d = 0
        self.match_l = 0
        self.game_wins = 0
        self.captures = 0

    def send(self, data):
        try:
            self.sock.sendall(data.encode('utf-8'))
        except OSError:
            pass

    def readline(self, timeout):
        self.sock.settimeout(timeout)
        try:
            return self.f.readline()
        finally:
            try:
                self.sock.settimeout(None)
            except OSError:
                pass

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ── Game runner ─────────────────────────────────────────────────────────────

def play_game(c_first, c_second, game_idx, log_lines):
    """Play one game where c_first is color A (first to move) and c_second
    is color B. Returns the result token (one of A_WINS, B_WINS, DRAW,
    A_DQ, B_DQ, A_TIMEOUT, B_TIMEOUT, A_STALEMATED, B_STALEMATED) and the
    number of captures attributed to each (cap_a, cap_b)."""
    board = initial_board()

    # Send GAME header + BOARD to both
    c_first.send(f"GAME {game_idx} A\n")
    c_first.send(f"BOARD {board_to_str(board)}\n")
    c_second.send(f"GAME {game_idx} B\n")
    c_second.send(f"BOARD {board_to_str(board)}\n")

    side = 'A'
    side_to_client = {'A': c_first, 'B': c_second}
    side_to_clock = {'A': GAME_TIMER, 'B': GAME_TIMER}
    pieces = {'A': 6, 'B': 6}
    captures = {'A': 0, 'B': 0}

    plies_since_capture = 0
    pos_history = {}   # canonical board+side → count

    while True:
        # Stalemate check before sending TURN
        if not has_legal_move(board, side):
            log_lines.append(f"  G{game_idx} {side}={side_to_client[side].name}"
                             f" has no legal move → stalemate")
            return f"{side}_STALEMATED", captures

        # Win-by-capture-all (defensive; pieces cannot be 0 unless we missed it)
        if pieces['A'] == 0:
            return "B_WINS", captures
        if pieces['B'] == 0:
            return "A_WINS", captures

        cur = side_to_client[side]
        opp = side_to_client['B' if side == 'A' else 'A']
        budget = side_to_clock[side]

        cur.send("TURN\n")
        t0 = time.monotonic()
        try:
            line = cur.readline(timeout=max(0.001, budget))
        except (socket.timeout, OSError):
            line = None
        elapsed = time.monotonic() - t0
        side_to_clock[side] = max(0.0, budget - elapsed)

        if line is None or line == '' or side_to_clock[side] <= 0:
            cur.send("DQ timeout\n")
            log_lines.append(f"  G{game_idx} {side}={cur.name} TIMEOUT "
                             f"(used {GAME_TIMER - side_to_clock[side]:.2f}s)")
            return f"{side}_TIMEOUT", captures

        seq = parse_move(line)
        if seq is None:
            cur.send("DQ malformed\n")
            log_lines.append(f"  G{game_idx} {side}={cur.name} DQ malformed: "
                             f"{line.rstrip()!r}")
            return f"{side}_DQ", captures

        ok, n_caps, dq = validate_and_apply(board, seq, side)
        if not ok:
            cur.send(f"DQ {dq}\n")
            log_lines.append(f"  G{game_idx} {side}={cur.name} DQ {dq}: "
                             f"{line.rstrip()!r}")
            return f"{side}_DQ", captures

        # OK + opponent broadcast
        cur.send(f"OK {n_caps}\n")
        opp.send(f"OPP {line}")   # `line` already ends with \n

        # Update piece counts
        if n_caps > 0:
            enemy = 'B' if side == 'A' else 'A'
            pieces[enemy] -= n_caps
            captures[side] += n_caps
            plies_since_capture = 0
            pos_history.clear()
        else:
            plies_since_capture += 1

        log_lines.append(f"  G{game_idx} ply {plies_since_capture if n_caps == 0 else 0}"
                         f" {side}={cur.name} {line.rstrip()} → OK {n_caps}"
                         f" (pieces A={pieces['A']} B={pieces['B']},"
                         f" clock {side}={side_to_clock[side]:.2f}s)")

        # Win-by-capture-all immediately
        if pieces['A'] == 0:
            return "B_WINS", captures
        if pieces['B'] == 0:
            return "A_WINS", captures

        # Draw: 40 plies without capture
        if plies_since_capture >= DRAW_PLY_LIMIT:
            return "DRAW", captures

        # Switch side and check threefold (after the side switch, on the
        # position the side-to-move sees).
        side = 'B' if side == 'A' else 'A'
        key = (tuple(board), side)
        pos_history[key] = pos_history.get(key, 0) + 1
        if pos_history[key] >= THREEFOLD:
            return "DRAW", captures


def announce_game_end(c_first, c_second, game_idx, result):
    c_first.send(f"GAME_END {game_idx} {result}\n")
    c_second.send(f"GAME_END {game_idx} {result}\n")


# ── Round-robin scheduler ────────────────────────────────────────────────────

def round_robin_schedule(n_bots):
    """Circle-method round-robin. List of rotation-rounds, each a list of
    disjoint (i, j) index pairs."""
    bots = list(range(n_bots))
    if n_bots % 2 == 1:
        bots.append(None)
    n = len(bots)

    schedule = []
    for _ in range(n - 1):
        rr = []
        for i in range(n // 2):
            a = bots[i]
            b = bots[n - 1 - i]
            if a is not None and b is not None:
                rr.append((a, b))
        schedule.append(rr)
        bots = [bots[0]] + [bots[-1]] + bots[1:-1]
    return schedule


def rotate_log():
    if not os.path.exists(LOG_PATH):
        return
    n = 1
    while os.path.exists(f"{LOG_PATH}.{n}"):
        n += 1
    for i in range(n - 1, 0, -1):
        os.rename(f"{LOG_PATH}.{i}", f"{LOG_PATH}.{i + 1}")
    os.rename(LOG_PATH, f"{LOG_PATH}.1")


# ── Tournament harness ───────────────────────────────────────────────────────

def run_tournament():
    rotate_log()
    log = open(LOG_PATH, 'w', encoding='utf-8')

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(32)
    server_sock.settimeout(1.0)

    clients = []
    print(f"[*] Server live on {HOST}:{PORT}. Registration: {REGISTRATION_WINDOW}s")

    name_re = re.compile(r'^[A-Za-z0-9_-]{1,32}$')
    start_reg = time.time()
    while time.time() - start_reg < REGISTRATION_WINDOW:
        try:
            conn, addr = server_sock.accept()
            conn.settimeout(None)
            f = conn.makefile('r', encoding='utf-8', errors='replace', newline='')
            raw = f.readline()
            name = raw[:-1] if raw.endswith('\n') else raw
            if not name_re.match(name):
                print(f"[!] Rejected name {name!r} from {addr}; closing.")
                try:
                    conn.close()
                except OSError:
                    pass
                continue
            c = Client(conn, name, f=f)
            clients.append(c)
            print(f"[*] Bot '{name}' joined.")
        except socket.timeout:
            continue

    if len(clients) < 2:
        print("[!] Need at least 2 bots for round-robin.")
        log.close()
        server_sock.close()
        return

    schedule = round_robin_schedule(len(clients))
    n_matches = sum(len(rr) for rr in schedule)
    max_concurrent = max(len(rr) for rr in schedule)
    print(f"[*] {len(clients)} bots registered. {n_matches} matchups "
          f"× {GAMES_PER_MATCH} games in {len(schedule)} rotation-rounds "
          f"(up to {max_concurrent} matchups in parallel).\n")
    log.write(f"Tournament: {len(clients)} bots, round-robin\n")
    log.write(f"Bots: {', '.join(c.name for c in clients)}\n")
    log.write(f"Matchups: {n_matches}, games per matchup: {GAMES_PER_MATCH}, "
              f"max concurrent: {max_concurrent}\n\n")

    log_lock = threading.Lock()
    match_counter = [0]
    match_counter_lock = threading.Lock()

    def emit(line):
        with log_lock:
            print(line)
            log.write(line + "\n")
            log.flush()

    def run_match(c_a, c_b):
        """Play 2 games: g1 has c_a as A; g2 has c_b as A."""
        with match_counter_lock:
            match_counter[0] += 1
            match_idx = match_counter[0]
        prefix = f"[M{match_idx:02d}]"
        emit(f"{prefix} === START: {c_a.name} vs {c_b.name} ===")

        # Send MATCH header to both
        c_a.send(f"MATCH {match_idx} {c_b.name}\n")
        c_b.send(f"MATCH {match_idx} {c_a.name}\n")

        a_game_wins = 0
        b_game_wins = 0

        for game_idx in (1, 2):
            if game_idx == 1:
                first, second = c_a, c_b
            else:
                first, second = c_b, c_a

            log_lines = []
            log_lines.append(f"{prefix} --- GAME {game_idx} (A={first.name}, "
                             f"B={second.name}) ---")
            log_lines.append(f"  initial BOARD: {board_to_str(initial_board())}")
            t0 = time.monotonic()
            result, caps = play_game(first, second, game_idx, log_lines)
            dur = time.monotonic() - t0

            announce_game_end(first, second, game_idx, result)

            log_lines.append(f"{prefix}   GAME_END {game_idx}: {result} "
                             f"(captures A={caps['A']} B={caps['B']}, "
                             f"duration {dur:.2f}s)")

            # Tally captures
            first.captures += caps['A']
            second.captures += caps['B']

            # Tally wins per the result token
            a_won_game = result in ('A_WINS', 'B_DQ', 'B_TIMEOUT', 'B_STALEMATED')
            b_won_game = result in ('B_WINS', 'A_DQ', 'A_TIMEOUT', 'A_STALEMATED')
            if a_won_game:
                first.game_wins += 1
                if first is c_a:
                    a_game_wins += 1
                else:
                    b_game_wins += 1
            elif b_won_game:
                second.game_wins += 1
                if second is c_a:
                    a_game_wins += 1
                else:
                    b_game_wins += 1
            # DRAW: neither bot increments game_wins

            with log_lock:
                for line in log_lines:
                    log.write(line + "\n")
                log.flush()

        # Match outcome from c_a's perspective
        if a_game_wins > b_game_wins:
            c_a.match_pts += MATCH_WIN_PTS
            c_a.match_w += 1
            c_b.match_l += 1
            verdict = f"{c_a.name} wins matchup {a_game_wins}-{b_game_wins}"
        elif b_game_wins > a_game_wins:
            c_b.match_pts += MATCH_WIN_PTS
            c_b.match_w += 1
            c_a.match_l += 1
            verdict = f"{c_b.name} wins matchup {b_game_wins}-{a_game_wins}"
        else:
            c_a.match_pts += MATCH_DRAW_PTS
            c_b.match_pts += MATCH_DRAW_PTS
            c_a.match_d += 1
            c_b.match_d += 1
            verdict = f"draw {a_game_wins}-{b_game_wins}"

        # MATCH_END to both
        if a_game_wins > b_game_wins:
            a_outcome, b_outcome = 'W', 'L'
        elif a_game_wins < b_game_wins:
            a_outcome, b_outcome = 'L', 'W'
        else:
            a_outcome, b_outcome = 'D', 'D'
        match_end_line = (f"MATCH_END {match_idx} "
                          f"{c_a.name}={a_outcome}:{a_game_wins} "
                          f"{c_b.name}={b_outcome}:{b_game_wins}\n")
        c_a.send(match_end_line)
        c_b.send(match_end_line)

        emit(f"{prefix} === VERDICT: {verdict} ===")

    for rr_idx, match_round in enumerate(schedule, 1):
        emit(f"\n========== ROTATION-ROUND {rr_idx}/{len(schedule)} "
             f"({len(match_round)} matches in parallel) ==========")
        threads = []
        for (i, j) in match_round:
            t = threading.Thread(
                target=run_match, args=(clients[i], clients[j]), daemon=True)
            t.start()
            threads.append(t)
        # Generous join timeout: each game can run up to (2 × GAME_TIMER) of
        # bot clock + protocol overhead. 2 games per matchup.
        for t in threads:
            t.join(timeout=GAMES_PER_MATCH * (2 * GAME_TIMER + 30))
        time.sleep(0.5)

    print("\n[*] Tournament complete. Sending TOURNAMENT_END.")
    for c in clients:
        c.send("TOURNAMENT_END\n")

    log.write("\n========== FINAL STANDINGS ==========\n")
    final = sorted(
        clients,
        key=lambda c: (-c.match_pts, -c.game_wins, -c.captures),
    )
    header = ("  rank  bot                          match_pts  W-D-L      "
              "game_wins  captures")
    print(header)
    log.write(header + "\n")
    for rank, c in enumerate(final, 1):
        line = (f"  #{rank:<3}  {c.name:<28}  {c.match_pts:>9}  "
                f"{c.match_w}-{c.match_d}-{c.match_l:<6}  "
                f"{c.game_wins:>9}  {c.captures:>8}")
        print(line)
        log.write(line + "\n")

    log.close()
    for c in clients:
        c.close()
    server_sock.close()


if __name__ == '__main__':
    run_tournament()
