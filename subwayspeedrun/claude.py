#!/usr/bin/env python3
"""
Subway Speedrun Bot - Day 5 Challenge
Standard library only, Python 3.10.
"""

import socket
import json
import sys
import time
import heapq
from collections import defaultdict
from itertools import permutations
import random

DEBUG = True

def log(msg):
    if DEBUG:
        print(msg, file=sys.stderr, flush=True)

def parse_time(t):
    h, m = t.split(':')
    return int(h) * 60 + int(m)

def format_time(minutes):
    h = (minutes // 60) % 24
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


# ──────────────────────────────────────────────────
# Network model
# ──────────────────────────────────────────────────

class Network:
    def __init__(self, data):
        self.lines = {}
        self.station_to_lines = defaultdict(list)

        for ld in data['lines']:
            lid = ld['id']
            st = parse_time(ld['start_time'])
            et = parse_time(ld['end_time'])
            if et <= st:
                et += 1440
            self.lines[lid] = {
                'id': lid,
                'stations': ld['stations'],
                'segments': ld['segments'],
                'interval': ld['interval'],
                'start_time': st,
                'end_time': et,
                'total_time': sum(ld['segments']),
            }
            for i, s in enumerate(ld['stations']):
                self.station_to_lines[s].append((lid, i))

        # Union-Find for transfer hubs
        self._parent = {}
        self.all_stations = set()
        for ld in data['lines']:
            self.all_stations.update(ld['stations'])
        for s in self.all_stations:
            self._parent[s] = s
        self.transfer_pairs = data.get('transfers', [])
        for s1, s2 in self.transfer_pairs:
            self._union(s1, s2)

        groups = defaultdict(set)
        for s in self.all_stations:
            groups[self._find(s)].add(s)
        self.hub_of = {}
        for root, group in groups.items():
            fg = frozenset(group)
            for s in group:
                self.hub_of[s] = fg

        self.unique_hubs = set(self._find(s) for s in self.all_stations)
        self.num_unique = len(self.unique_hubs)

        # Adjacency graph (rides + transfers with weight 0)
        self.graph = defaultdict(list)
        for lid, line in self.lines.items():
            stations = line['stations']
            segments = line['segments']
            for i in range(len(segments)):
                self.graph[stations[i]].append((stations[i+1], segments[i], lid))
                self.graph[stations[i+1]].append((stations[i], segments[i], lid))
        for s1, s2 in self.transfer_pairs:
            self.graph[s1].append((s2, 0, '__xfer__'))
            self.graph[s2].append((s1, 0, '__xfer__'))

        # Line-to-line adjacency via transfers
        self.line_adj = defaultdict(list)  # lid -> [(other_lid, my_station, my_idx, other_station, other_idx)]
        for s1, s2 in self.transfer_pairs:
            for lid1, idx1 in self.station_to_lines[s1]:
                for lid2, idx2 in self.station_to_lines[s2]:
                    if lid1 != lid2:
                        self.line_adj[lid1].append((lid2, s1, idx1, s2, idx2))
                        self.line_adj[lid2].append((lid1, s2, idx2, s1, idx1))

    def _find(self, x):
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def _union(self, x, y):
        px, py = self._find(x), self._find(y)
        if px != py:
            self._parent[px] = py

    def find(self, x):
        return self._find(x)


# ──────────────────────────────────────────────────
# Train schedule helpers
# ──────────────────────────────────────────────────

def next_train(line, station_idx, direction, min_time):
    """Earliest time a train passes station_idx going `direction`, at or after min_time."""
    segs = line['segments']
    offset = sum(segs[:station_idx]) if direction == 'fwd' else sum(segs[station_idx:])
    start, interval, end = line['start_time'], line['interval'], line['end_time']
    needed = min_time - start - offset
    k = max(0, (needed + interval - 1) // interval) if needed > 0 else 0
    dep = start + k * interval
    if dep > end:
        return None
    return dep + offset


# ──────────────────────────────────────────────────
# Simulation  (correctly handles every transition)
# ──────────────────────────────────────────────────

def simulate(net, t0, route):
    """Returns (duration, visited_hub_set) or (None, set()) on failure."""
    if len(route) < 1:
        return None, set()

    t = t0
    vis = {net.find(route[0])}
    i = 0

    while i < len(route) - 1:
        cur, nxt = route[i], route[i + 1]

        # --- transfer (same hub, different station name) ---
        hub = net.hub_of.get(cur, frozenset({cur}))
        if nxt in hub and nxt != cur:
            vis.add(net.find(nxt))
            i += 1
            continue

        # --- find ride line & direction ---
        ride_lid = ride_dir = None
        ride_idx = -1
        for lid, idx in net.station_to_lines[cur]:
            sts = net.lines[lid]['stations']
            if ride_dir is None and idx + 1 < len(sts) and sts[idx + 1] == nxt:
                ride_lid, ride_dir, ride_idx = lid, 'fwd', idx
                break
            if ride_dir is None and idx - 1 >= 0 and sts[idx - 1] == nxt:
                ride_lid, ride_dir, ride_idx = lid, 'bwd', idx
                break
        if ride_lid is None:
            return None, vis  # invalid move

        line = net.lines[ride_lid]
        sts = line['stations']

        # transfer buffer: if previous step was a hub transfer, +1 min
        xfer_buf = 0
        if i > 0:
            prev = route[i - 1]
            prev_hub = net.hub_of.get(prev, frozenset({prev}))
            if cur in prev_hub and cur != prev:
                xfer_buf = 1

        train_t = next_train(line, ride_idx, ride_dir, t + xfer_buf)
        if train_t is None:
            return None, vis

        t = train_t
        ci = ride_idx
        j = i + 1

        # consume consecutive stations on the same ride
        while j < len(route):
            ei = ci + (1 if ride_dir == 'fwd' else -1)
            if ei < 0 or ei >= len(sts) or sts[ei] != route[j]:
                break
            t += line['segments'][min(ci, ei)]
            vis.add(net.find(route[j]))
            ci = ei
            j += 1

        # CRITICAL: we are now at route[j-1]; process from there next
        i = j - 1

    return t - t0, vis


# ──────────────────────────────────────────────────
# Graph helpers
# ──────────────────────────────────────────────────

def dijkstra_all(net, start):
    dist = {start: 0}
    heap = [(0, start)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, float('inf')):
            continue
        for v, w, _ in net.graph[u]:
            nd = d + w
            if nd < dist.get(v, float('inf')):
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return dist


def dijkstra_path(net, start, end):
    dist = {start: 0}
    prev = {start: None}
    heap = [(0, start)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, float('inf')):
            continue
        if u == end:
            break
        for v, w, _ in net.graph[u]:
            nd = d + w
            if nd < dist.get(v, float('inf')):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))
    if end not in prev:
        return None
    path = []
    c = end
    while c is not None:
        path.append(c)
        c = prev[c]
    return list(reversed(path))


# ──────────────────────────────────────────────────
# Route construction helpers
# ──────────────────────────────────────────────────

def seg(lid, net, a, b):
    """Stations list for riding line `lid` from index a to index b."""
    sts = net.lines[lid]['stations']
    if a <= b:
        return [sts[i] for i in range(a, b + 1)]
    return [sts[i] for i in range(a, b - 1, -1)]


def find_entry(net, from_station, to_lid):
    """Find shortest path from from_station to any station on line to_lid.
    Returns (path_to_append, entry_station, entry_idx) or None."""
    target_sts = set(net.lines[to_lid]['stations'])

    # Already on the target line?
    for lid, idx in net.station_to_lines[from_station]:
        if lid == to_lid:
            return [], from_station, idx

    # Hub contains target station?
    hub = net.hub_of.get(from_station, frozenset({from_station}))
    for s in hub:
        if s in target_sts:
            idx = net.lines[to_lid]['stations'].index(s)
            return ([s] if s != from_station else []), s, idx

    # General Dijkstra
    dmap = dijkstra_all(net, from_station)
    best_t, best_via, best_entry, best_idx = float('inf'), None, None, None
    for s in target_sts:
        for hs in net.hub_of.get(s, frozenset({s})):
            if hs in dmap and dmap[hs] < best_t:
                best_t = dmap[hs]
                best_via = hs
                best_entry = s
                best_idx = net.lines[to_lid]['stations'].index(s)
    if best_via is None:
        return None

    path = dijkstra_path(net, from_station, best_via)
    if path is None:
        return None
    r = list(path[1:])
    if best_via != best_entry:
        r.append(best_entry)
    return r, best_entry, best_idx


def build_route(net, line_order, start_end='start'):
    """Build a complete route riding lines in the given order.
    start_end: 'start' = begin at first station of first line,
               'end'   = begin at last station of first line."""
    if not line_order:
        return None

    visited_hubs = set()

    def mark(stations):
        for s in stations:
            visited_hubs.add(net.find(s))

    first = net.lines[line_order[0]]
    fsts = first['stations']
    n0 = len(fsts)

    if start_end == 'start':
        route = list(fsts)
    else:
        route = list(reversed(fsts))
    mark(route)

    for k in range(1, len(line_order)):
        lid = line_order[k]
        line = net.lines[lid]
        sts = line['stations']
        n = len(sts)

        # Check if already fully visited
        if all(net.find(s) in visited_hubs for s in sts):
            continue

        cur = route[-1]
        result = find_entry(net, cur, lid)
        if result is None:
            return None
        xfer_path, entry_s, entry_i = result
        route.extend(xfer_path)
        mark(xfer_path)

        # Determine which portions are unvisited
        need_left = any(net.find(sts[j]) not in visited_hubs for j in range(entry_i))
        need_right = any(net.find(sts[j]) not in visited_hubs for j in range(entry_i + 1, n))

        if not need_left and not need_right:
            visited_hubs.add(net.find(entry_s))
            continue

        if need_left and need_right:
            # Ride both directions: pick shorter side first to minimize travel
            left_cost = sum(line['segments'][:entry_i])
            right_cost = sum(line['segments'][entry_i:])
            if left_cost <= right_cost:
                # left first: entry->0, then 0->n-1
                part = seg(lid, net, entry_i, 0) + seg(lid, net, 0, n-1)[1:]
            else:
                # right first: entry->n-1, then n-1->0
                part = seg(lid, net, entry_i, n-1) + seg(lid, net, n-1, 0)[1:]
            route.extend(part[1:])
        elif need_left:
            route.extend(seg(lid, net, entry_i, 0)[1:])
        else:
            route.extend(seg(lid, net, entry_i, n-1)[1:])

        mark(route)

    return route


def build_route_exitnear(net, line_order, start_end='start'):
    """Like build_route but tries to end each line near the transfer to the next line."""
    if not line_order:
        return None

    visited_hubs = set()

    def mark(stations):
        for s in stations:
            visited_hubs.add(net.find(s))

    # Precompute direct transfer index between consecutive lines
    exit_idx = {}
    for k in range(len(line_order) - 1):
        l1, l2 = line_order[k], line_order[k + 1]
        for adj_lid, my_s, my_i, other_s, other_i in net.line_adj.get(l1, []):
            if adj_lid == l2:
                exit_idx[k] = my_i
                break

    first = net.lines[line_order[0]]
    fsts = first['stations']
    n0 = len(fsts)

    if start_end == 'start':
        route = list(fsts)
    else:
        route = list(reversed(fsts))

    # Backtrack toward exit if needed
    if 0 in exit_idx:
        end_i = n0 - 1 if start_end == 'start' else 0
        ex = exit_idx[0]
        if ex != end_i:
            route.extend(seg(line_order[0], net, end_i, ex)[1:])
    mark(route)

    for k in range(1, len(line_order)):
        lid = line_order[k]
        line = net.lines[lid]
        sts = line['stations']
        n = len(sts)

        if all(net.find(s) in visited_hubs for s in sts):
            continue

        cur = route[-1]
        result = find_entry(net, cur, lid)
        if result is None:
            return None
        xfer_path, entry_s, entry_i = result
        route.extend(xfer_path)
        mark(xfer_path)

        need_left = any(net.find(sts[j]) not in visited_hubs for j in range(entry_i))
        need_right = any(net.find(sts[j]) not in visited_hubs for j in range(entry_i + 1, n))

        if not need_left and not need_right:
            visited_hubs.add(net.find(entry_s))
            continue

        want_exit = exit_idx.get(k)

        if need_left and need_right:
            # Choose direction order to end near exit
            if want_exit is not None:
                go_left_first = (want_exit >= entry_i)  # end at right side
            else:
                left_cost = sum(line['segments'][:entry_i])
                right_cost = sum(line['segments'][entry_i:])
                go_left_first = (left_cost <= right_cost)

            if go_left_first:
                part = seg(lid, net, entry_i, 0) + seg(lid, net, 0, n-1)[1:]
                end_of_ride = n - 1
            else:
                part = seg(lid, net, entry_i, n-1) + seg(lid, net, n-1, 0)[1:]
                end_of_ride = 0
            route.extend(part[1:])

            # Backtrack to exit if needed
            if want_exit is not None and want_exit != end_of_ride:
                route.extend(seg(lid, net, end_of_ride, want_exit)[1:])
        elif need_left:
            route.extend(seg(lid, net, entry_i, 0)[1:])
            if want_exit is not None and want_exit > 0:
                route.extend(seg(lid, net, 0, want_exit)[1:])
        else:
            route.extend(seg(lid, net, entry_i, n-1)[1:])
            if want_exit is not None and want_exit < n - 1:
                route.extend(seg(lid, net, n-1, want_exit)[1:])

        mark(route)

    return route


def greedy_route(net, start_station, deadline):
    """Greedy nearest-unvisited-hub, extending along lines."""
    route = [start_station]
    vis = {net.find(start_station)}
    cur = start_station

    while vis < net.unique_hubs:
        if time.time() > deadline:
            return None

        dmap = dijkstra_all(net, cur)
        best_s, best_d = None, float('inf')
        for s in net.all_stations:
            h = net.find(s)
            if h not in vis and s in dmap and dmap[s] < best_d:
                best_d = dmap[s]
                best_s = s
        if best_s is None:
            break

        path = dijkstra_path(net, cur, best_s)
        if path is None:
            break
        for s in path[1:]:
            route.append(s)
            vis.add(net.find(s))
        cur = route[-1]

        # Extend: ride line of current station to cover more unvisited
        best_ext = None
        best_cnt = 0
        for lid, idx in net.station_to_lines[cur]:
            sts = net.lines[lid]['stations']
            n = len(sts)
            fwd = sum(1 for j in range(idx+1, n) if net.find(sts[j]) not in vis)
            bwd = sum(1 for j in range(0, idx) if net.find(sts[j]) not in vis)
            total = fwd + bwd
            if total > best_cnt:
                best_cnt = total
                if fwd > 0 and bwd > 0:
                    lc = sum(net.lines[lid]['segments'][:idx])
                    rc = sum(net.lines[lid]['segments'][idx:])
                    if lc <= rc:
                        ext = seg(lid, net, idx, 0) + seg(lid, net, 0, n-1)[1:]
                    else:
                        ext = seg(lid, net, idx, n-1) + seg(lid, net, n-1, 0)[1:]
                    best_ext = ext
                elif fwd > 0:
                    best_ext = seg(lid, net, idx, n-1)
                else:
                    best_ext = seg(lid, net, idx, 0)

        if best_ext:
            route.extend(best_ext[1:])
            for s in best_ext:
                vis.add(net.find(s))
            cur = route[-1]

    return route


# ──────────────────────────────────────────────────
# Validation & start-time optimization
# ──────────────────────────────────────────────────

def all_visited(net, route):
    vis = set()
    for s in route:
        vis.add(net.find(s))
    return vis >= net.unique_hubs


def optimize_start(net, route, deadline=None):
    """Find the best start time. Returns (start_time, duration) or (None, inf)."""
    if not route or len(route) < 2:
        return None, float('inf')

    # Find first actual ride
    first_lid = first_dir = None
    first_idx = -1
    for k in range(len(route) - 1):
        s1, s2 = route[k], route[k+1]
        hub = net.hub_of.get(s1, frozenset({s1}))
        if s2 in hub and s2 != s1:
            continue
        for lid, idx in net.station_to_lines[s1]:
            sts = net.lines[lid]['stations']
            if idx+1 < len(sts) and sts[idx+1] == s2:
                first_lid, first_dir, first_idx = lid, 'fwd', idx
                break
            if idx-1 >= 0 and sts[idx-1] == s2:
                first_lid, first_dir, first_idx = lid, 'bwd', idx
                break
        if first_lid is not None:
            break

    best_t, best_dur = None, float('inf')

    if first_lid:
        line = net.lines[first_lid]
        segs = line['segments']
        offset = sum(segs[:first_idx]) if first_dir == 'fwd' else sum(segs[first_idx:])
        start, interval, end = line['start_time'], line['interval'], line['end_time']

        # The ideal start_time = when first train arrives at boarding station
        # = start + k*interval + offset
        # Start from k=0 (earliest train) and scan forward
        k = 0
        consecutive_fail = 0
        consecutive_no_improve = 0
        while start + k * interval <= end:
            if deadline and time.time() > deadline:
                break
            cand = start + k * interval + offset
            dur, vis = simulate(net, cand, route)
            if dur is not None and vis >= net.unique_hubs:
                consecutive_fail = 0
                if dur < best_dur:
                    best_dur = dur
                    best_t = cand
                    consecutive_no_improve = 0
                else:
                    consecutive_no_improve += 1
                    # For early start times, keep searching (trains may align better later)
                    # For late start times, stop if no improvement
                    if consecutive_no_improve > 20:
                        break
            else:
                consecutive_fail += 1
                # If we already found a valid route and now failing, stop
                if best_t is not None and consecutive_fail > 5:
                    break
                # If we've never found valid and failing a lot, skip ahead
                if best_t is None and consecutive_fail > 50:
                    break
            k += 1
            if k > 800:
                break

        # If aligned times didn't work, try minute-by-minute scan from earliest
        if best_t is None:
            earliest_train = start + offset  # first possible boarding time
            for t in range(max(0, earliest_train - 5), earliest_train + interval * 3):
                if deadline and time.time() > deadline:
                    break
                dur, vis = simulate(net, t, route)
                if dur is not None and vis >= net.unique_hubs:
                    if dur < best_dur:
                        best_dur = dur
                        best_t = t
                    break  # found one, the aligned search should now work
    else:
        mn = min(l['start_time'] for l in net.lines.values())
        for t in range(mn, mn + 360):
            if deadline and time.time() > deadline:
                break
            dur, vis = simulate(net, t, route)
            if dur is not None and vis >= net.unique_hubs:
                if dur < best_dur:
                    best_dur = dur
                    best_t = t

    return best_t, best_dur


def quick_eval(net, route):
    """Quick lower-bound evaluation: sum of segment travel times in the route."""
    if route is None:
        return float('inf')
    total = 0
    for i in range(len(route) - 1):
        s1, s2 = route[i], route[i+1]
        hub = net.hub_of.get(s1, frozenset({s1}))
        if s2 in hub and s2 != s1:
            continue
        for v, w, _ in net.graph[s1]:
            if v == s2 and _ != '__xfer__':
                total += w
                break
    return total


# ──────────────────────────────────────────────────
# Solver
# ──────────────────────────────────────────────────

def solve(net, deadline):
    line_ids = list(net.lines.keys())
    num_lines = len(line_ids)

    best_route = None
    best_start = None
    best_dur = float('inf')
    attempts = 0

    def try_route(route, time_budget=None):
        nonlocal best_route, best_start, best_dur, attempts
        if route is None or not all_visited(net, route):
            return
        if time.time() > deadline - 1:
            return
        dl = min(deadline - 0.5, time.time() + (time_budget or 5))
        st, dur = optimize_start(net, route, dl)
        attempts += 1
        if st is not None and dur < best_dur:
            best_dur = dur
            best_route = route
            best_start = st
            log(f"  [#{attempts}] New best: {dur}min start={format_time(st)} "
                f"len={len(route)}")

    # --- Generate candidates ---
    candidates = []

    def collect(route):
        if route and all_visited(net, route):
            qe = quick_eval(net, route)
            candidates.append((qe, route))

    gen_deadline = time.time() + max(2, (deadline - time.time()) * 0.6)

    # Phase 1: Permutation-based
    if num_lines <= 7:
        perms = list(permutations(line_ids))
        random.shuffle(perms)
    elif num_lines <= 10:
        perms = list({tuple(random.sample(line_ids, num_lines)) for _ in range(3000)})
    else:
        perms = list({tuple(random.sample(line_ids, num_lines)) for _ in range(1500)})

    for perm in perms:
        if time.time() > gen_deadline:
            break
        for se in ['start', 'end']:
            collect(build_route(net, list(perm), se))
            collect(build_route_exitnear(net, list(perm), se))

    # Phase 2: Greedy line orderings
    for start_lid in line_ids:
        if time.time() > gen_deadline:
            break
        for start_terminal in ['start', 'end']:
            order = [start_lid]
            line = net.lines[start_lid]
            cur = line['stations'][-1] if start_terminal == 'start' else line['stations'][0]
            remaining = set(line_ids) - {start_lid}
            while remaining:
                dmap = dijkstra_all(net, cur)
                best_next, best_d = None, float('inf')
                for lid in remaining:
                    for s in net.lines[lid]['stations']:
                        for hs in net.hub_of.get(s, frozenset({s})):
                            if hs in dmap and dmap[hs] < best_d:
                                best_d = dmap[hs]
                                best_next = lid
                if best_next is None:
                    break
                order.append(best_next)
                remaining.remove(best_next)
                result = find_entry(net, cur, best_next)
                if result:
                    _, _, ei = result
                    ns = net.lines[best_next]['stations']
                    cur = ns[-1] if ei <= len(ns) // 2 else ns[0]
                else:
                    cur = net.lines[best_next]['stations'][-1]
            for se in ['start', 'end']:
                collect(build_route(net, order, se))
                collect(build_route_exitnear(net, order, se))

    # Phase 3: Greedy station-by-station
    for start_lid in line_ids:
        if time.time() > gen_deadline:
            break
        for tidx in [0, -1]:
            ss = net.lines[start_lid]['stations'][tidx]
            r = greedy_route(net, ss, gen_deadline)
            collect(r)
    for s1, s2 in net.transfer_pairs[:8]:
        if time.time() > gen_deadline:
            break
        for ss in [s1, s2]:
            r = greedy_route(net, ss, gen_deadline)
            collect(r)

    # --- Evaluate candidates ---
    candidates.sort(key=lambda x: x[0])
    # Deduplicate by route length + quick_eval (same qe + same length = likely same route)
    seen = set()
    unique = []
    for qe, route in candidates:
        key = (qe, len(route))
        if key not in seen:
            seen.add(key)
            unique.append((qe, route))
    candidates = unique

    log(f"  Candidates: {len(candidates)}, "
        f"best qe: {candidates[0][0] if candidates else 'N/A'}")

    # Allocate time: give more to top candidates
    remaining_time = max(1, deadline - time.time() - 3)
    n_to_try = min(len(candidates), max(10, int(remaining_time / 0.3)))

    for i, (qe, route) in enumerate(candidates[:n_to_try]):
        if time.time() > deadline - 2:
            break
        # Give more time to top candidates
        if i < 5:
            budget = min(5, remaining_time * 0.15)
        elif i < 20:
            budget = min(2, remaining_time * 0.05)
        else:
            budget = 0.5
        try_route(route, time_budget=budget)

    # 2-opt on best found
    if best_route and time.time() < deadline - 5:
        for perm in perms[:20]:
            if time.time() > deadline - 3:
                break
            base = list(perm)
            for i in range(len(base)):
                if time.time() > deadline - 3:
                    break
                for j in range(i+1, len(base)):
                    new_order = list(base)
                    new_order[i], new_order[j] = new_order[j], new_order[i]
                    for se in ['start', 'end']:
                        r = build_route(net, new_order, se)
                        if r and all_visited(net, r):
                            qe = quick_eval(net, r)
                            if qe < best_dur:
                                try_route(r, time_budget=2)

    if best_route is None:
        log("WARNING: Emergency fallback")
        for lid in line_ids:
            line = net.lines[lid]
            route = list(line['stations'])
            dur, vis = simulate(net, line['start_time'], route)
            if dur is not None:
                best_route, best_start, best_dur = route, line['start_time'], dur
                break

    log(f"Final: {best_dur}min, {attempts} evaluated")
    return best_route, best_start, best_dur


# ──────────────────────────────────────────────────
# TCP client
# ──────────────────────────────────────────────────

def main():
    log("Subway Speedrun Bot starting...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(120)
    sock.connect(('localhost', 7474))
    log("Connected")
    sock.sendall(b'claude_bot\n')
    log("Registered")

    buf = b''

    def read_line():
        nonlocal buf
        while b'\n' not in buf:
            chunk = sock.recv(8192)
            if not chunk:
                raise ConnectionError("Disconnected")
            buf += chunk
        line, buf = buf.split(b'\n', 1)
        return line.decode().strip()

    def read_bytes(n):
        nonlocal buf
        while len(buf) < n:
            chunk = sock.recv(8192)
            if not chunk:
                raise ConnectionError("Disconnected")
            buf += chunk
        data, buf = buf[:n], buf[n:]
        return data

    try:
        while True:
            rl = read_line()
            log(f"\n{'='*50}")
            log(f"<< {rl}")

            if not rl.startswith("ROUND"):
                if any(x in rl.upper() for x in ["GAMEOVER", "END", "FINAL", "SCORE"]):
                    log(f"Game over: {rl}")
                    break
                continue

            t_start = time.time()
            sl = read_line()
            log(f"<< {sl}")
            sz = int(sl.split()[1])
            payload = read_bytes(sz)
            data = json.loads(payload.decode())

            log(f"Network: {len(data['lines'])} lines, "
                f"{len(data.get('transfers',[]))} transfers, "
                f"{sum(len(l['stations']) for l in data['lines'])} total stations")

            net = Network(data)
            log(f"Unique hubs to visit: {net.num_unique}")

            dl = t_start + 55
            route, st, dur = solve(net, dl)

            if route:
                resp = {"start_time": format_time(st), "route": route}
                log(f">> duration={dur}, start={format_time(st)}, "
                    f"route_len={len(route)}")
            else:
                lid = list(net.lines.keys())[0]
                line = net.lines[lid]
                resp = {"start_time": format_time(line['start_time']),
                        "route": line['stations']}
                log(">> fallback route")

            sock.sendall((json.dumps(resp) + '\n').encode())
            result = read_line()
            log(f"<< {result} ({time.time()-t_start:.1f}s)")

    except (ConnectionError, socket.timeout) as e:
        log(f"Connection: {e}")
    except Exception as e:
        log(f"Error: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)
    finally:
        sock.close()
        log("Done.")


if __name__ == '__main__':
    random.seed(42)
    main()