"""
SquishyWordBits Tournament Server.

10 solo rounds. Each round, the server generates a uniform random bitstream
of the round's specified length and broadcasts it. Each bot has 30 s
wall-clock to submit a set of `(word, offset)` pairs (one per line, ending
with the literal line `END`). The server validates each word: lowercased
form must be in the dictionary, encoding must equal `bits[offset:offset+L]`,
and the bit intervals must be pairwise disjoint. The round score is the
sum of `letters - 3` across accepted words; this can be negative.

Per-round ranking → points: 1st=10, 2nd=7, 3rd=5, 4th=3, 5th=1, 6th+=0.
Ties on round score break by earliest submission timestamp at the server.
"""
import os
import random
import re
import socket
import threading
import time

# ── Tournament configuration ─────────────────────────────────────────────────
HOST = 'localhost'
PORT = 7474
REGISTRATION_WINDOW = 10.0
ROUND_BUDGET = 30.0
N_ROUNDS = 10
LOG_PATH = 'results.log'
DICT_PATH = 'dictionary.txt'

# Bitstream length per round; monotonically growing within [10K, 20K], where
# bot differentiation actually appears. Stays inside the prompt's [200, 20000]
# bitstream bound.
ROUND_BITS = [10000, 11000, 12000, 13000, 14000, 15000, 16000, 17000, 18000, 20000]
assert len(ROUND_BITS) == N_ROUNDS
for i in range(len(ROUND_BITS) - 1):
    assert ROUND_BITS[i] < ROUND_BITS[i + 1]

POINTS_BY_RANK = (10, 7, 5, 3, 1)


# ── Encoding ─────────────────────────────────────────────────────────────────

LETTER_BITS = {chr(ord('a') + i): format(i, 'b') for i in range(26)}


def encode_word(word_lower):
    return ''.join(LETTER_BITS[c] for c in word_lower)


# ── Dictionary loading ───────────────────────────────────────────────────────

def load_dictionary(path):
    words = set()
    with open(path, encoding='utf-8') as f:
        for line in f:
            w = line.strip().lower()
            if w and all('a' <= ch <= 'z' for ch in w):
                words.add(w)
    return words


# ── Bitstream generation ─────────────────────────────────────────────────────

def build_bitstream(n_bits, seed):
    rng = random.Random(seed)
    return ''.join(rng.choice('01') for _ in range(n_bits))


# ── Submission parsing & validation ──────────────────────────────────────────

WORD_LINE_RE = re.compile(r'^WORD ([A-Z]+) (0|[1-9][0-9]*)$')


def validate_submission(lines, bitstream, dictionary):
    """
    lines: list[str], each one stripped of its trailing '\n'. The list is
        the bot's submission lines BEFORE the 'END' line (i.e., the lines
        the server expects to be `WORD <word> <offset>`).
    Returns (ok, info). On success, info is (round_score, word_count, list of
    (word, offset)). On failure, info is the INVALID reason token.
    """
    parsed = []   # list[(word_lower, offset, encoding, length_bits)]
    for i, line in enumerate(lines):
        m = WORD_LINE_RE.match(line)
        if not m:
            return False, f"malformed_{i}"
        word_upper = m.group(1)
        word = word_upper.lower()
        offset = int(m.group(2))
        if word not in dictionary:
            return False, f"not_in_dictionary_{i}"
        enc = encode_word(word)
        end = offset + len(enc)
        if end > len(bitstream) or bitstream[offset:end] != enc:
            return False, f"not_in_bitstream_{i}"
        parsed.append((word, offset, enc, len(enc)))

    # Pairwise overlap check (intervals are half-open [offset, offset+L)).
    for i in range(len(parsed)):
        ai, _, _, li = parsed[i][1], None, None, parsed[i][3]
        for j in range(i + 1, len(parsed)):
            aj, _, _, lj = parsed[j][1], None, None, parsed[j][3]
            # Use real values:
            si = parsed[i][1]; ei = si + parsed[i][3]
            sj = parsed[j][1]; ej = sj + parsed[j][3]
            if not (ei <= sj or ej <= si):
                return False, f"overlap_{i}_{j}"

    score = sum(len(w) - 3 for (w, _, _, _) in parsed)
    return True, (score, len(parsed), [(w, o) for (w, o, _, _) in parsed])


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
        self.round_scores = []          # per-round score (None if INVALID)
        self.round_word_counts = []     # per-round word count (None if INVALID)
        self.first_place_count = 0

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

def collect_submission(client, deadline):
    """Read lines from client until 'END' or deadline. Returns
    (word_lines, end_ts, error_or_None). word_lines is the list of lines
    received before END (each stripped of \n). On timeout returns
    (None, end_ts, 'timeout')."""
    word_lines = []
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None, time.monotonic(), "timeout"
        try:
            line = client.readline(timeout=remaining)
        except (socket.timeout, OSError):
            return None, time.monotonic(), "timeout"
        if line is None or line == '':
            return None, time.monotonic(), "timeout"
        s = line.rstrip('\n')
        if s == 'END':
            return word_lines, time.monotonic(), None
        word_lines.append(s)


def run_round(round_idx, n_bits, clients, dictionary, log, log_lock):
    seed = round_idx * 1000003
    bitstream = build_bitstream(n_bits, seed)

    with log_lock:
        log.write(f"\n========== ROUND {round_idx} (bits={n_bits}) ==========\n")
        log.write(f"seed={seed}\n")
        log.write(f"bitstream[:120]={bitstream[:120]}"
                  f"{'…' if n_bits > 120 else ''}\n")
        log.flush()
    print(f"\n[*] Round {round_idx}: {n_bits} bits, seed={seed}, "
          f"sending to {len(clients)} bots.")

    t_round_start = time.monotonic()
    for c in clients:
        c.send(f"ROUND {round_idx} {bitstream}\n")

    results = {}
    results_lock = threading.Lock()

    def worker(c):
        deadline = t_round_start + ROUND_BUDGET
        word_lines, end_ts, err = collect_submission(c, deadline)
        if err is not None:
            with results_lock:
                results[c] = (False, err, end_ts, None)
            return
        ok, info = validate_submission(word_lines, bitstream, dictionary)
        with results_lock:
            results[c] = (ok, info, end_ts, word_lines)

    threads = [threading.Thread(target=worker, args=(c,), daemon=True)
               for c in clients]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=ROUND_BUDGET + 5.0)

    log_lines = []
    valid_pairs = []   # (client, score, end_ts, word_lines)
    for c in clients:
        ok, info, end_ts, raw_lines = results.get(
            c, (False, "no_response", time.monotonic(), None))
        elapsed = end_ts - t_round_start
        if ok:
            score, word_count, placements = info
            valid_pairs.append((c, score, end_ts, raw_lines))
            c.send(f"OK {score} {word_count}\n")
            c.round_scores.append(score)
            c.round_word_counts.append(word_count)
            log_lines.append(
                f"  {c.name:<32} t={elapsed:5.2f}s  OK  "
                f"score={score:>4}  words={word_count}")
            for (w, o) in placements:
                log_lines.append(f"      WORD {w.upper()} {o}")
        else:
            c.send(f"INVALID {info}\n")
            c.round_scores.append(None)
            c.round_word_counts.append(None)
            sample = ' | '.join((raw_lines or [])[:3])
            log_lines.append(
                f"  {c.name:<32} t={elapsed:5.2f}s  INVALID  {info}  "
                f"raw_lines={sample!r}")

    for c in clients:
        c.send(f"END_ROUND {round_idx}\n")

    # Rank scoring: highest round_score wins; tie → earliest end_ts.
    valid_pairs.sort(key=lambda x: (-x[1], x[2]))
    rank_log = []
    for slot, (c, score, end_ts, _) in enumerate(valid_pairs):
        rank = slot + 1
        pts = POINTS_BY_RANK[slot] if slot < len(POINTS_BY_RANK) else 0
        c.points += pts
        if rank == 1:
            c.first_place_count += 1
        rank_log.append(f"    #{rank}  {c.name}  score={score:>4}  "
                        f"t={end_ts - t_round_start:5.2f}s  +{pts} pts")

    with log_lock:
        for line in log_lines:
            log.write(line + "\n")
        log.write("  results:\n")
        for line in rank_log:
            log.write(line + "\n")
        log.flush()

    print("  results:")
    for line in rank_log:
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

    dict_path = DICT_PATH
    if not os.path.isabs(dict_path):
        dict_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 dict_path)
    print(f"[*] Loading dictionary from {dict_path}")
    dictionary = load_dictionary(dict_path)
    print(f"[*] Dictionary: {len(dictionary)} words")

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(32)
    server_sock.settimeout(1.0)

    clients = []
    print(f"[*] SquishyWordBits server live on {HOST}:{PORT}. "
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

    print(f"[*] {len(clients)} bots registered.")
    log.write(f"Tournament: {len(clients)} bots, {N_ROUNDS} rounds.\n")
    log.write(f"Bots: {', '.join(c.name for c in clients)}\n")
    log.write(f"Bitstream lengths per round: {ROUND_BITS}\n\n")
    log.flush()

    for round_idx, n_bits in enumerate(ROUND_BITS, 1):
        run_round(round_idx, n_bits, clients, dictionary, log, log_lock)

    print("\n[*] Tournament complete. Sending TOURNAMENT_END.")
    for c in clients:
        c.send("TOURNAMENT_END\n")

    log.write("\n========== FINAL STANDINGS ==========\n")
    final = sorted(
        clients,
        key=lambda c: (-c.points, -c.first_place_count,
                       -sum(s for s in c.round_scores if s is not None)),
    )
    header = "  rank  bot                            pts   1sts  total_score"
    print(header)
    log.write(header + "\n")
    for rank, c in enumerate(final, 1):
        total = sum(s for s in c.round_scores if s is not None)
        line = (f"  #{rank:<3}  {c.name:<30}  {c.points:>3}    "
                f"{c.first_place_count:>3}    {total:>5}")
        print(line)
        log.write(line + "\n")

    log.write("\n========== PER-BOT ROUND SCORES ==========\n")
    for c in clients:
        scores = ', '.join('--' if s is None else str(s)
                           for s in c.round_scores)
        log.write(f"  {c.name:<32}  [{scores}]\n")

    log.close()
    for c in clients:
        c.close()
    server_sock.close()


if __name__ == '__main__':
    run_tournament()
