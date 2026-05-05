# bot author: DeepSeek V4-Pro (deepseek/deepseek-v4-pro via OpenRouter)
# bot author: Claude-3.5-Sonnet
import os
import socket
import sys
import bisect

def build_trie(dict_path):
    """Build a compact trie from dictionary words (len>=3)."""
    trie = [(0, 0, None, 0)]  # (child0, child1, word, weight)
    # precompute letter -> bit code
    letter_code = {}
    for i in range(26):
        letter = chr(ord('a') + i)
        letter_code[letter] = format(i, 'b')
    with open(dict_path, 'r') as f:
        for line in f:
            word = line.strip()
            if len(word) < 3:
                continue
            # encode word
            bits = ''.join(letter_code[ch] for ch in word)
            # insert into trie
            node = 0
            for bit in bits:
                if bit == '0':
                    child = trie[node][0]
                    if child == 0:
                        child = len(trie)
                        trie.append((0, 0, None, 0))
                        trie[node] = (child, trie[node][1], trie[node][2], trie[node][3])
                    node = child
                else:
                    child = trie[node][1]
                    if child == 0:
                        child = len(trie)
                        trie.append((0, 0, None, 0))
                        trie[node] = (trie[node][0], child, trie[node][2], trie[node][3])
                    node = child
            # store word and weight
            weight = len(word) - 3
            trie[node] = (trie[node][0], trie[node][1], word.upper(), weight)
    return trie

def find_intervals(bitstream, trie):
    """Return all (start, end, weight, word) intervals for words found in bitstream."""
    intervals = []
    n = len(bitstream)
    for i in range(n):
        node = 0
        for j in range(i, n):
            bit = bitstream[j]
            if bit == '0':
                next_node = trie[node][0]
            else:
                next_node = trie[node][1]
            if next_node == 0:
                break
            node = next_node
            word = trie[node][2]
            if word is not None:
                intervals.append((i, j + 1, trie[node][3], word))
    return intervals

def solve_intervals(intervals):
    """Weighted interval scheduling: max weight non-overlapping subset."""
    if not intervals:
        return []
    intervals.sort(key=lambda x: x[1])  # sort by end
    ends = [iv[1] for iv in intervals]
    n = len(intervals)
    dp = [0] * (n + 1)
    for i in range(1, n + 1):
        start, end, weight, word = intervals[i - 1]
        idx = bisect.bisect_right(ends, start) - 1
        if idx >= 0:
            val = weight + dp[idx + 1]
        else:
            val = weight
        dp[i] = max(dp[i - 1], val)
    # backtrack
    chosen = []
    i = n
    while i > 0:
        start, end, weight, word = intervals[i - 1]
        idx = bisect.bisect_right(ends, start) - 1
        if idx >= 0:
            if weight + dp[idx + 1] >= dp[i - 1]:
                chosen.append(intervals[i - 1])
                i = idx + 1
            else:
                i -= 1
        else:
            if weight >= dp[i - 1]:
                chosen.append(intervals[i - 1])
                i = 0
            else:
                i -= 1
    return chosen

def main():
    botname = os.environ.get('BOTNAME', '').strip()
    if not botname:
        print("BOTNAME not set", file=sys.stderr)
        sys.exit(1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sock.connect(('localhost', 7474))
    sock.sendall((botname + '\n').encode())

    # Build dictionary trie while waiting for ROUND (server buffers our BOTNAME)
    trie = build_trie('dictionary.txt')

    rf = sock.makefile('r', buffering=1)
    try:
        for line in rf:
            line = line.rstrip('\n')
            if line.startswith('ROUND'):
                parts = line.split(' ', 2)
                if len(parts) < 3:
                    continue
                bitstream = parts[2]
                intervals = find_intervals(bitstream, trie)
                chosen = solve_intervals(intervals)
                chosen.sort(key=lambda x: x[0])  # optional: sort by offset
                for start, end, weight, word in chosen:
                    sock.sendall(f"WORD {word} {start}\n".encode())
                sock.sendall(b"END\n")
            elif line == 'TOURNAMENT_END':
                break
    finally:
        sock.close()

if __name__ == '__main__':
    main()
