#!/usr/bin/env python3
import math
import socket
import sys
from typing import List, Tuple, Dict, Iterable

# ------------------------------------------------------------
# Geometry & helpers
# ------------------------------------------------------------

Dot = Tuple[float, float]
Segment = Tuple[int, int]

DOTS: List[Dot] = [
    (0.000, 0.000), (0.197, 0.000), (0.401, 0.000),
    (0.602, 0.000), (0.803, 0.000), (0.995, 0.003),
    (0.000, 0.091), (0.858, 0.070), (1.000, 0.091),
    (0.725, 0.133), (0.000, 0.182), (0.593, 0.196),
    (1.000, 0.182), (0.459, 0.260), (0.000, 0.273),
    (1.000, 0.273), (0.325, 0.324), (0.000, 0.364),
    (1.000, 0.364), (0.194, 0.387), (0.000, 0.454),
    (0.062, 0.450), (1.000, 0.454), (0.017, 0.511),
    (0.204, 0.512), (0.394, 0.512), (0.580, 0.511),
    (0.768, 0.512), (0.976, 0.517), (0.000, 0.545),
    (1.000, 0.545), (0.858, 0.585), (0.000, 0.636),
    (0.725, 0.648), (1.000, 0.636), (0.000, 0.727),
    (0.593, 0.711), (1.000, 0.727), (0.459, 0.775),
    (0.000, 0.818), (1.000, 0.818), (0.325, 0.839),
    (0.194, 0.902), (0.000, 0.909), (1.000, 0.909),
    (0.062, 0.965), (0.000, 1.000), (0.197, 1.000),
    (0.401, 1.000), (0.602, 1.000), (0.803, 1.000),
    (1.000, 1.000),
]
# Convert to 0-based indices internally
DOTS = DOTS  # already fine, but note digit patterns are 1-based

def seq_to_segments(seq: List[int]) -> List[Segment]:
    return [(seq[i] - 1, seq[i + 1] - 1) for i in range(len(seq) - 1)]

DIGIT_STROKES_RAW: Dict[str, List[List[int]]] = {
    "0": [[1, 2, 3, 4, 5, 6, 9, 13, 16, 19, 23, 29, 31, 35, 38, 41, 45, 52,
           51, 50, 49, 48, 47, 44, 40, 36, 33, 30, 24, 21, 18, 15, 11, 7, 1]],
    "1": [[24, 22, 20, 17, 14, 12, 10, 8, 6, 9, 13, 16, 19, 23, 29, 31,
           35, 38, 41, 45, 52]],
    "2": [[1, 2, 3, 4, 5, 6, 9, 13, 16, 19, 23, 29, 32, 34, 37, 39, 42, 43,
           46, 47, 48, 49, 50, 51, 52]],
    "3": [[1, 2, 3, 4, 5, 6, 8, 10, 12, 14, 17, 20, 22, 24, 25, 26, 27, 28,
           29, 32, 34, 37, 39, 42, 43, 46, 47]],
    "4": [
        [1, 7, 11, 15, 18, 21, 24, 25, 26, 27, 28, 29],
        [6, 9, 13, 16, 19, 23, 29, 31, 35, 38, 41, 45, 52],
    ],
    "5": [[6, 5, 4, 3, 2, 1, 7, 11, 15, 18, 21, 24, 25, 26, 27, 28, 29, 31,
           35, 38, 41, 45, 52, 51, 50, 49, 48, 47]],
    "6": [
        [6, 8, 10, 12, 14, 17, 20, 22, 24],
        [24, 30, 33, 36, 40, 44, 47, 48, 49, 50, 51, 52, 45, 41, 38, 35, 31,
         29, 28, 27, 26, 25, 24],
    ],
    "7": [[1, 2, 3, 4, 5, 6, 8, 10, 12, 14, 17, 20, 22, 24, 30, 33, 36, 40,
           44, 47]],
    "8": [
        [1, 2, 3, 4, 5, 6, 9, 13, 16, 19, 23, 29, 31, 35, 38, 41, 45, 52, 51,
         50, 49, 48, 47, 44, 40, 36, 33, 30, 24, 21, 18, 15, 11, 7, 1],
        [24, 25, 26, 27, 28, 29],
    ],
    "9": [
        [24, 21, 18, 15, 11, 7, 1, 2, 3, 4, 5, 6, 9, 13, 16, 19, 23, 29, 28,
         27, 26, 25, 24],
        [29, 32, 34, 37, 39, 42, 43, 46, 47],
    ],
}

DIGIT_SEGMENTS: Dict[str, List[Segment]] = {}
for d, strokes in DIGIT_STROKES_RAW.items():
    segs: List[Segment] = []
    for seq in strokes:
        segs.extend(seq_to_segments(seq))
    DIGIT_SEGMENTS[d] = segs

def dot_to_pixel(
    dot: Dot, bbox: Tuple[int, int, int, int]
) -> Tuple[float, float]:
    x0, y0, x1, y1 = bbox
    return (x0 + dot[0] * (x1 - x0), y0 + dot[1] * (y1 - y0))

# ------------------------------------------------------------
# PPM parsing & basic image ops
# ------------------------------------------------------------

def parse_ppm_p3(data: str) -> Tuple[int, int, List[int]]:
    tokens = []
    for line in data.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for tok in line.split():
            tokens.append(tok)
    if tokens[0] != "P3":
        raise ValueError("Not a P3 PPM")
    w = int(tokens[1])
    h = int(tokens[2])
    maxv = int(tokens[3])
    if maxv != 255:
        raise ValueError("Expected maxval 255")
    vals = list(map(int, tokens[4:4 + 3 * w * h]))
    if len(vals) != 3 * w * h:
        raise ValueError("PPM size mismatch")
    return w, h, vals

def rgb_to_bw_mask(
    w: int, h: int, vals: List[int], threshold: int = 128
) -> List[int]:
    mask = [0] * (w * h)
    for i in range(w * h):
        r, g, b = vals[3 * i], vals[3 * i + 1], vals[3 * i + 2]
        lum = (r + g + b) // 3
        mask[i] = 1 if lum < threshold else 0
    return mask

def rotate_point(x: float, y: float, cx: float, cy: float, ang: float) -> Tuple[float, float]:
    s, c = math.sin(ang), math.cos(ang)
    x -= cx
    y -= cy
    xr = x * c - y * s
    yr = x * s + y * c
    return xr + cx, yr + cy

def get_pixel(mask: List[int], w: int, h: int, x: int, y: int) -> int:
    if x < 0 or y < 0 or x >= w or y >= h:
        return 0
    return mask[y * w + x]

def rotate_image(mask: List[int], w: int, h: int, ang_deg: float) -> Tuple[List[int], int, int]:
    ang = math.radians(ang_deg)
    # compute bounds of rotated image
    corners = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    rx, ry = [], []
    for x, y in corners:
        xx, yy = rotate_point(x, y, cx, cy, ang)
        rx.append(xx)
        ry.append(yy)
    minx, maxx = min(rx), max(rx)
    miny, maxy = min(ry), max(ry)
    nw = int(math.ceil(maxx - minx + 1))
    nh = int(math.ceil(maxy - miny + 1))
    nmask = [0] * (nw * nh)
    ncx, ncy = (nw - 1) / 2.0, (nh - 1) / 2.0
    for y in range(nh):
        for x in range(nw):
            # map back
            ox, oy = rotate_point(x, y, ncx, ncy, -ang)
            ox = int(round(ox - (ncx - cx)))
            oy = int(round(oy - (ncy - cy)))
            nmask[y * nw + x] = get_pixel(mask, w, h, ox, oy)
    return nmask, nw, nh

# ------------------------------------------------------------
# Deskew & segmentation
# ------------------------------------------------------------

def deskew(mask: List[int], w: int, h: int) -> Tuple[List[int], int, int]:
    # search angle -10..10
    best_score = -1
    best = (mask, w, h)
    for ang in range(-10, 11, 2):
        rmask, rw, rh = rotate_image(mask, w, h, ang)
        # score: vertical alignment of black pixels
        col_counts = [0] * rw
        for y in range(rh):
            row = y * rw
            for x in range(rw):
                col_counts[x] += rmask[row + x]
        score = sum(c * c for c in col_counts)
        if score > best_score:
            best_score = score
            best = (rmask, rw, rh)
    return best

def find_vertical_segments(mask: List[int], w: int, h: int, parts: int = 6) -> List[Tuple[int, int]]:
    col_counts = [0] * w
    for y in range(h):
        row = y * w
        for x in range(w):
            col_counts[x] += mask[row + x]
    # smooth counts
    sm = [0] * w
    for x in range(w):
        s = 0
        for dx in (-1, 0, 1):
            xx = x + dx
            if 0 <= xx < w:
                s += col_counts[xx]
        sm[x] = s
    # threshold to find gaps (between digits)
    maxc = max(sm) if sm else 1
    gap_thresh = maxc * 0.1
    in_gap = sm[0] < gap_thresh
    gaps = []
    start = 0
    for x in range(w):
        g = sm[x] < gap_thresh
        if g and not in_gap:
            # start of gap
            in_gap = True
            start = x
        elif not g and in_gap:
            in_gap = False
            gaps.append((start, x))
    if in_gap:
        gaps.append((start, w - 1))
    # deduce segments between gaps
    boundaries = [0]
    for g0, g1 in gaps:
        mid = (g0 + g1) // 2
        boundaries.append(mid)
    boundaries.append(w)
    segs = []
    for i in range(len(boundaries) - 1):
        a, b = boundaries[i], boundaries[i + 1]
        if b - a > 5:  # ignore tiny segments
            segs.append((a, b))
    # if we did not find 6, fallback to equal segmentation
    if len(segs) != parts:
        segs = []
        step = w / parts
        for i in range(parts):
            a = int(round(i * step))
            b = int(round((i + 1) * step))
            segs.append((a, b))
    return segs

def bbox_for_segment(
    mask: List[int], w: int, h: int, x0: int, x1: int
) -> Tuple[int, int, int, int]:
    y_top, y_bot = None, None
    for y in range(h):
        for x in range(x0, x1):
            if mask[y * w + x]:
                y_top = y
                break
        if y_top is not None:
            break
    for y in range(h - 1, -1, -1):
        for x in range(x0, x1):
            if mask[y * w + x]:
                y_bot = y
                break
        if y_bot is not None:
            break
    if y_top is None:
        y_top, y_bot = 0, h - 1
    return x0, y_top, x1 - 1, y_bot

# ------------------------------------------------------------
# Recognizing a single digit cell
# ------------------------------------------------------------

def sample_line(mask: List[int], w: int, h: int,
                p0: Tuple[float, float], p1: Tuple[float, float],
                samples: int = 40) -> float:
    cnt = 0
    for i in range(samples):
        t = (i + 0.5) / samples
        x = int(round(p0[0] * (1 - t) + p1[0] * t))
        y = int(round(p0[1] * (1 - t) + p1[1] * t))
        if 0 <= x < w and 0 <= y < h and mask[y * w + x]:
            cnt += 1
    return cnt / samples

def recognize_digit(mask: List[int], w: int, h: int,
                    cell_bbox: Tuple[int, int, int, int]) -> str:
    x0, y0, x1, y1 = cell_bbox
    cw = x1 - x0 + 1
    ch = y1 - y0 + 1
    # dot pixel positions
    dot_px = [dot_to_pixel(d, (x0, y0, x1, y1)) for d in DOTS]
    # precompute samples for all possible segments
    seg_strength: Dict[Segment, float] = {}
    for d, segs in DIGIT_SEGMENTS.items():
        for seg in segs:
            if seg in seg_strength:
                continue
            a, b = seg
            p0 = dot_px[a]
            p1 = dot_px[b]
            strength = sample_line(mask, w, h, p0, p1, samples=30)
            seg_strength[seg] = strength

    # classify by comparing template segments
    best_d = "0"
    best_score = float("inf")
    for d, segs in DIGIT_SEGMENTS.items():
        # active segments: those with strength above threshold
        # choose threshold relative to max in this cell
        vals = [seg_strength[s] for s in segs]
        if not vals:
            continue
        vmax = max(vals)
        thr = max(0.2, vmax * 0.5)
        # define bitset of all candidate segments used by any digit
        # but we only need distance among template segs
        score = 0.0
        for seg, v in seg_strength.items():
            in_template = seg in segs
            active = v >= thr
            if in_template and not active:
                score += 1.0
            elif not in_template and active:
                score += 0.5
        if score < best_score:
            best_score = score
            best_d = d
    return best_d

def recognize_six(mask: List[int], w: int, h: int) -> str:
    mask, w, h = deskew(mask, w, h)
    segments = find_vertical_segments(mask, w, h, 6)
    digits = []
    for (sx, ex) in segments:
        bbox = bbox_for_segment(mask, w, h, sx, ex)
        digits.append(recognize_digit(mask, w, h, bbox))
    return "".join(digits)

# ------------------------------------------------------------
# TCP client
# ------------------------------------------------------------

def recv_until(sock: socket.socket, delim: bytes) -> bytes:
    data = b""
    while not data.endswith(delim):
        chunk = sock.recv(1)
        if not chunk:
            break
        data += chunk
    return data

def recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf

def main():
    host = "localhost"
    port = 7474
    bot_name = "nemotron_super\n"

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    s.sendall(bot_name.encode("ascii"))

    s.settimeout(9.0)

    try:
        while True:
            line = recv_until(s, b"\n")
            if not line:
                break
            if not line.startswith(b"ROUND"):
                # may be final message
                sys.stderr.write(line.decode("ascii", "ignore"))
                break
            # read SIZE
            size_line = recv_until(s, b"\n")
            if not size_line.startswith(b"SIZE"):
                break
            parts = size_line.strip().split()
            size = int(parts[1])
            ppm_bytes = recv_exact(s, size)
            ppm_text = ppm_bytes.decode("ascii", "ignore")
            w, h, vals = parse_ppm_p3(ppm_text)
            mask = rgb_to_bw_mask(w, h, vals)
            code = recognize_six(mask, w, h)
            s.sendall((code + "\n").encode("ascii"))
            # read feedback
            resp = recv_until(s, b"\n")
            if not resp:
                break
            if resp.startswith(b"ELIMINATED"):
                break
            # else CORRECT or WRONG; continue
    finally:
        s.close()

if __name__ == "__main__":
    main()
