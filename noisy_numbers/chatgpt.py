#!/usr/bin/env python3
import math
import socket
import sys
from collections import deque

HOST = "localhost"
PORT = 7474
BOT_NAME = "gpt54_bot"

DOTS = {
    1: (0.000, 0.000), 2: (0.197, 0.000), 3: (0.401, 0.000), 4: (0.602, 0.000),
    5: (0.803, 0.000), 6: (0.995, 0.003), 7: (0.000, 0.091), 8: (0.858, 0.070),
    9: (1.000, 0.091), 10: (0.725, 0.133), 11: (0.000, 0.182), 12: (0.593, 0.196),
    13: (1.000, 0.182), 14: (0.459, 0.260), 15: (0.000, 0.273), 16: (1.000, 0.273),
    17: (0.325, 0.324), 18: (0.000, 0.364), 19: (1.000, 0.364), 20: (0.194, 0.387),
    21: (0.000, 0.454), 22: (0.062, 0.450), 23: (1.000, 0.454), 24: (0.017, 0.511),
    25: (0.204, 0.512), 26: (0.394, 0.512), 27: (0.580, 0.511), 28: (0.768, 0.512),
    29: (0.976, 0.517), 30: (0.000, 0.545), 31: (1.000, 0.545), 32: (0.858, 0.585),
    33: (0.000, 0.636), 34: (0.725, 0.648), 35: (1.000, 0.636), 36: (0.000, 0.727),
    37: (0.593, 0.711), 38: (1.000, 0.727), 39: (0.459, 0.775), 40: (0.000, 0.818),
    41: (1.000, 0.818), 42: (0.325, 0.839), 43: (0.194, 0.902), 44: (0.000, 0.909),
    45: (1.000, 0.909), 46: (0.062, 0.965), 47: (0.000, 1.000), 48: (0.197, 1.000),
    49: (0.401, 1.000), 50: (0.602, 1.000), 51: (0.803, 1.000), 52: (1.000, 1.000),
}

DIGIT_STROKES = {
    0: [[1,2,3,4,5,6,9,13,16,19,23,29,31,35,38,41,45,52,51,50,49,48,47,44,40,36,33,30,24,21,18,15,11,7,1]],
    1: [[24,22,20,17,14,12,10,8,6,9,13,16,19,23,29,31,35,38,41,45,52]],
    2: [[1,2,3,4,5,6,9,13,16,19,23,29,32,34,37,39,42,43,46,47,48,49,50,51,52]],
    3: [[1,2,3,4,5,6,8,10,12,14,17,20,22,24,25,26,27,28,29,32,34,37,39,42,43,46,47]],
    4: [[1,7,11,15,18,21,24,25,26,27,28,29], [6,9,13,16,19,23,29,31,35,38,41,45,52]],
    5: [[6,5,4,3,2,1,7,11,15,18,21,24,25,26,27,28,29,31,35,38,41,45,52,51,50,49,48,47]],
    6: [[6,8,10,12,14,17,20,22,24], [24,30,33,36,40,44,47,48,49,50,51,52,45,41,38,35,31,29,28,27,26,25,24]],
    7: [[1,2,3,4,5,6,8,10,12,14,17,20,22,24,30,33,36,40,44,47]],
    8: [[1,2,3,4,5,6,9,13,16,19,23,29,31,35,38,41,45,52,51,50,49,48,47,44,40,36,33,30,24,21,18,15,11,7,1],
        [24,25,26,27,28,29]],
    9: [[24,21,18,15,11,7,1,2,3,4,5,6,9,13,16,19,23,29,28,27,26,25,24], [29,32,34,37,39,42,43,46,47]],
}

# Base layout from the statement.
BASE_CELL_W = 60.0
BASE_CELL_H = 100.0
BASE_GAP = 16.0

# Rendering/model parameters.
DOT_RADIUS_FRAC = 0.028
LINE_RADIUS_FRAC = 0.022
SAMPLE_STEP = 0.010

# Matching parameters.
ANGLE_CANDIDATES = [a * 0.5 for a in range(-20, 21)]   # -10 .. 10 deg
SCALE_CANDIDATES = [0.90 + i * 0.01 for i in range(21)]  # 0.90 .. 1.10

def recv_line(sock_file):
    line = sock_file.readline()
    if not line:
        return None
    return line.decode("ascii", "replace")

def parse_p3_ppm(data_bytes):
    text = data_bytes.decode("ascii", "replace")
    tokens = []
    for line in text.splitlines():
        if "#" in line:
            line = line[:line.index("#")]
        line = line.strip()
        if line:
            tokens.extend(line.split())
    if len(tokens) < 4 or tokens[0] != "P3":
        raise ValueError("not a P3 ppm")
    w = int(tokens[1])
    h = int(tokens[2])
    maxv = int(tokens[3])
    if maxv <= 0:
        raise ValueError("bad maxv")
    vals = list(map(int, tokens[4:]))
    if len(vals) != w * h * 3:
        raise ValueError("wrong rgb count")
    img = [[255] * w for _ in range(h)]
    k = 0
    for y in range(h):
        row = img[y]
        for x in range(w):
            r = vals[k]
            g = vals[k + 1]
            b = vals[k + 2]
            k += 3
            gray = (r + g + b) // 3
            row[x] = gray
    return w, h, img

def otsu_threshold(w, h, gray):
    hist = [0] * 256
    for row in gray:
        for v in row:
            hist[v] += 1
    total = w * h
    sum_all = sum(i * hist[i] for i in range(256))
    sum_b = 0
    w_b = 0
    var_max = -1.0
    threshold = 127
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        var_between = w_b * w_f * (m_b - m_f) * (m_b - m_f)
        if var_between > var_max:
            var_max = var_between
            threshold = t
    return threshold

def binarize(w, h, gray):
    t = otsu_threshold(w, h, gray)
    bw = [[1 if gray[y][x] <= t else 0 for x in range(w)] for y in range(h)]  # 1 = black
    return bw

def majority_filter(bw, radius=1):
    h = len(bw)
    w = len(bw[0])
    out = [[0] * w for _ in range(h)]
    for y in range(h):
        y0 = max(0, y - radius)
        y1 = min(h - 1, y + radius)
        for x in range(w):
            x0 = max(0, x - radius)
            x1 = min(w - 1, x + radius)
            total = 0
            cnt = 0
            for yy in range(y0, y1 + 1):
                row = bw[yy]
                for xx in range(x0, x1 + 1):
                    total += row[xx]
                    cnt += 1
            out[y][x] = 1 if total * 2 >= cnt else 0
    return out

def connected_components(bw, min_area=20):
    h = len(bw)
    w = len(bw[0])
    vis = [[False] * w for _ in range(h)]
    comps = []
    for y in range(h):
        for x in range(w):
            if bw[y][x] != 1 or vis[y][x]:
                continue
            q = deque([(x, y)])
            vis[y][x] = True
            pts = []
            minx = maxx = x
            miny = maxy = y
            while q:
                cx, cy = q.popleft()
                pts.append((cx, cy))
                if cx < minx: minx = cx
                if cx > maxx: maxx = cx
                if cy < miny: miny = cy
                if cy > maxy: maxy = cy
                for nx, ny in ((cx+1,cy),(cx-1,cy),(cx,cy+1),(cx,cy-1),(cx+1,cy+1),(cx-1,cy-1),(cx+1,cy-1),(cx-1,cy+1)):
                    if 0 <= nx < w and 0 <= ny < h and bw[ny][nx] == 1 and not vis[ny][nx]:
                        vis[ny][nx] = True
                        q.append((nx, ny))
            if len(pts) >= min_area:
                comps.append({
                    "pts": pts,
                    "area": len(pts),
                    "minx": minx, "maxx": maxx, "miny": miny, "maxy": maxy,
                    "w": maxx - minx + 1, "h": maxy - miny + 1,
                    "cx": sum(p[0] for p in pts) / len(pts),
                    "cy": sum(p[1] for p in pts) / len(pts),
                })
    return comps

def pca_angle(points):
    n = len(points)
    if n < 2:
        return 0.0
    mx = sum(x for x, _ in points) / n
    my = sum(y for _, y in points) / n
    sxx = syy = sxy = 0.0
    for x, y in points:
        dx = x - mx
        dy = y - my
        sxx += dx * dx
        syy += dy * dy
        sxy += dx * dy
    if abs(sxy) < 1e-9 and sxx >= syy:
        return 0.0
    ang = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
    deg = ang * 180.0 / math.pi
    while deg <= -90.0:
        deg += 180.0
    while deg > 90.0:
        deg -= 180.0
    if deg < -45.0:
        deg += 90.0
    if deg > 45.0:
        deg -= 90.0
    return deg

def estimate_global_angle_and_scale(bw):
    comps = connected_components(bw, min_area=30)
    tall = [c for c in comps if c["h"] > c["w"] * 1.1]
    if not tall:
        pts = []
        h = len(bw)
        w = len(bw[0])
        for y in range(h):
            row = bw[y]
            for x in range(w):
                if row[x]:
                    pts.append((x, y))
        angle = pca_angle(pts) if pts else 0.0
        scale = min(w / (6 * BASE_CELL_W + 5 * BASE_GAP), h / BASE_CELL_H)
        return angle, max(0.9, min(1.1, scale))
    tall.sort(key=lambda c: c["area"], reverse=True)
    tall = tall[:12]
    angles = [pca_angle(c["pts"]) for c in tall]
    angles.sort()
    angle = angles[len(angles)//2]
    hs = sorted(c["h"] for c in tall)
    est_h = hs[len(hs)//2]
    scale = est_h / BASE_CELL_H
    return angle, max(0.9, min(1.1, scale))

def black_prefix_sum(bw):
    h = len(bw)
    w = len(bw[0])
    ps = [[0] * (w + 1) for _ in range(h + 1)]
    for y in range(h):
        run = 0
        for x in range(w):
            run += bw[y][x]
            ps[y + 1][x + 1] = ps[y][x + 1] + run
    return ps

def rect_sum(ps, x0, y0, x1, y1):
    return ps[y1][x1] - ps[y0][x1] - ps[y1][x0] + ps[y0][x0]

def locate_code_band(bw, angle_deg):
    h = len(bw)
    w = len(bw[0])
    ps = black_prefix_sum(bw)

    rad = math.radians(-angle_deg)
    ca = math.cos(rad)
    sa = math.sin(rad)
    cx = (w - 1) * 0.5
    cy = (h - 1) * 0.5

    xs = []
    ys = []
    pts = []
    for y in range(h):
        row = bw[y]
        for x in range(w):
            if row[x]:
                dx = x - cx
                dy = y - cy
                xr = ca * dx - sa * dy
                yr = sa * dx + ca * dy
                pts.append((x, y, xr, yr))
                xs.append(xr)
                ys.append(yr)

    if not pts:
        return (0, 0, w, h)

    minxr = min(xs)
    maxxr = max(xs)
    minyr = min(ys)
    maxyr = max(ys)

    bins = 120
    yh = [0] * bins
    for _, _, _, yr in pts:
        idx = int((yr - minyr) / max(1e-9, maxyr - minyr) * (bins - 1))
        yh[idx] += 1

    best_l = 0
    best_r = bins - 1
    best_score = -1
    for l in range(bins):
        s = 0
        for r in range(l, bins):
            s += yh[r]
            if s > best_score and (r - l + 1) >= bins // 6:
                best_score = s
                best_l, best_r = l, r

    ylo = minyr + (maxyr - minyr) * best_l / bins
    yhi = minyr + (maxyr - minyr) * (best_r + 1) / bins

    sel = [(x, y, xr, yr) for (x, y, xr, yr) in pts if ylo <= yr <= yhi]
    xs2 = [p[2] for p in sel]
    ys2 = [p[3] for p in sel]
    minxr2 = min(xs2)
    maxxr2 = max(xs2)
    minyr2 = min(ys2)
    maxyr2 = max(ys2)

    corners = []
    for xr, yr in ((minxr2, minyr2), (maxxr2, minyr2), (maxxr2, maxyr2), (minxr2, maxyr2)):
        dx = ca * xr + sa * yr
        dy = -sa * xr + ca * yr
        x = dx + cx
        y = dy + cy
        corners.append((x, y))

    minx = max(0, int(math.floor(min(c[0] for c in corners))) - 4)
    maxx = min(w, int(math.ceil(max(c[0] for c in corners))) + 4)
    miny = max(0, int(math.floor(min(c[1] for c in corners))) - 4)
    maxy = min(h, int(math.ceil(max(c[1] for c in corners))) + 4)

    if maxx - minx < 20 or maxy - miny < 20:
        col_counts = [rect_sum(ps, x, 0, x + 1, h) for x in range(w)]
        xs_black = [i for i, c in enumerate(col_counts) if c > max(2, h // 25)]
        if xs_black:
            minx = max(0, min(xs_black) - 2)
            maxx = min(w, max(xs_black) + 3)
        row_counts = [rect_sum(ps, 0, y, w, y + 1) for y in range(h)]
        ys_black = [i for i, c in enumerate(row_counts) if c > max(2, w // 25)]
        if ys_black:
            miny = max(0, min(ys_black) - 2)
            maxy = min(h, max(ys_black) + 3)

    return (minx, miny, maxx, maxy)

def make_canvas(w, h, fill=0):
    return [[fill] * w for _ in range(h)]

def draw_disc(canvas, cx, cy, r):
    h = len(canvas)
    w = len(canvas[0])
    x0 = max(0, int(math.floor(cx - r)))
    x1 = min(w - 1, int(math.ceil(cx + r)))
    y0 = max(0, int(math.floor(cy - r)))
    y1 = min(h - 1, int(math.ceil(cy + r)))
    rr = r * r
    for y in range(y0, y1 + 1):
        dy = y - cy
        row = canvas[y]
        for x in range(x0, x1 + 1):
            dx = x - cx
            if dx * dx + dy * dy <= rr:
                row[x] = 1

def draw_segment(canvas, x1, y1, x2, y2, r):
    dist = math.hypot(x2 - x1, y2 - y1)
    steps = max(1, int(dist / max(0.5, SAMPLE_STEP * max(len(canvas), len(canvas[0])))))
    for i in range(steps + 1):
        t = i / steps
        x = x1 + (x2 - x1) * t
        y = y1 + (y2 - y1) * t
        draw_disc(canvas, x, y, r)

def render_digit(digit, cell_w, cell_h, with_dots=True):
    c = make_canvas(cell_w, cell_h, 0)
    dot_r = max(1.0, min(cell_w, cell_h) * DOT_RADIUS_FRAC)
    line_r = max(1.0, min(cell_w, cell_h) * LINE_RADIUS_FRAC)

    if with_dots:
        for idx in range(1, 53):
            x = DOTS[idx][0] * (cell_w - 1)
            y = DOTS[idx][1] * (cell_h - 1)
            draw_disc(c, x, y, dot_r)

    for stroke in DIGIT_STROKES[digit]:
        for a, b in zip(stroke, stroke[1:]):
            x1 = DOTS[a][0] * (cell_w - 1)
            y1 = DOTS[a][1] * (cell_h - 1)
            x2 = DOTS[b][0] * (cell_w - 1)
            y2 = DOTS[b][1] * (cell_h - 1)
            draw_segment(c, x1, y1, x2, y2, line_r)
    return c

def sample_rotated(bw, x, y, angle_deg):
    h = len(bw)
    w = len(bw[0])
    rad = math.radians(angle_deg)
    ca = math.cos(rad)
    sa = math.sin(rad)
    cx = (w - 1) * 0.5
    cy = (h - 1) * 0.5
    dx = x - cx
    dy = y - cy
    sx = ca * dx - sa * dy + cx
    sy = sa * dx + ca * dy + cy
    ix = int(round(sx))
    iy = int(round(sy))
    if 0 <= ix < w and 0 <= iy < h:
        return bw[iy][ix]
    return 0

def extract_patch_rotated(bw, bbox, angle_deg):
    minx, miny, maxx, maxy = bbox
    pw = maxx - minx
    ph = maxy - miny
    patch = make_canvas(pw, ph, 0)
    for y in range(ph):
        for x in range(pw):
            patch[y][x] = sample_rotated(bw, minx + x, miny + y, angle_deg)
    return patch

def resize_nn(src, new_w, new_h):
    h = len(src)
    w = len(src[0])
    dst = make_canvas(new_w, new_h, 0)
    for y in range(new_h):
        sy = min(h - 1, int(round((y / max(1, new_h - 1)) * (h - 1))))
        rowd = dst[y]
        rows = src[sy]
        for x in range(new_w):
            sx = min(w - 1, int(round((x / max(1, new_w - 1)) * (w - 1))))
            rowd[x] = rows[sx]
    return dst

def column_sums(img):
    h = len(img)
    w = len(img[0])
    sums = [0] * w
    for y in range(h):
        row = img[y]
        for x in range(w):
            sums[x] += row[x]
    return sums

def smooth_1d(arr, radius=2):
    n = len(arr)
    out = [0.0] * n
    for i in range(n):
        s = 0.0
        c = 0
        for j in range(max(0, i - radius), min(n, i + radius + 1)):
            s += arr[j]
            c += 1
        out[i] = s / c
    return out

def split_six_cells(img):
    h = len(img)
    w = len(img[0])
    cols = column_sums(img)
    cols = smooth_1d(cols, radius=3)
    target_cell = w / 6.0
    target_gap = max(4.0, w / (6 * BASE_CELL_W / BASE_GAP + 5))

    best = None
    for left in range(0, max(1, int(w * 0.15)) + 1, 2):
        for right in range(max(left + 6, int(w * 0.85)), w + 1, 2):
            total = right - left
            if total <= 0:
                continue
            cell = total / 6.0
            score = 0.0
            cuts = [left + i * cell for i in range(7)]
            for c in cuts[1:-1]:
                i = int(round(c))
                lo = max(0, i - 3)
                hi = min(w, i + 4)
                valley = min(cols[lo:hi]) if lo < hi else 0.0
                score += valley * 4.0
            for i in range(6):
                a = int(round(cuts[i]))
                b = int(round(cuts[i + 1]))
                a = max(0, min(w, a))
                b = max(0, min(w, b))
                if b > a:
                    mass = sum(cols[a:b])
                    score -= mass / max(1, b - a)
            score += abs(cell - target_cell) * 20.0
            if best is None or score < best[0]:
                best = (score, cuts)

    _, cuts = best
    cells = []
    for i in range(6):
        a = max(0, min(w, int(round(cuts[i]))))
        b = max(0, min(w, int(round(cuts[i + 1]))))
        if b <= a:
            b = min(w, a + 1)
        cell = [row[a:b] for row in img]
        cells.append(cell)
    return cells

def crop_tight(img, pad=2):
    h = len(img)
    w = len(img[0])
    xs = []
    ys = []
    for y in range(h):
        for x in range(w):
            if img[y][x]:
                xs.append(x)
                ys.append(y)
    if not xs:
        return img
    minx = max(0, min(xs) - pad)
    maxx = min(w, max(xs) + pad + 1)
    miny = max(0, min(ys) - pad)
    maxy = min(h, max(ys) + pad + 1)
    return [row[minx:maxx] for row in img[miny:maxy]]

def xor_score(a, b):
    h = min(len(a), len(b))
    w = min(len(a[0]), len(b[0]))
    mism = 0
    for y in range(h):
        ra = a[y]
        rb = b[y]
        for x in range(w):
            if ra[x] != rb[x]:
                mism += 1
    return mism / (w * h)

def overlap_score(obs, tmpl):
    h = min(len(obs), len(tmpl))
    w = min(len(obs[0]), len(tmpl[0]))
    inter = 0
    union = 0
    for y in range(h):
        ro = obs[y]
        rt = tmpl[y]
        for x in range(w):
            a = ro[x]
            b = rt[x]
            if a and b:
                inter += 1
            if a or b:
                union += 1
    if union == 0:
        return 1.0
    return 1.0 - inter / union

def digit_score(obs, digit, norm_w=72, norm_h=120):
    tmpl = render_digit(digit, norm_w, norm_h, with_dots=True)
    obs2 = resize_nn(obs, norm_w, norm_h)
    return xor_score(obs2, tmpl) * 0.55 + overlap_score(obs2, tmpl) * 0.45

def decode_cells(cells):
    ans = []
    for cell in cells:
        tight = crop_tight(cell, pad=1)
        best_d = None
        best_s = None
        for d in range(10):
            s = digit_score(tight, d)
            if best_s is None or s < best_s:
                best_s = s
                best_d = d
        ans.append(str(best_d))
    return "".join(ans)

def try_decode(bw):
    angle0, scale0 = estimate_global_angle_and_scale(bw)
    best = None

    for angle in sorted(ANGLE_CANDIDATES, key=lambda a: abs(a - angle0)):
        bbox = locate_code_band(bw, angle)
        patch = extract_patch_rotated(bw, bbox, angle)
        patch = majority_filter(patch, radius=1)
        patch = crop_tight(patch, pad=2)

        for scale in sorted(SCALE_CANDIDATES, key=lambda s: abs(s - scale0)):
            target_h = max(80, int(round(BASE_CELL_H * scale)))
            ph = len(patch)
            pw = len(patch[0])
            target_w = max(200, int(round(pw * (target_h / max(1, ph)))))
            norm = resize_nn(patch, target_w, target_h)
            cells = split_six_cells(norm)
            code = decode_cells(cells)

            conf = 0.0
            for i, cell in enumerate(cells):
                tight = crop_tight(cell, pad=1)
                best1 = 1e9
                best2 = 1e9
                for d in range(10):
                    s = digit_score(tight, d)
                    if s < best1:
                        best2 = best1
                        best1 = s
                    elif s < best2:
                        best2 = s
                conf += (best2 - best1)

            score = -conf
            if best is None or score < best[0]:
                best = (score, code)

    return best[1]

def read_round_ppm(sock_file):
    line = recv_line(sock_file)
    if line is None:
        return None, None
    if not line.startswith("ROUND "):
        raise RuntimeError(f"unexpected line: {line!r}")
    round_no = int(line.split()[1])

    line = recv_line(sock_file)
    if line is None or not line.startswith("SIZE "):
        raise RuntimeError(f"unexpected line: {line!r}")
    size = int(line.split()[1])

    data = sock_file.read(size)
    if data is None or len(data) != size:
        raise RuntimeError("short ppm read")
    return round_no, data

def solve_ppm(ppm_bytes):
    w, h, gray = parse_p3_ppm(ppm_bytes)
    bw = binarize(w, h, gray)
    bw = majority_filter(bw, radius=1)
    return try_decode(bw)

def run():
    with socket.create_connection((HOST, PORT), timeout=10.0) as sock:
        sock.settimeout(10.0)
        sock.sendall((BOT_NAME + "\n").encode("ascii"))
        sock_file = sock.makefile("rwb", buffering=0)

        while True:
            try:
                round_no, ppm = read_round_ppm(sock_file)
                if round_no is None:
                    return
                answer = solve_ppm(ppm)
                sock.sendall((answer + "\n").encode("ascii"))

                resp = recv_line(sock_file)
                if resp is None:
                    return
                resp = resp.strip()
                if resp == "CORRECT":
                    continue
                if resp.startswith("WRONG "):
                    continue
                if resp == "ELIMINATED":
                    return
                if resp.startswith("ROUND "):
                    raise RuntimeError("protocol desync")
            except (socket.timeout, TimeoutError):
                return
            except EOFError:
                return

if __name__ == "__main__":
    run()
