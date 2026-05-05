# bot author: Claude Opus 4.7
#!/usr/bin/env python3
# bot author: Claude Opus 4.7
"""SquishyWordBits tournament bot.

Strategy:
  1. Pre-build a binary trie of bit encodings for every dictionary word with
     >= 4 letters (only those have positive score = letters - 3). At each
     terminal node we keep the word with the most letters at that exact
     encoding (handles collisions like 'ba'/'c' both encoding to '10').
  2. Per round, traverse the trie from every offset in the bitstream to
     enumerate all matching (start, end, word, weight) candidates.
  3. Solve weighted interval scheduling via standard DP to pick the
     non-overlapping subset that maximizes total weight, then submit.

The DP is optimal for this exact problem (intervals on a line with weights).
"""
import array
import os
import socket
import sys


# Per-letter bit codes: format(i, 'b') is the minimum-bit binary representation
# (a=0, b=1, c=10, ..., z=11001), matching the spec exactly.
LETTER_CODES = [format(i, 'b') for i in range(26)]


def build_trie(dict_path):
    """Build a binary trie of word encodings for words with >= 4 letters.

    Node 0 is the root. A child index of 0 means "no child" (since the root
    cannot be its own child). Two parallel int arrays hold the two children;
    a separate dict holds terminal info only for the relatively few terminal
    nodes, keeping memory bounded.
    """
    left = array.array('i', [0])
    right = array.array('i', [0])
    left_append = left.append
    right_append = right.append
    terminals = {}  # node_idx -> (word, letter_count)

    with open(dict_path, 'r', encoding='ascii', errors='ignore') as f:
        for raw in f:
            word = raw.strip()
            n = len(word)
            if n < 4:
                continue  # 1-3 letter words have weight <= 0; never useful

            try:
                enc = ''.join(LETTER_CODES[ord(c) - 97] for c in word)
            except IndexError:
                # Out-of-range char (shouldn't happen for a clean a-z dict).
                continue

            node = 0
            for bit in enc:
                if bit == '0':
                    nxt = left[node]
                    if nxt == 0:
                        nxt = len(left)
                        left_append(0)
                        right_append(0)
                        left[node] = nxt
                    node = nxt
                else:
                    nxt = right[node]
                    if nxt == 0:
                        nxt = len(left)
                        left_append(0)
                        right_append(0)
                        right[node] = nxt
                    node = nxt

            cur = terminals.get(node)
            if cur is None or n > cur[1]:
                terminals[node] = (word, n)

    return left, right, terminals


def solve_round(bitstream, left, right, terminals):
    """Pick non-overlapping (word, offset) pairs maximizing sum of (letters - 3).

    Returns a list of (word, offset) tuples. Empty list is a valid submission
    (round score 0).
    """
    N = len(bitstream)
    if N == 0:
        return []

    # candidates_by_end[i] is a list of (start, weight, word) tuples for words
    # whose encoded interval is [start, i). We populate it lazily.
    candidates_by_end = [None] * (N + 1)
    terminals_get = terminals.get

    # For every offset, walk the trie until either we run out of bitstream
    # or there's no matching child. At every node visited along the path we
    # check if it's a terminal (encoding of some word) and record the candidate.
    for p in range(N):
        node = 0
        q = p
        while q < N:
            bit = bitstream[q]
            if bit == '0':
                node = left[node]
            elif bit == '1':
                node = right[node]
            else:
                break  # defensive: should not happen per spec
            if node == 0:
                break
            q += 1
            t = terminals_get(node)
            if t is not None:
                weight = t[1] - 3  # letters - 3 (>= 1 since we filtered to 4+)
                lst = candidates_by_end[q]
                if lst is None:
                    candidates_by_end[q] = [(p, weight, t[0])]
                else:
                    lst.append((p, weight, t[0]))

    # Weighted interval scheduling DP.
    # dp[i] = max total weight using bitstream[0:i].
    # take[i] = (start, word) of the candidate used at position i, or None
    #           if dp[i] = dp[i-1] (no improvement at i).
    dp = [0] * (N + 1)
    take = [None] * (N + 1)

    for i in range(1, N + 1):
        best = dp[i - 1]
        best_take = None
        cands = candidates_by_end[i]
        if cands is not None:
            for start, weight, word in cands:
                score = dp[start] + weight
                if score > best:  # strict: ties keep the simpler "skip" path
                    best = score
                    best_take = (start, word)
        dp[i] = best
        take[i] = best_take

    # Recover chosen words by walking take[] backwards.
    result = []
    i = N
    while i > 0:
        t = take[i]
        if t is None:
            i -= 1
        else:
            start, word = t
            result.append((word, start))
            i = start

    return result


def make_line_reader(sock):
    """Return a function that reads one '\\n'-terminated line, blocking as needed."""
    buf = bytearray()

    def read_line():
        while True:
            idx = buf.find(b'\n')
            if idx >= 0:
                line = bytes(buf[:idx]).decode('ascii', errors='replace')
                del buf[:idx + 1]
                return line
            data = sock.recv(65536)
            if not data:
                if buf:
                    line = bytes(buf).decode('ascii', errors='replace')
                    buf.clear()
                    return line
                return None
            buf.extend(data)

    return read_line


def find_dictionary():
    """Locate dictionary.txt: prefer cwd, fall back to script directory."""
    if os.path.exists('dictionary.txt'):
        return 'dictionary.txt'
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(script_dir, 'dictionary.txt')
    if os.path.exists(candidate):
        return candidate
    return None


def main():
    botname = os.environ.get('BOTNAME', '')
    if botname.endswith('\n'):
        botname = botname[:-1]
    if not botname:
        print("BOTNAME environment variable is not set", file=sys.stderr)
        sys.exit(1)

    dict_path = find_dictionary()
    if dict_path is None:
        print("dictionary.txt not found in cwd or script dir", file=sys.stderr)
        sys.exit(1)

    # Build the trie before connecting so we are ready the instant ROUND arrives.
    left, right, terminals = build_trie(dict_path)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock.sendall((botname + '\n').encode('ascii'))

    read_line = make_line_reader(sock)

    try:
        while True:
            line = read_line()
            if line is None:
                break

            if line.startswith('ROUND '):
                parts = line.split(' ', 2)
                if len(parts) < 3:
                    sock.sendall(b'END\n')
                    continue
                bitstream = parts[2]

                try:
                    submission = solve_round(bitstream, left, right, terminals)
                except Exception as e:
                    print(f"solve_round error: {e}", file=sys.stderr)
                    submission = []

                # Build the whole submission and send it in one syscall to
                # minimize transmit time (ties on round score are broken by
                # earliest submission timestamp at the server).
                out = []
                for word, offset in submission:
                    out.append('WORD ')
                    out.append(word.upper())
                    out.append(' ')
                    out.append(str(offset))
                    out.append('\n')
                out.append('END\n')
                sock.sendall(''.join(out).encode('ascii'))

            elif line == 'TOURNAMENT_END':
                break
            # Otherwise: OK <score> <count>, INVALID <reason>, END_ROUND <n> -
            # nothing to do, just loop and wait for the next ROUND.
    finally:
        try:
            sock.close()
        except Exception:
            pass


if __name__ == '__main__':
    main()