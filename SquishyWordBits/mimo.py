# bot author: MiMo V2.5-Pro (xiaomi/mimo-v2.5-pro via OpenRouter)
# bot author: Claude 3.5 Sonnet
import os
import sys
import socket
import bisect
import array

def main():
    botname = os.environ.get('BOTNAME', '').strip()
    if not botname:
        sys.exit(1)

    with open('dictionary.txt') as f:
        words = [line.strip() for line in f if line.strip()]

    lenc = [format(i, 'b') for i in range(26)]

    trie = array.array('i', [-1, -1])
    twords = [None]

    for w in words:
        wl = len(w)
        if wl < 4:
            continue
        score = wl - 3
        node = 0
        for c in w:
            for b in lenc[ord(c) - 97]:
                bit = ord(b) - 48
                idx = node + node + bit
                child = trie[idx]
                if child == -1:
                    child = len(twords)
                    trie[idx] = child
                    trie.extend([-1, -1])
                    twords.append(None)
                node = child
        if twords[node] is None:
            twords[node] = []
        twords[node].append((w, score))

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock.sendall((botname + '\n').encode())

    buf = b''
    def readline():
        nonlocal buf
        while True:
            nl = buf.find(b'\n')
            if nl >= 0:
                line = buf[:nl].decode()
                buf = buf[nl + 1:]
                return line
            data = sock.recv(65536)
            if not data:
                return None
            buf += data

    def sendline(s):
        sock.sendall((s + '\n').encode())

    while True:
        line = readline()
        if line is None or line == 'TOURNAMENT_END':
            break
        if not line.startswith('ROUND '):
            continue

        _, _, bits = line.split(' ', 2)
        nbits = len(bits)
        ba = bytearray(ord(c) - 48 for c in bits)

        intervals = []
        tr = trie
        tw = twords
        for i in range(nbits):
            node = 0
            for j in range(i, nbits):
                child = tr[node + node + ba[j]]
                if child == -1:
                    break
                node = child
                wl = tw[node]
                if wl:
                    for word, score in wl:
                        intervals.append((j + 1, i, word, score))

        if intervals:
            intervals.sort()
            n = len(intervals)
            ends = [iv[0] for iv in intervals]
            dp = [0] * (n + 1)
            for k in range(n):
                end, start, word, score = intervals[k]
                p = bisect.bisect_right(ends, start, 0, k)
                dp[k + 1] = max(dp[k], score + dp[p])
            selected = []
            k = n
            while k > 0:
                if dp[k] == dp[k - 1]:
                    k -= 1
                else:
                    end, start, word, score = intervals[k - 1]
                    selected.append((word, start))
                    k = bisect.bisect_right(ends, start, 0, k - 1)
        else:
            selected = []

        for word, offset in selected:
            sendline(f'WORD {word.upper()} {offset}')
        sendline('END')

        readline()
        readline()

    sock.close()

if __name__ == '__main__':
    main()
