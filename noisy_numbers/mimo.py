#!/usr/bin/env python3
import socket
import math

DOTS = [
    (0.000,0.000),(0.197,0.000),(0.401,0.000),(0.602,0.000),(0.803,0.000),(0.995,0.003),
    (0.000,0.091),(0.858,0.070),(1.000,0.091),(0.725,0.133),(0.000,0.182),(0.593,0.196),
    (1.000,0.182),(0.459,0.260),(0.000,0.273),(1.000,0.273),(0.325,0.324),(0.000,0.364),
    (1.000,0.364),(0.194,0.387),(0.000,0.454),(0.062,0.450),(1.000,0.454),(0.017,0.511),
    (0.204,0.512),(0.394,0.512),(0.580,0.511),(0.768,0.512),(0.976,0.517),(0.000,0.545),
    (1.000,0.545),(0.858,0.585),(0.000,0.636),(0.725,0.648),(1.000,0.636),(0.000,0.727),
    (0.593,0.711),(1.000,0.727),(0.459,0.775),(0.000,0.818),(1.000,0.818),(0.325,0.839),
    (0.194,0.902),(0.000,0.909),(1.000,0.909),(0.062,0.965),(0.000,1.000),(0.197,1.000),
    (0.401,1.000),(0.602,1.000),(0.803,1.000),(1.000,1.000),
]

STROKES = [
    [[1,2,3,4,5,6,9,13,16,19,23,29,31,35,38,41,45,52,51,50,49,48,47,44,40,36,33,30,24,21,18,15,11,7,1]],
    [[24,22,20,17,14,12,10,8,6,9,13,16,19,23,29,31,35,38,41,45,52]],
    [[1,2,3,4,5,6,9,13,16,19,23,29,32,34,37,39,42,43,46,47,48,49,50,51,52]],
    [[1,2,3,4,5,6,8,10,12,14,17,20,22,24,25,26,27,28,29,32,34,37,39,42,43,46,47]],
    [[1,7,11,15,18,21,24,25,26,27,28,29],[6,9,13,16,19,23,29,31,35,38,41,45,52]],
    [[6,5,4,3,2,1,7,11,15,18,21,24,25,26,27,28,29,31,35,38,41,45,52,51,50,49,48,47]],
    [[6,8,10,12,14,17,20,22,24],[24,30,33,36,40,44,47,48,49,50,51,52,45,41,38,35,31,29,28,27,26,25,24]],
    [[1,2,3,4,5,6,8,10,12,14,17,20,22,24,30,33,36,40,44,47]],
    [[1,2,3,4,5,6,9,13,16,19,23,29,31,35,38,41,45,52,51,50,49,48,47,44,40,36,33,30,24,21,18,15,11,7,1],
     [24,25,26,27,28,29]],
    [[24,21,18,15,11,7,1,2,3,4,5,6,9,13,16,19,23,29,28,27,26,25,24],
     [29,32,34,37,39,42,43,46,47]],
]


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(15)
    sock.connect(('localhost', 7474))
    sock.sendall(b'mimo_bot\n')

    try:
        while True:
            line = b''
            while not line.endswith(b'\n'):
                c = sock.recv(1)
                if not c:
                    return
                line += c
            line = line.decode().strip()
            if not line.startswith('ROUND'):
                break
            print(line)

            size_line = b''
            while not size_line.endswith(b'\n'):
                c = sock.recv(1)
                if not c:
                    return
                size_line += c
            total = int(size_line.decode().strip().split()[1])

            data = b''
            while len(data) < total:
                chunk = sock.recv(min(65536, total - len(data)))
                if not chunk:
                    return
                data += chunk
            data = data[:total]

            gray, h, w = parse_ppm(data)
            dark = find_dark(gray, h, w)
            if not dark:
                sock.sendall(b'000000\n')
                r = b''
                while not r.endswith(b'\n'):
                    c = sock.recv(1)
                    if not c:
                        return
                    r += c
                print(r.decode().strip())
                continue

            angle = detect_angle(dark)
            rotated = derotate(dark, angle, h, w)

            xs = [p[0] for p in rotated]
            ys = [p[1] for p in rotated]
            px = max(5, int((max(xs) - min(xs)) * 0.05))
            py = max(5, int((max(ys) - min(ys)) * 0.15))
            x1, x2 = min(xs) - px, max(xs) + px
            y1, y2 = min(ys) - py, max(ys) + py
            gw, gh = x2 - x1, y2 - y1
            if gw < 1 or gh < 1:
                sock.sendall(b'000000\n')
                r = b''
                while not r.endswith(b'\n'):
                    c = sock.recv(1)
                    if not c:
                        return
                    r += c
                print(r.decode().strip())
                continue

            dark_set = set(rotated)
            cw = (gw - 80) / 6.0

            answer = ''
            for i in range(6):
                cx1 = x1 + i * (cw + 16)
                cell = (cx1, y1, cx1 + cw, y2)
                best_d, best_s = 0, -1
                for d in range(10):
                    s = score(d, cell, dark_set)
                    if s > best_s:
                        best_s, best_d = s, d
                answer += str(best_d)

            print(f'  -> {answer}')
            sock.sendall((answer + '\n').encode())

            resp = b''
            while not resp.endswith(b'\n'):
                c = sock.recv(1)
                if not c:
                    return
                resp += c
            print(f'  {resp.decode().strip()}')
    finally:
        sock.close()


def parse_ppm(data):
    parts = data.split()
    w, h = int(parts[1]), int(parts[2])
    vals = list(map(int, parts[4:]))
    gray = []
    idx = 0
    for _ in range(h):
        row = []
        for _ in range(w):
            row.append(int(0.299 * vals[idx] + 0.587 * vals[idx+1] + 0.114 * vals[idx+2]))
            idx += 3
        gray.append(row)
    return gray, h, w


def find_dark(gray, h, w):
    return [(r, c) for r in range(h) for c in range(w) if gray[r][c] < 128]


def detect_angle(dark):
    bins = [0.0] * 48
    for r, c in dark:
        d = math.hypot(c, r)
        if d > 1:
            a = math.degrees(math.atan2(r, c))
            if -12 <= a <= 12:
                bins[int((a + 12) * 2)] += d
    s = [0.0] * 48
    for i in range(48):
        for j in range(max(0, i-2), min(48, i+3)):
            s[i] += bins[j]
    return (s.index(max(s)) / 2.0) - 12.0


def derotate(dark, angle, h, w):
    rad = math.radians(-angle)
    co, si = math.cos(rad), math.sin(rad)
    cy, cx = h / 2.0, w / 2.0
    return [(int(round((r-cy)*si + (c-cx)*co + cx)),
             int(round((r-cy)*co - (c-cx)*si + cy))) for r, c in dark]


def score(digit, cell, dark):
    x1, y1, x2, y2 = cell
    cw, ch = x2 - x1, y2 - y1
    if cw < 1 or ch < 1:
        return 0
    total = 0
    for stroke in STROKES[digit]:
        sc = 0
        segs = 0
        for i in range(len(stroke) - 1):
            ax, ay = DOTS[stroke[i]-1]
            bx, by = DOTS[stroke[i+1]-1]
            px1, py1 = x1 + ax*cw, y1 + ay*ch
            px2, py2 = x1 + bx*cw, y1 + by*ch
            dist = math.hypot(px2-px1, py2-py1)
            n = max(int(dist * 2), 4)
            for j in range(n + 1):
                t = j / n
                if (int(round(py1 + t*(py2-py1))), int(round(px1 + t*(px2-px1)))) in dark:
                    sc += 1
            segs += 1
        total += sc if sc >= segs * 3 else 0
    return total


if __name__ == '__main__':
    main()
