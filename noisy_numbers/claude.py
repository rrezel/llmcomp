#!/usr/bin/env python3
"""Soviet Postal Code Reader Bot - Tournament Client

Pipeline: parse PPM → Otsu threshold → binarize → erode(mn=5) + dilate
(removes dot grid, keeps thick strokes) → PCA rotation → tight bounds →
equal 6-cell division → resize → NCC against synthetic templates.
"""
import socket
import sys
import math

# =============================================================================
# Synthetic template generation from geometric segment definitions
# =============================================================================
TW, TH = 24, 36

_M = 1
_TL = (_M, _M); _TR = (TW-1-_M, _M)
_ML = (_M, TH//2); _MR = (TW-1-_M, TH//2)
_BL = (_M, TH-1-_M); _BR = (TW-1-_M, TH-1-_M)

_SEG_EP = {
    'top': (_TL, _TR), 'bot': (_BL, _BR),
    'lt': (_TL, _ML), 'lb': (_ML, _BL),
    'rt': (_TR, _MR), 'rb': (_MR, _BR),
    'mid': (_ML, _MR),
    'dt': (_TR, _ML),   # diagonal: top-right → mid-left
    'db': (_MR, _BL),   # diagonal: mid-right → bot-left
}

_DIGIT_SEGS = {
    0: ['top','bot','lt','lb','rt','rb'],
    1: ['rt','rb','dt'],
    2: ['top','bot','rt','db'],
    3: ['top','mid','dt','db'],
    4: ['lt','rt','rb','mid'],
    5: ['top','bot','lt','rb','mid'],
    6: ['bot','lb','rb','mid','dt'],
    7: ['top','lb','dt'],
    8: ['top','bot','lt','lb','rt','rb','mid'],
    9: ['top','lt','rt','mid','db'],
}


def _draw_line(img, tw, th, p1, p2, thickness=1):
    x1, y1 = p1; x2, y2 = p2
    steps = max(abs(x2-x1), abs(y2-y1), 1) * 2
    inv = 1.0 / steps
    for i in range(steps + 1):
        t = i * inv
        cx = x1 + t * (x2 - x1)
        cy = y1 + t * (y2 - y1)
        for dy in range(-thickness, thickness + 1):
            py = int(cy + dy + 0.5)
            if py < 0 or py >= th: continue
            row = py * tw
            for dx in range(-thickness, thickness + 1):
                px = int(cx + dx + 0.5)
                if 0 <= px < tw:
                    img[row + px] = 1


# Build templates at module load
_TMPL_STATS = {}
for _d, _segs in _DIGIT_SEGS.items():
    _img = [0] * (TW * TH)
    for _seg in _segs:
        _draw_line(_img, TW, TH, *_SEG_EP[_seg], thickness=1)
    _n = TW * TH
    _mean = sum(_img) / _n
    _da = [x - _mean for x in _img]
    _denom = math.sqrt(sum(x * x for x in _da))
    _TMPL_STATS[_d] = (_da, _denom)


# =============================================================================
# Image processing
# =============================================================================

def parse_ppm(data):
    tokens = data.split()
    w = int(tokens[1]); h = int(tokens[2])
    idx = 4
    n = w * h
    gray = [0] * n
    for i in range(n):
        r = int(tokens[idx]); g = int(tokens[idx+1]); b = int(tokens[idx+2])
        idx += 3
        gray[i] = (r * 299 + g * 587 + b * 114) // 1000
    return w, h, gray


def otsu(gray):
    hist = [0] * 256
    for g in gray: hist[min(255, g)] += 1
    total = len(gray)
    s_all = sum(i * hist[i] for i in range(256))
    s_bg = w_bg = 0; bv = bt = 0
    for t in range(256):
        w_bg += hist[t]
        if w_bg == 0: continue
        w_fg = total - w_bg
        if w_fg == 0: break
        s_bg += t * hist[t]
        d = s_bg / w_bg - (s_all - s_bg) / w_fg
        v = w_bg * w_fg * d * d
        if v > bv: bv = v; bt = t
    return bt


def erode(b, w, h, mn):
    r = [0] * (w * h)
    for y in range(1, h-1):
        yw = y*w; ym = yw-w; yp = yw+w
        for x in range(1, w-1):
            if b[yw+x]:
                c = (b[ym+x-1]+b[ym+x]+b[ym+x+1]+
                     b[yw+x-1]+b[yw+x+1]+
                     b[yp+x-1]+b[yp+x]+b[yp+x+1])
                if c >= mn: r[yw+x] = 1
    return r


def dilate(b, w, h):
    r = b[:]
    for y in range(1, h-1):
        yw = y*w
        for x in range(1, w-1):
            if b[yw+x]:
                for dy in (-w, 0, w):
                    for dx in (-1, 0, 1):
                        r[yw+x+dy+dx] = 1
    return r


def tight_bounds(s, w, h, f=0.15):
    hp = [0]*h
    for y in range(h):
        v = 0; base = y*w
        for x in range(w): v += s[base+x]
        hp[y] = v
    mh = max(hp) if hp else 1; ht = mh*f
    rows = [y for y in range(h) if hp[y] > ht]
    if not rows: return 0, 0, w-1, h-1
    y1, y2 = rows[0], rows[-1]
    vp = [0]*w
    for y in range(y1, y2+1):
        base = y*w
        for x in range(w): vp[x] += s[base+x]
    mv = max(vp) if vp else 1; vt = mv*f
    cols = [x for x in range(w) if vp[x] > vt]
    if not cols: return 0, y1, w-1, y2
    return cols[0], y1, cols[-1], y2


def pca_angle(s, w, h, x1, y1, x2, y2):
    sx=sy=sxx=syy=sxy=0.0; n=0
    for y in range(y1, y2+1):
        base = y*w
        for x in range(x1, x2+1):
            if s[base+x]:
                sx+=x; sy+=y; sxx+=x*x; syy+=y*y; sxy+=x*y; n+=1
    if n < 10: return 0.0
    mx=sx/n; my=sy/n
    return math.degrees(0.5*math.atan2(2*(sxy/n-mx*my), sxx/n-mx*mx-(syy/n-my*my)))


def rot_gray(g, w, h, deg):
    if abs(deg) < 0.3: return g[:], w, h
    rad=math.radians(deg); ca=math.cos(rad); sa=math.sin(rad)
    cx=w/2.0; cy=h/2.0
    cs=[(-cx,-cy),(w-cx,-cy),(-cx,h-cy),(w-cx,h-cy)]
    rt=[(x*ca-y*sa, x*sa+y*ca) for x,y in cs]
    nw=int(math.ceil(max(c[0] for c in rt)-min(c[0] for c in rt)))+1
    nh=int(math.ceil(max(c[1] for c in rt)-min(c[1] for c in rt)))+1
    ncx=nw/2.0; ncy=nh/2.0
    r=[255]*(nw*nh)
    for ny in range(nh):
        dy=ny-ncy; bx=dy*sa+cx; by=dy*ca+cy; dst=ny*nw
        for nx in range(nw):
            dx=nx-ncx
            ox=int(dx*ca+bx+0.5); oy=int(-dx*sa+by+0.5)
            if 0<=ox<w and 0<=oy<h: r[dst+nx]=g[oy*w+ox]
    return r, nw, nh


def resize(cell, cw, ch, tw, th):
    r = [0]*(tw*th)
    for ty in range(th):
        sy=int(ty*ch/th); src=sy*cw; dst=ty*tw
        for tx in range(tw):
            r[dst+tx] = cell[src+int(tx*cw/tw)]
    return r


def classify(resized):
    n=TW*TH; mc=sum(resized)/n
    dc=[x-mc for x in resized]
    dnc=math.sqrt(sum(x*x for x in dc))
    if dnc < 1e-10: return 0
    bd=0; bs=-999.0
    for d,(da,dt) in _TMPL_STATS.items():
        if dt < 1e-10: continue
        s=sum(dc[i]*da[i] for i in range(n))/(dnc*dt)
        if s > bs: bs=s; bd=d
    return bd


def do_pipeline(gray, w, h, thresh, mn):
    """Run full pipeline with given erosion strength. Returns 6-digit string."""
    binary = [1 if g < thresh else 0 for g in gray]
    strokes = dilate(erode(binary, w, h, mn), w, h)
    if sum(strokes) < 30:
        return None

    bx1, by1, bx2, by2 = tight_bounds(strokes, w, h)
    angle = pca_angle(strokes, w, h, bx1, by1, bx2, by2)

    if abs(angle) > 0.5:
        rg, rw, rh = rot_gray(gray, w, h, -angle)
        rb = [1 if g < thresh else 0 for g in rg]
        rs = dilate(erode(rb, rw, rh, mn), rw, rh)
        rx1, ry1, rx2, ry2 = tight_bounds(rs, rw, rh)
    else:
        rs, rw = strokes, w
        rx1, ry1, rx2, ry2 = bx1, by1, bx2, by2

    bw = rx2 - rx1 + 1; bh = ry2 - ry1 + 1
    if bw < 6 or bh < 3:
        return None

    cw_f = bw / 6.0
    result = ''
    for i in range(6):
        cs = int(i * cw_f)
        ce = int((i + 1) * cw_f) - 1
        cw = ce - cs + 1
        cell = [0] * (cw * bh)
        for r in range(bh):
            src = (ry1 + r) * rw + rx1 + cs
            dst = r * cw
            for c in range(cw):
                idx = src + c
                if 0 <= idx < len(rs):
                    cell[dst + c] = rs[idx]
        result += str(classify(resize(cell, cw, bh, TW, TH)))
    return result


def process_image(img_data):
    w, h, gray = parse_ppm(img_data)
    thresh = otsu(gray)

    # Primary: mn=5 (removes most dot grid noise)
    result = do_pipeline(gray, w, h, thresh, 5)
    if result:
        return result

    # Fallback: mn=4 (if mn=5 removed too much)
    result = do_pipeline(gray, w, h, thresh, 4)
    if result:
        return result

    # Last resort: mn=3
    result = do_pipeline(gray, w, h, thresh, 3)
    return result if result else '000000'


# =============================================================================
# Network client
# =============================================================================

def recv_line(sock, buf):
    while b'\n' not in buf:
        d = sock.recv(65536)
        if not d: return None, buf
        buf += d
    i = buf.index(b'\n')
    return buf[:i].decode('ascii'), buf[i+1:]


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(15)
    sock.connect(('localhost', 7474))
    sock.sendall(b'claude_bot\n')
    print("Connected", file=sys.stderr)

    buf = b''; score = total = 0

    while True:
        line, buf = recv_line(sock, buf)
        if line is None: break
        if line == 'ELIMINATED':
            print("ELIMINATED", file=sys.stderr); break
        if not line.startswith('ROUND'): continue

        total = int(line.split()[1])
        sl, buf = recv_line(sock, buf)
        if sl is None: break
        nb = int(sl.split()[1])

        while len(buf) < nb:
            d = sock.recv(65536)
            if not d: break
            buf += d
        img = buf[:nb].decode('ascii')
        buf = buf[nb:]

        try:
            answer = process_image(img)
        except Exception as e:
            print(f"R{total}: ERR {e}", file=sys.stderr)
            answer = '000000'

        sock.sendall(f'{answer}\n'.encode())

        resp, buf = recv_line(sock, buf)
        if resp is None: break
        parts = resp.split()
        if parts[0] == 'CORRECT': score += 1
        elif parts[0] == 'ELIMINATED':
            print("ELIMINATED", file=sys.stderr); break
        tag = 'OK' if parts[0]=='CORRECT' else f'WRONG {parts[1] if len(parts)>1 else "?"}'
        print(f"R{total}: {answer} {tag} ({score}/{total})", file=sys.stderr)

    sock.close()
    print(f"Final: {score}/{total}", file=sys.stderr)


if __name__ == '__main__':
    main()