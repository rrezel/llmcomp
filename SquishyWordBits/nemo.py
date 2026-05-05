# bot author: Nemotron 3 Super (nvidia/nemotron-3-super-120b-a12b via OpenRouter)
import os
import socket
import bisect

# Letter to bit encoding (minimal binary representation of 0-indexed position)
_LETTER_TO_BITS = {chr(ord('a') + i): format(i, 'b') for i in range(26)}

class TrieNode:
    __slots__ = ('children', 'words')
    def __init__(self):
        self.children = {}   # maps '0' or '1' -> TrieNode
        self.words = []      # list of (word, weight, bitlen) for words ending here

def build_trie():
    """Load dictionary.txt and construct the encoding trie."""
    root = TrieNode()
    with open('dictionary.txt', 'r', encoding='ascii') as f:
        for line in f:
            word = line.strip()
            if not word:
                continue
            # encode word
            enc = ''.join(_LETTER_TO_BITS[ch] for ch in word)
            weight = len(word) - 3          # contribution to score
            node = root
            for b in enc:
                if b not in node.children:
                    node.children[b] = TrieNode()
                node = node.children[b]
            node.words.append((word, weight, len(enc)))
    return root

TRIE_ROOT = build_trie()

def find_intervals(bitstream):
    """
    Return list of tuples (start, end_exclusive, weight, word, original_index)
    for all dictionary word occurrences in bitstream with positive weight.
    """
    intervals = []
    n = len(bitstream)
    for i in range(n):
        node = TRIE_ROOT
        j = i
        while j < n:
            b = bitstream[j]
            if b not in node.children:
                break
            node = node.children[b]
            j += 1
            if node.words:
                for (w, weight, _) in node.words:
                    if weight > 0:          # ignore non‑positive contributions
                        intervals.append((i, j, weight, w, len(intervals)))
    return intervals

def select_intervals(intervals):
    """
    Weighted interval scheduling.
    Returns list of original indices of selected intervals (non‑overlapping, max total weight).
    """
    if not intervals:
        return []
    # Sort by end coordinate
    sorted_ints = sorted(intervals, key=lambda x: x[1])
    starts = [iv[0] for iv in sorted_ints]
    ends   = [iv[1] for iv in sorted_ints]
    weights = [iv[2] for iv in sorted_ints]
    orig_idx = [iv[4] for iv in sorted_ints]   # keep original index
    m = len(sorted_ints)

    # p[i] = index of rightmost interval that ends <= start_i
    p = [-1] * m
    for i in range(m):
        # search in ends[0:i]
        j = bisect.bisect_right(ends, starts[i], 0, i) - 1
        p[i] = j

    dp = [0] * (m + 1)      # dp[i] = best weight using first i intervals
    take = [False] * (m + 1) # whether interval i-1 is taken in optimal solution for prefix i
    for i in range(1, m + 1):
        incl = weights[i-1] + dp[p[i-1] + 1]
        excl = dp[i-1]
        if incl > excl:
            dp[i] = incl
            take[i] = True
        else:
            dp[i] = excl
            take[i] = False

    # Reconstruct solution
    selected = []
    i = m
    while i > 0:
        if take[i]:
            selected.append(orig_idx[i-1])
            i = p[i-1] + 1
        else:
            i -= 1
    selected.reverse()
    return selected

def main():
    botname = os.environ.get('BOTNAME')
    if not botname:
        return  # misconfigured

    host = 'localhost'
    port = 7474
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    # Handshake: send botname
    sock.sendall((botname + '\n').encode())
    file = sock.makefile('r', encoding='ascii', newline='\n')

    while True:
        line = file.readline()
        if not line:
            break  # connection closed
        line = line.rstrip('\n')
        if not line:
            continue
        if line.startswith('ROUND'):
            parts = line.split()
            if len(parts) < 3:
                continue
            bitstream = parts[2]
            intervals = find_intervals(bitstream)
            chosen = select_intervals(intervals)
            # Submit chosen words
            for idx in chosen:
                start, _, _, word, _ = intervals[idx]
                sock.sendall((f'WORD {word.upper()} {start}' + '\n').encode())
            sock.sendall(('END' + '\n').encode())
            # Server response
            resp = file.readline()
            if not resp:
                break
            resp = resp.rstrip('\n')
            # Expect END_ROUND next
            end_round = file.readline()
            if not end_round:
                break
            end_round = end_round.rstrip('\n')
            if end_round.startswith('TOURNAMENT_END'):
                break
        elif line.startswith('TOURNAMENT_END'):
            break
        # Other lines (e.g., END_ROUND) are ignored; they will be read as part of the flow above.

    sock.close()

if __name__ == '__main__':
    main()
