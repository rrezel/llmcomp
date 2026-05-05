# bot author: Meta Muse Spark
# bot author: Muse Spark
import os
import sys
import socket
import bisect

# ---------- dictionary preprocessing ----------
def load_dictionary(path='dictionary.txt'):
    codes = [
        '0','1','10','11','100','101','110','111',
        '1000','1001','1010','1011','1100','1101','1110','1111',
        '10000','10001','10010','10011','10100','10101','10110','10111','11000','11001'
    ]
    enc_map = {} # bitstring -> (WORD_UPPER, weight)
    try:
        with open(path, 'r', encoding='ascii') as f:
            for line in f:
                w = line.strip()
                if len(w) < 4:
                    continue
                if not w.isalpha() or not w.islower():
                    continue
                # encode
                enc = ''.join(codes[ord(ch) - 97] for ch in w)
                weight = len(w) - 3 # >0
                prev = enc_map.get(enc)
                if prev is None or weight > prev[1]:
                    enc_map[enc] = (w.upper(), weight)
    except FileNotFoundError:
        sys.stderr.write('dictionary.txt not found\n')
        sys.exit(1)

    lengths = sorted({len(k) for k in enc_map})
    min_len = lengths[0] if lengths else 0
    return enc_map, lengths, min_len

# ---------- solve one round ----------
def solve_round(bits, enc_map, lengths, min_len):
    n = len(bits)
    if n < min_len:
        return []

    matches = []
    get = enc_map.get
    # find all occurrences
    limit_start = n - min_len + 1
    for start in range(limit_start):
        rem = n - start
        # iterate possible lengths
        for l in lengths:
            if l > rem:
                break
            sub = bits[start:start+l]
            val = get(sub)
            if val:
                # val = (word, weight)
                matches.append((start, start + l, val[1], val[0]))

    if not matches:
        return []

    # weighted interval scheduling
    matches.sort(key=lambda x: (x[1], x[0]))
    starts = [m[0] for m in matches]
    ends = [m[1] for m in matches]
    weights = [m[2] for m in matches]
    words = [m[3] for m in matches]
    m = len(matches)

    p = [0] * m
    for i in range(m):
        j = bisect.bisect_right(ends, starts[i], 0, i) - 1
        p[i] = j

    dp = [0] * (m + 1)
    for i in range(1, m + 1):
        wi = weights[i-1]
        pi = p[i-1]
        include = wi + (dp[pi+1] if pi >= 0 else 0)
        exclude = dp[i-1]
        dp[i] = include if include > exclude else exclude

    selected = []
    i = m
    while i > 0:
        wi = weights[i-1]
        pi = p[i-1]
        include = wi + (dp[pi+1] if pi >= 0 else 0)
        if include > dp[i-1]:
            selected.append((words[i-1], starts[i-1]))
            i = pi + 1
        else:
            i -= 1
    selected.reverse()
    return selected

# ---------- main network loop ----------
def main():
    name = os.environ.get('BOTNAME', '')
    if not name:
        sys.exit(1)
    name = name.rstrip('\r\n')

    sock = socket.create_connection(('localhost', 7474))
    rfile = sock.makefile('rb')
    sock.sendall((name + '\n').encode('ascii'))

    enc_map, lengths, min_len = load_dictionary()

    while True:
        line_bytes = rfile.readline()
        if not line_bytes:
            break
        line = line_bytes.decode('ascii').rstrip('\n')
        if line.startswith('ROUND'):
            # ROUND <n> <bits>
            try:
                _, _, bits = line.split(' ', 2)
            except ValueError:
                bits = ''
            selected = solve_round(bits, enc_map, lengths, min_len)
            for word, offset in selected:
                sock.sendall(f'WORD {word} {offset}\n'.encode('ascii'))
            sock.sendall(b'END\n')
        elif line == 'TOURNAMENT_END':
            break
        else:
            # OK, INVALID, END_ROUND – just continue
            continue

    try:
        rfile.close()
    finally:
        sock.close()

if __name__ == '__main__':
    main()