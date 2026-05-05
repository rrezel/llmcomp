# bot author: Kimi K2.6 (moonshotai/kimi-k2.6 via OpenRouter)
# bot author: assistant
import os
import socket


def build_trie(dict_path):
    ch0 = [-1]
    ch1 = [-1]
    best_len = [0]
    best_word = ['']

    letter_bits = []
    for i in range(26):
        bits = format(i, 'b')
        letter_bits.append([0 if c == '0' else 1 for c in bits])

    with open(dict_path, 'r', encoding='ascii') as f:
        for line in f:
            word = line.strip()
            if not word or len(word) < 4:
                continue
            node = 0
            for ch in word:
                for b in letter_bits[ord(ch) - 97]:
                    if b == 0:
                        nxt = ch0[node]
                        if nxt == -1:
                            nxt = len(ch0)
                            ch0[node] = nxt
                            ch0.append(-1)
                            ch1.append(-1)
                            best_len.append(0)
                            best_word.append('')
                        node = nxt
                    else:
                        nxt = ch1[node]
                        if nxt == -1:
                            nxt = len(ch0)
                            ch1[node] = nxt
                            ch0.append(-1)
                            ch1.append(-1)
                            best_len.append(0)
                            best_word.append('')
                        node = nxt
            lw = len(word)
            if lw > best_len[node]:
                best_len[node] = lw
                best_word[node] = word.upper()

    return ch0, ch1, best_len, best_word


def solve_round(bits, ch0, ch1, best_len, best_word):
    n = len(bits)
    bit_arr = [0 if c == '0' else 1 for c in bits]

    best = [0] * (n + 1)
    choice_end = [-1] * n
    choice_word = [''] * n

    ch0_local = ch0
    ch1_local = ch1
    bl = best_len
    bw = best_word
    b = bit_arr

    for p in range(n - 1, -1, -1):
        best_val = best[p + 1]
        best_end = -1
        best_w = ''
        node = 0
        for q in range(p, n):
            if b[q]:
                node = ch1_local[node]
            else:
                node = ch0_local[node]
            if node == -1:
                break
            lw = bl[node]
            if lw >= 4:
                end = q + 1
                val = (lw - 3) + best[end]
                if val > best_val:
                    best_val = val
                    best_end = end
                    best_w = bw[node]
        best[p] = best_val
        choice_end[p] = best_end
        choice_word[p] = best_w

    result = []
    p = 0
    while p < n:
        end = choice_end[p]
        if end != -1:
            result.append((choice_word[p], p))
            p = end
        else:
            p += 1
    return result


def main():
    botname = os.environ.get('BOTNAME', '').rstrip('\n')
    if not botname:
        return

    script_dir = os.path.dirname(os.path.abspath(__file__))
    dict_path = os.path.join(script_dir, 'dictionary.txt')
    if not os.path.exists(dict_path):
        dict_path = './dictionary.txt'

    ch0, ch1, best_len, best_word = build_trie(dict_path)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sock.connect(('localhost', 7474))
    sock.sendall((botname + '\n').encode('ascii'))

    fileobj = sock.makefile('rb')
    try:
        for raw in fileobj:
            line = raw.rstrip(b'\r\n').decode('ascii')
            if line.startswith('ROUND '):
                parts = line.split(' ', 2)
                if len(parts) < 3:
                    sock.sendall(b'END\n')
                    continue
                bits = parts[2]
                words = solve_round(bits, ch0, ch1, best_len, best_word)
                out = []
                for w, off in words:
                    out.append(f'WORD {w} {off}\n')
                out.append('END\n')
                sock.sendall(''.join(out).encode('ascii'))
            elif line == 'TOURNAMENT_END':
                break
    finally:
        try:
            sock.close()
        except Exception:
            pass


if __name__ == '__main__':
    main()
