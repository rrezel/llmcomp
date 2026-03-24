#!/usr/bin/env python3
"""Subway Speedrun — greedy solver for subway routing optimization over TCP."""

import socket
import json
import time as _time


def t2m(s):
    h, m = s.split(':')
    return int(h) * 60 + int(m)


def m2t(m):
    m = m % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def solve(data):
    lines = data['lines']
    transfers = data.get('transfers', [])

    # station -> [(line_idx, pos_idx)]
    stn_lines = {}
    for li, ln in enumerate(lines):
        for si, st in enumerate(ln['stations']):
            stn_lines.setdefault(st, []).append((li, si))

    # Hub pairs
    hub_set = set()
    hub_list = []
    for pair in transfers:
        a, b = pair[0], pair[1]
        hub_set.update([a, b])
        hub_list.append((a, b))

    L = len(lines)
    L_st = [ln['stations'] for ln in lines]
    L_n = [len(s) for s in L_st]
    L_seg = [ln['segments'] for ln in lines]
    L_int = [ln['interval'] for ln in lines]
    L_s0 = [t2m(ln['start_time']) for ln in lines]
    L_e0 = [t2m(ln['end_time']) for ln in lines]

    # Cumulative times from each end
    L_cf = []
    L_cb = []
    for li in range(L):
        n = L_n[li]
        cf = [0] * n
        for i in range(1, n):
            cf[i] = cf[i - 1] + L_seg[li][i - 1]
        cb = [0] * n
        for i in range(n - 2, -1, -1):
            cb[i] = cb[i + 1] + L_seg[li][i]
        L_cf.append(cf)
        L_cb.append(cb)

    # Union-find
    all_stations = list(stn_lines.keys())
    parent = {s: s for s in all_stations}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b in hub_list:
        union(a, b)

    def group(st):
        r = find(st)
        return frozenset(s for s in all_stations if find(s) == r)

    all_groups = list(set(group(s) for s in all_stations))

    # Next train: returns (depart_at_si, arrive_at_adj) or None
    def ntrain(li, si, now, fwd):
        if fwd:
            first = L_s0[li] - L_cf[li][si]
        else:
            first = L_s0[li] - L_cb[li][si]
        gap = now - first
        if gap <= 0:
            dep = first
        else:
            dep = first + ((gap + L_int[li] - 1) // L_int[li]) * L_int[li]
        if dep > L_e0[li]:
            return None
        if fwd:
            return dep, dep + L_cf[li][si + 1]
        else:
            return dep, dep + L_cb[li][si - 1]

    # Greedy route from (start_st, start_min)
    def route_from(start_st, start_min):
        visited = set()
        path = []
        cur = start_st
        ct = start_min
        cli = None  # current line

        for _ in range(len(all_groups) + 500):
            cg = group(cur)
            if cg not in visited:
                visited.add(cg)
                for s in sorted(cg):
                    if not path or path[-1] != s:
                        path.append(s)

            if len(visited) >= len(all_groups):
                break

            cands = []

            # Ride current line
            if cli is not None:
                csi = None
                for li, si in stn_lines.get(cur, []):
                    if li == cli:
                        csi = si
                        break
                if csi is not None:
                    # Forward
                    for j in range(csi + 1, L_n[cli]):
                        st = L_st[cli][j]
                        arr = ct + L_cf[cli][j] - L_cf[cli][csi]
                        g = group(st)
                        if g not in visited:
                            cands.append((arr, st, cli, g))
                            break
                    # Backward
                    for j in range(csi - 1, -1, -1):
                        st = L_st[cli][j]
                        arr = ct + L_cb[cli][j] - L_cb[cli][csi]
                        g = group(st)
                        if g not in visited:
                            cands.append((arr, st, cli, g))
                            break

            # Transfer at hub
            if cur in hub_set:
                for tli, tsi in stn_lines.get(cur, []):
                    if tli == cli:
                        continue
                    for d in (0, 1):
                        if d == 0 and tsi >= L_n[tli] - 1:
                            continue
                        if d == 1 and tsi <= 0:
                            continue
                        res = ntrain(tli, tsi, ct, d == 0)
                        if res is None:
                            continue
                        _, arr = res
                        adj = L_st[tli][tsi + (1 if d == 0 else -1)]
                        g = group(adj)
                        if g not in visited:
                            cands.append((arr, adj, tli, g))

            # First boarding (no line yet)
            if cli is None:
                for tli, tsi in stn_lines.get(cur, []):
                    for d in (0, 1):
                        if d == 0 and tsi >= L_n[tli] - 1:
                            continue
                        if d == 1 and tsi <= 0:
                            continue
                        res = ntrain(tli, tsi, ct, d == 0)
                        if res is None:
                            continue
                        _, arr = res
                        adj = L_st[tli][tsi + (1 if d == 0 else -1)]
                        g = group(adj)
                        if g not in visited:
                            cands.append((arr, adj, tli, g))

            if not cands:
                break

            # Pick best: new group first, then earliest arrival
            cands.sort(key=lambda c: (0 if c[3] not in visited else 1, c[0]))
            arr, nxt, nli, ng = cands[0]

            # Expand intermediates if same line
            if cli is not None and cli == nli:
                csi = next(si for li, si in stn_lines[cur] if li == cli)
                nsi = next(si for li, si in stn_lines[nxt] if li == cli)
                step = 1 if nsi > csi else -1
                for j in range(csi + step, nsi + step, step):
                    s = L_st[cli][j]
                    if not path or path[-1] != s:
                        path.append(s)
            else:
                if not path or path[-1] != nxt:
                    path.append(nxt)

            cur = nxt
            ct = arr
            cli = nli

            fg = group(cur)
            if fg not in visited:
                visited.add(fg)
                for s in sorted(fg):
                    if not path or path[-1] != s:
                        path.append(s)

        return path, ct

    # Try multiple starts and times
    best_path = None
    best_dur = float('inf')
    best_start = "06:00"

    for s0 in all_stations:
        for sm in [300, 360, 420, 480, 540]:
            p, end_t = route_from(s0, sm)
            if p and len(p) >= len(all_groups):
                dur = end_t - sm
                if 0 < dur < best_dur:
                    best_dur = dur
                    best_path = list(p)
                    best_start = m2t(sm)

    if best_path is None:
        # Fallback: just use first station at 06:00
        best_path, _ = route_from(all_stations[0], 360)
        best_start = "06:00"

    return {"start_time": best_start, "route": best_path}


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock.sendall(b"mimo_bot\n")
    print("Connected as mimo_bot", flush=True)

    buf = b''
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk

        while b'\n' in buf:
            line_b, buf = buf.split(b'\n', 1)
            line = line_b.decode().strip()
            if not line:
                continue

            if line.startswith('ROUND'):
                print(f"\n{line}", flush=True)
                # Read SIZE line
                while b'\n' not in buf:
                    more = sock.recv(65536)
                    if not more:
                        sock.close()
                        return
                    buf += more
                size_b, buf = buf.split(b'\n', 1)
                sz = int(size_b.decode().strip().split()[1])

                while len(buf) < sz:
                    more = sock.recv(65536)
                    if not more:
                        sock.close()
                        return
                    buf += more

                payload = buf[:sz].decode()
                buf = buf[sz:]
                data = json.loads(payload)

                t0 = _time.time()
                result = solve(data)
                dt = _time.time() - t0

                out = json.dumps(result, separators=(',', ':'))
                sock.sendall((out + '\n').encode())
                print(f"  Sent: start={result['start_time']} "
                      f"stops={len(result['route'])} time={dt:.1f}s", flush=True)

            elif line.startswith(('VALID', 'INVALID', 'TIMEOUT')):
                print(f"  Server: {line}", flush=True)

    sock.close()


if __name__ == '__main__':
    main()
