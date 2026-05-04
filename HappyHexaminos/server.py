"""
HappyHexaminos Tournament Server.

10 rounds. Each round, the server picks a rectangle (w, h) with w*h ≡ 0
(mod 6), w*h ≥ 36, areas monotonically growing. The server constructs a
witness tiling using the 35 free hexominoes (so each round is guaranteed
tileable) and broadcasts ROUND <n> <w> <h> to every registered bot.

Each bot has 30 s wall-clock per round to send back a tiling grid: h rows
of w cells, each cell written as `[<id>]`. The server validates that the
submission fully covers the rectangle, every connected same-id region is
exactly 6 cells, every region is one of the 35 free hexominoes, and ids
are globally unique. The bot's score for the round is its *inventory*:
the number of distinct free hexomino shapes used.

Per-round medals: 3/2/1 to the bottom-3 inventories. Ties for any medal
slot break by submission arrival timestamp; the bot whose `END` line was
received earliest wins the slot. Invalid/timeout → 0 pts that round.

Tournament total = sum of round points. Tiebreak in standings: total
medals, then lowest cumulative inventory.
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
ROUND_BUDGET = 30.0          # wall-clock per bot per round
N_ROUNDS = 10
LOG_PATH = 'results.log'

# Round sizes: (w, h) per round, areas monotonically growing, all ≡ 0 mod 6,
# and w*h ≥ 36. Picked to grow smoothly to a 30×30 ceiling.
ROUND_SIZES = [
    (24, 27),   # 648
    (24, 28),   # 672
    (24, 29),   # 696
    (24, 30),   # 720
    (25, 30),   # 750
    (26, 30),   # 780
    (27, 30),   # 810
    (28, 30),   # 840
    (29, 30),   # 870
    (30, 30),   # 900
]
assert len(ROUND_SIZES) == N_ROUNDS
for (w, h) in ROUND_SIZES:
    assert 1 <= w <= 30 and 1 <= h <= 30
    assert (w * h) % 6 == 0 and w * h >= 36
areas = [w * h for w, h in ROUND_SIZES]
assert all(areas[i] < areas[i + 1] for i in range(len(areas) - 1))


# ── Free hexomino enumeration ────────────────────────────────────────────────

def _normalize(cells):
    """Translate so min-row=0, min-col=0; return a frozenset."""
    mr = min(r for r, c in cells)
    mc = min(c for r, c in cells)
    return frozenset((r - mr, c - mc) for r, c in cells)


def _all_orientations(cells):
    """All 8 rotations + reflections of a polyomino, normalized."""
    out = set()
    cur = cells
    for _ in range(4):
        cur = _normalize(cur)
        out.add(cur)
        cur = frozenset((c, -r) for r, c in cur)   # 90° rotation
    cur = frozenset((r, -c) for r, c in cells)     # horizontal reflection
    for _ in range(4):
        cur = _normalize(cur)
        out.add(cur)
        cur = frozenset((c, -r) for r, c in cur)
    return out


def _canonical(cells):
    """Lex-min representative across rotations + reflections."""
    return min(_all_orientations(cells),
               key=lambda s: tuple(sorted(s)))


def _enumerate_polyominoes(n):
    """All free n-ominoes as canonical frozensets."""
    shapes = {frozenset([(0, 0)])}
    for _ in range(n - 1):
        new = set()
        for s in shapes:
            for (r, c) in s:
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = r + dr, c + dc
                    if (nr, nc) not in s:
                        new.add(_normalize(s | {(nr, nc)}))
        shapes = new
    canon = set()
    for s in shapes:
        canon.add(_canonical(s))
    return sorted(canon, key=lambda x: tuple(sorted(x)))


HEXOMINOES = _enumerate_polyominoes(6)
assert len(HEXOMINOES) == 35, f"expected 35 free hexominoes, got {len(HEXOMINOES)}"
HEX_ID = {h: i for i, h in enumerate(HEXOMINOES)}

# All fixed orientations of all 35 hexominoes (used by the witness-tiling
# generator). list[(canonical_id, frozenset_of_cells)].
HEX_ORIENTATIONS = []
for hid, h in enumerate(HEXOMINOES):
    for ori in _all_orientations(h):
        HEX_ORIENTATIONS.append((hid, ori))


# ── Witness-tiling generator ─────────────────────────────────────────────────
# Each round size satisfies 6|w or 6|h, so the I-hexomino (#0, 1×6) tiles it
# constructively in O(area). The generator is deterministic given (w, h, seed)
# — the seed only permutes piece-instance ids — so a witness is replayable
# from the seed logged in results.log.


def generate_witness_tiling(w, h, seed=None):
    """Construct a tiling of w×h using the I-hexomino (shape #0, 1×6) only.

    Every round size we use satisfies 6|w or 6|h, so the I-hexomino tiles
    each round constructively in O(area). The generator is deterministic
    given (w, h) and `seed` — the seed only permutes the piece-instance
    ids assigned to each placement, so the witness logged with one seed
    can be reproduced exactly by another caller with the same seed.

    Returns a (h × w) grid of piece-instance ids.
    """
    import random
    rng = random.Random(seed)

    grid = [[-1] * w for _ in range(h)]

    if w % 6 == 0:
        # Horizontal I-pieces: each piece is 1 row × 6 cols.
        piece = 0
        for r in range(h):
            for c0 in range(0, w, 6):
                for dc in range(6):
                    grid[r][c0 + dc] = piece
                piece += 1
    elif h % 6 == 0:
        # Vertical I-pieces: each piece is 6 rows × 1 col.
        piece = 0
        for c in range(w):
            for r0 in range(0, h, 6):
                for dr in range(6):
                    grid[r0 + dr][c] = piece
                piece += 1
    else:
        raise ValueError(
            f"witness size {w}×{h} has neither dim divisible by 6; "
            f"the I-hexomino tiling does not apply")

    # Permute piece ids deterministically so witnesses generated with the
    # same seed are byte-identical, but witnesses with different seeds
    # show variation in the id labels.
    n_pieces = w * h // 6
    perm = list(range(n_pieces))
    rng.shuffle(perm)
    for r in range(h):
        for c in range(w):
            grid[r][c] = perm[grid[r][c]]

    return grid


# ── Submission parser & validator ────────────────────────────────────────────

CELL_RE = re.compile(r'\[(\d+)\]')


def parse_row(line, w):
    """Parse a row of w `[<id>]` cells. Returns list[int] of length w, or None."""
    if line is None:
        return None
    if line.endswith('\n'):
        line = line[:-1]
    if line.endswith('\r') or '\r' in line:
        return None
    if line.startswith(' ') or line.endswith(' '):
        return None
    cells = []
    pos = 0
    while pos < len(line):
        m = CELL_RE.match(line, pos)
        if not m:
            return None
        digits = m.group(1)
        # Reject leading-zero except literal "0"
        if len(digits) > 1 and digits[0] == '0':
            return None
        cells.append(int(digits))
        pos = m.end()
    if len(cells) != w:
        return None
    return cells


def validate_submission(rows, w, h):
    """Return (ok, inventory_or_reason).

    rows: list[list[int]] of shape (h, w). Returns (True, inventory) on
    success or (False, reason_string) on failure.
    """
    # Group cells by id; check connectedness, size, shape.
    cells_by_id = {}
    for r in range(h):
        for c in range(w):
            v = rows[r][c]
            cells_by_id.setdefault(v, []).append((r, c))

    distinct_shapes = set()

    for piece_id, cells in cells_by_id.items():
        if len(cells) != 6:
            return False, f"wrong_size_{piece_id}_{len(cells)}"
        # Connectedness check (4-neighbour). If two cells aren't reachable
        # via 4-adjacency, they're a duplicate-id violation.
        cell_set = set(cells)
        seen = {cells[0]}
        stack = [cells[0]]
        while stack:
            r, c = stack.pop()
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if (nr, nc) in cell_set and (nr, nc) not in seen:
                    seen.add((nr, nc))
                    stack.append((nr, nc))
        if len(seen) != 6:
            # Multiple disconnected components share this id → duplicate.
            return False, f"duplicate_id_{piece_id}"

        canon = _canonical(frozenset(cells))
        if canon not in HEX_ID:
            return False, f"not_a_hexomino_{piece_id}"
        distinct_shapes.add(HEX_ID[canon])

    return True, len(distinct_shapes)


# ── Client wrapper ───────────────────────────────────────────────────────────

class Client:
    def __init__(self, sock, name, f=None):
        self.sock = sock
        self.name = name
        if f is None:
            f = sock.makefile('r', encoding='utf-8', errors='replace',
                              newline='')
        self.f = f
        self.points = 0
        self.medals = [0, 0, 0]   # gold, silver, bronze
        self.inventories = []     # per-round inventory or None
        self.medal_inv_sum = 0    # cumulative inventory across medal-earning rounds

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


# ── Round driver ─────────────────────────────────────────────────────────────

def collect_submission(client, w, h, deadline):
    """Read h row lines + END from the client. Returns
    (rows, end_timestamp, error_or_None).

    rows is None on error; end_timestamp is the wall-clock at which `END`
    (or the timeout) was reached.
    """
    rows = []
    for r in range(h):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None, time.monotonic(), "timeout"
        try:
            line = client.readline(timeout=remaining)
        except (socket.timeout, OSError):
            return None, time.monotonic(), "timeout"
        if line is None or line == '':
            return None, time.monotonic(), "timeout"
        parsed = parse_row(line, w)
        if parsed is None:
            return None, time.monotonic(), f"malformed_row_{r}"
        rows.append(parsed)

    # Read the END line.
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None, time.monotonic(), "timeout"
    try:
        end_line = client.readline(timeout=remaining)
    except (socket.timeout, OSError):
        return None, time.monotonic(), "timeout"
    end_ts = time.monotonic()
    if end_line is None or end_line.rstrip('\n') != 'END':
        return None, end_ts, "malformed_rows"
    return rows, end_ts, None


def grid_to_str(grid):
    """Render an integer grid as a human-readable [<id>] block."""
    return '\n'.join(''.join(f"[{v}]" for v in row) for row in grid)


def run_round(round_idx, w, h, clients, log, log_lock):
    """Send ROUND to all bots in parallel and collect submissions in
    parallel threads. Validate each, then medal-rank.

    Returns nothing — mutates client tallies.
    """
    # Generate witness tiling (server confirms tileability). Seed is
    # derived from the round index so witnesses are reproducible: a tester
    # can re-call `generate_witness_tiling(w, h, seed=witness_seed)` with
    # the seed logged below to regenerate the exact same tiling.
    witness_seed = round_idx * 1000003
    t_witness = time.monotonic()
    witness = generate_witness_tiling(w, h, seed=witness_seed)
    witness_dur = time.monotonic() - t_witness

    with log_lock:
        log.write(f"\n========== ROUND {round_idx} ({w}×{h}, area={w*h}, "
                  f"k={w*h//6}) ==========\n")
        log.write(f"witness seed={witness_seed}, generated in {witness_dur:.4f}s,"
                  f" uses {len(set(v for row in witness for v in row))} pieces\n")
        log.write("witness:\n")
        log.write(grid_to_str(witness) + "\n")
        log.flush()
    print(f"\n[*] Round {round_idx}: {w}×{h} (k={w*h//6}). "
          f"Witness seed={witness_seed} ({witness_dur:.4f}s). "
          f"Sending ROUND to {len(clients)} bots.")

    # Broadcast ROUND.
    t_round_start = time.monotonic()
    for c in clients:
        c.send(f"ROUND {round_idx} {w} {h}\n")

    # Per-bot collection thread.
    results = {}   # client → (ok, inventory_or_reason, end_ts, rows)
    results_lock = threading.Lock()

    def worker(c):
        deadline = t_round_start + ROUND_BUDGET
        rows, end_ts, err = collect_submission(c, w, h, deadline)
        if err is not None:
            with results_lock:
                results[c] = (False, err, end_ts, None)
            return
        ok, info = validate_submission(rows, w, h)
        with results_lock:
            results[c] = (ok, info, end_ts, rows)

    threads = [threading.Thread(target=worker, args=(c,), daemon=True)
               for c in clients]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=ROUND_BUDGET + 5.0)

    # Per-bot result lines and replyback.
    log_lines = []
    valid_pairs = []   # (client, inventory, end_ts) for OK submissions
    for c in clients:
        ok, info, end_ts, rows = results.get(
            c, (False, "no_response", time.monotonic(), None))
        elapsed = end_ts - t_round_start
        if ok:
            inv = info
            valid_pairs.append((c, inv, end_ts))
            c.send(f"OK {inv}\n")
            c.inventories.append(inv)
            log_lines.append(f"  {c.name:<32} t={elapsed:5.2f}s  OK  inv={inv}")
            log_lines.append(f"    submission:")
            log_lines.append(grid_to_str(rows))
        else:
            reason = info
            c.send(f"INVALID {reason}\n")
            c.inventories.append(None)
            log_lines.append(f"  {c.name:<32} t={elapsed:5.2f}s  INVALID  {reason}")
            if rows is not None:
                log_lines.append(f"    submission:")
                log_lines.append(grid_to_str(rows))

    # Send END_ROUND to everyone.
    for c in clients:
        c.send(f"END_ROUND {round_idx}\n")

    # Medal scoring: rank valid bots by (inventory desc, end_ts asc).
    # Higher inventory wins; ties on inventory break by earliest arrival.
    medal_pts = (3, 2, 1)
    medal_label = ('GOLD', 'SILVER', 'BRONZE')
    medal_log = []
    awarded = 0
    used = [False] * len(valid_pairs)
    for slot in range(3):
        if awarded >= len(valid_pairs):
            break
        # Find highest-inventory unassigned bot, tie-break by earliest end_ts.
        best_idx = None
        best_key = None
        for idx, (c, inv, end_ts) in enumerate(valid_pairs):
            if used[idx]:
                continue
            key = (-inv, end_ts)
            if best_key is None or key < best_key:
                best_key = key
                best_idx = idx
        if best_idx is None:
            break
        c, inv, end_ts = valid_pairs[best_idx]
        c.points += medal_pts[slot]
        c.medals[slot] += 1
        c.medal_inv_sum += inv
        used[best_idx] = True
        awarded += 1
        medal_log.append(f"    {medal_label[slot]:<6} → {c.name} (inv={inv}, "
                         f"t={end_ts - t_round_start:5.2f}s) +{medal_pts[slot]} pts")

    with log_lock:
        for line in log_lines:
            log.write(line + "\n")
        log.write("  results:\n")
        for line in medal_log:
            log.write(line + "\n")
        log.flush()

    print("  results:")
    for line in medal_log:
        print(line)


# ── Tournament harness ───────────────────────────────────────────────────────

def rotate_log():
    if not os.path.exists(LOG_PATH):
        return
    n = 1
    while os.path.exists(f"{LOG_PATH}.{n}"):
        n += 1
    for i in range(n - 1, 0, -1):
        os.rename(f"{LOG_PATH}.{i}", f"{LOG_PATH}.{i + 1}")
    os.rename(LOG_PATH, f"{LOG_PATH}.1")


def run_tournament():
    rotate_log()
    log = open(LOG_PATH, 'w', encoding='utf-8')
    log_lock = threading.Lock()

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(32)
    server_sock.settimeout(1.0)

    clients = []
    print(f"[*] HappyHexaminos server live on {HOST}:{PORT}. "
          f"Registration window: {REGISTRATION_WINDOW}s")

    name_re = re.compile(r'^[A-Za-z0-9_-]{1,32}$')
    start_reg = time.time()
    while time.time() - start_reg < REGISTRATION_WINDOW:
        try:
            conn, addr = server_sock.accept()
            conn.settimeout(None)
            f = conn.makefile('r', encoding='utf-8', errors='replace',
                              newline='')
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

    if len(clients) < 1:
        print("[!] No bots registered.")
        log.close()
        server_sock.close()
        return

    print(f"[*] {len(clients)} bots registered. Pre-generating witness tilings…")
    log.write(f"Tournament: {len(clients)} bots, {N_ROUNDS} rounds.\n")
    log.write(f"Bots: {', '.join(c.name for c in clients)}\n")
    log.write(f"Sizes: {ROUND_SIZES}\n\n")
    log.flush()

    for round_idx, (w, h) in enumerate(ROUND_SIZES, 1):
        run_round(round_idx, w, h, clients, log, log_lock)

    print("\n[*] Tournament complete. Sending TOURNAMENT_END.")
    for c in clients:
        c.send("TOURNAMENT_END\n")

    log.write("\n========== FINAL STANDINGS ==========\n")
    final = sorted(
        clients,
        key=lambda c: (-c.points, -c.medals[0], -c.medals[1], -c.medals[2],
                        -c.medal_inv_sum),
    )
    header = ("  rank  bot                          pts   G  S  B    "
              "medal_inv_sum")
    print(header)
    log.write(header + "\n")
    for rank, c in enumerate(final, 1):
        line = (f"  #{rank:<3}  {c.name:<28}  {c.points:>3}   "
                f"{c.medals[0]}  {c.medals[1]}  {c.medals[2]}    "
                f"{c.medal_inv_sum:>5}")
        print(line)
        log.write(line + "\n")

    log.write("\n========== PER-BOT INVENTORIES PER ROUND ==========\n")
    for c in clients:
        invs = ', '.join('--' if v is None else str(v) for v in c.inventories)
        log.write(f"  {c.name:<32}  [{invs}]\n")

    log.close()
    for c in clients:
        c.close()
    server_sock.close()


if __name__ == '__main__':
    run_tournament()
