#!/usr/bin/env python3
import json
import math
import socket
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from heapq import heappush, heappop

HOST = "localhost"
PORT = 7474
BOT_NAME = "gpt54_bot"

INF = 10**18


def parse_hhmm(s: str) -> int:
    h, m = map(int, s.split(":"))
    return h * 60 + m


def fmt_hhmm(x: int) -> str:
    x %= 24 * 60
    return f"{x // 60:02d}:{x % 60:02d}"


def recv_line(sock_file) -> str:
    line = sock_file.readline()
    if not line:
        raise EOFError("connection closed")
    return line.decode("utf-8").rstrip("\n")


def recv_exact(sock_file, n: int) -> bytes:
    data = sock_file.read(n)
    if data is None or len(data) != n:
        raise EOFError("unexpected EOF while reading payload")
    return data


@dataclass(frozen=True)
class Ride:
    line_id: str
    direction: int          # +1 forward, -1 backward
    from_hub: int
    to_hub: int
    depart_offset: int      # minutes from line terminal departure to reach from_hub
    travel_time: int
    visit_mask: int
    station_seq: tuple      # actual station names along the ride, inclusive


class SubwaySolver:
    def __init__(self, payload: dict):
        self.lines = payload["lines"]
        self.transfers = payload.get("transfers", [])
        self.station_to_hub = {}
        self.hub_members = []
        self.station_lines = defaultdict(list)
        self.station_index_on_line = {}
        self.line_by_id = {}
        self.all_stations = set()
        self.build_hubs()
        self.build_lines()
        self.build_masks()
        self.build_rides()

    def build_hubs(self):
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for line in self.lines:
            for s in line["stations"]:
                self.all_stations.add(s)
                parent.setdefault(s, s)

        for a, b in self.transfers:
            union(a, b)

        groups = defaultdict(list)
        for s in self.all_stations:
            groups[find(s)].append(s)

        self.hub_members = []
        for members in groups.values():
            idx = len(self.hub_members)
            members = sorted(members)
            self.hub_members.append(members)
            for s in members:
                self.station_to_hub[s] = idx

        self.hub_count = len(self.hub_members)

    def build_lines(self):
        self.line_by_id = {}
        for line in self.lines:
            lid = line["id"]
            stations = line["stations"]
            segments = line["segments"]
            prefix = [0]
            for t in segments:
                prefix.append(prefix[-1] + t)
            info = {
                "id": lid,
                "stations": stations,
                "segments": segments,
                "prefix": prefix,
                "interval": line["interval"],
                "start": parse_hhmm(line["start_time"]),
                "end": parse_hhmm(line["end_time"]),
            }
            self.line_by_id[lid] = info
            for i, s in enumerate(stations):
                self.station_lines[s].append(lid)
                self.station_index_on_line[(lid, s)] = i

    def build_masks(self):
        self.hub_bit = {}
        for h in range(self.hub_count):
            self.hub_bit[h] = 1 << h
        self.full_mask = (1 << self.hub_count) - 1

    def build_rides(self):
        self.rides_from_hub = defaultdict(list)
        self.hub_lines = defaultdict(set)

        for line in self.lines:
            lid = line["id"]
            stations = line["stations"]
            prefix = self.line_by_id[lid]["prefix"]

            for s in stations:
                self.hub_lines[self.station_to_hub[s]].add(lid)

            n = len(stations)
            for i in range(n):
                hi = self.station_to_hub[stations[i]]

                # forward
                seen_mask = 0
                for j in range(i, n):
                    hj = self.station_to_hub[stations[j]]
                    seen_mask |= self.hub_bit[hj]
                    if j > i and hj != hi:
                        seq = tuple(stations[i:j + 1])
                        ride = Ride(
                            line_id=lid,
                            direction=+1,
                            from_hub=hi,
                            to_hub=hj,
                            depart_offset=prefix[i],
                            travel_time=prefix[j] - prefix[i],
                            visit_mask=seen_mask,
                            station_seq=seq,
                        )
                        self.rides_from_hub[hi].append(ride)

                # backward
                seen_mask = 0
                for j in range(i, -1, -1):
                    hj = self.station_to_hub[stations[j]]
                    seen_mask |= self.hub_bit[hj]
                    if j < i and hj != hi:
                        seq = tuple(stations[i:j - 1:-1]) if j - 1 >= 0 else tuple(stations[i::-1])
                        ride = Ride(
                            line_id=lid,
                            direction=-1,
                            from_hub=hi,
                            to_hub=hj,
                            depart_offset=(prefix[-1] - prefix[i]),
                            travel_time=prefix[i] - prefix[j],
                            visit_mask=seen_mask,
                            station_seq=seq,
                        )
                        self.rides_from_hub[hi].append(ride)

    def next_departure(self, line_id: str, direction: int, from_station: str, earliest: int) -> int:
        line = self.line_by_id[line_id]
        idx = self.station_index_on_line[(line_id, from_station)]
        if direction == +1:
            offset = line["prefix"][idx]
        else:
            offset = line["prefix"][-1] - line["prefix"][idx]

        base_start = line["start"] + offset
        last_depart = line["end"] + offset

        if earliest <= base_start:
            depart = base_start
        else:
            k = (earliest - base_start + line["interval"] - 1) // line["interval"]
            depart = base_start + k * line["interval"]

        if depart > last_depart:
            return INF
        return depart

    def hub_station_for_line(self, hub: int, line_id: str):
        for s in self.hub_members[hub]:
            if line_id in self.station_lines[s]:
                return s
        return None

    def preprocess_lower_bounds(self):
        deg = [len(self.rides_from_hub[h]) for h in range(self.hub_count)]
        min_edge = [INF] * self.hub_count
        for h in range(self.hub_count):
            for r in self.rides_from_hub[h]:
                min_edge[h] = min(min_edge[h], r.travel_time)
            if min_edge[h] == INF:
                min_edge[h] = 0
        self.min_edge = min_edge
        self.avg_min_edge = max(1, sum(min_edge) // max(1, len(min_edge)))

    def solve(self):
        self.preprocess_lower_bounds()

        start_candidates = []
        for h in range(self.hub_count):
            lines_here = set()
            for s in self.hub_members[h]:
                lines_here.update(self.station_lines[s])
            earliest = INF
            for lid in lines_here:
                line = self.line_by_id[lid]
                for s in self.hub_members[h]:
                    if lid in self.station_lines[s]:
                        idx = self.station_index_on_line[(lid, s)]
                        t1 = line["start"] + line["prefix"][idx]
                        t2 = line["start"] + (line["prefix"][-1] - line["prefix"][idx])
                        earliest = min(earliest, t1, t2)
            if earliest == INF:
                earliest = 0
            start_candidates.append((earliest, h))

        start_candidates.sort()
        start_candidates = start_candidates[: min(12, len(start_candidates))]

        best = None
        best_duration = INF

        for start_time, start_hub in start_candidates:
            result = self.beam_search(start_hub, start_time, beam_width=160, expansions=5000, incumbent=best_duration)
            if result and result["duration"] < best_duration:
                best = result
                best_duration = result["duration"]

        if best is None:
            h = start_candidates[0][1]
            station = self.hub_members[h][0]
            return {
                "start_time": fmt_hhmm(start_candidates[0][0]),
                "route": [station],
            }

        return {
            "start_time": fmt_hhmm(best["start_time"]),
            "route": best["route"],
        }

    def optimistic_remaining(self, mask: int) -> int:
        remaining = self.full_mask ^ mask
        cnt = remaining.bit_count()
        if cnt <= 1:
            return 0
        return (cnt - 1) * self.avg_min_edge

    def beam_search(self, start_hub: int, start_time: int, beam_width: int, expansions: int, incumbent: int):
        start_station = self.hub_members[start_hub][0]
        start_mask = self.hub_bit[start_hub]

        states = [{
            "hub": start_hub,
            "time": start_time,
            "mask": start_mask,
            "route": [start_station],
            "last_line": None,
        }]

        best_finish = None
        best_finish_duration = incumbent
        seen = {}

        for _ in range(expansions):
            candidates = []

            for st in states:
                if st["mask"] == self.full_mask:
                    duration = st["time"] - start_time
                    if duration < best_finish_duration:
                        best_finish_duration = duration
                        best_finish = {
                            "start_time": start_time,
                            "duration": duration,
                            "route": st["route"],
                        }
                    continue

                cur_hub = st["hub"]
                cur_time = st["time"]
                cur_mask = st["mask"]

                rides = self.rides_from_hub[cur_hub]
                scored_moves = []

                for ride in rides:
                    from_station = self.hub_station_for_line(cur_hub, ride.line_id)
                    if from_station is None:
                        continue

                    earliest_board = cur_time if st["last_line"] == ride.line_id else cur_time + 1
                    depart = self.next_departure(ride.line_id, ride.direction, from_station, earliest_board)
                    if depart >= INF:
                        continue

                    arrive = depart + ride.travel_time
                    new_mask = cur_mask | ride.visit_mask
                    gain = (new_mask ^ cur_mask).bit_count()
                    if gain == 0:
                        continue

                    est_total = (arrive - start_time) + self.optimistic_remaining(new_mask)
                    if est_total >= best_finish_duration:
                        continue

                    scored_moves.append((-(gain * 1000) + (arrive - cur_time), ride, depart, arrive, new_mask))

                scored_moves.sort()
                for _, ride, depart, arrive, new_mask in scored_moves[:8]:
                    route = st["route"][:]
                    seq = list(ride.station_seq)
                    if route[-1] == seq[0]:
                        route.extend(seq[1:])
                    else:
                        route.extend(seq)

                    key = (ride.to_hub, new_mask)
                    old_best = seen.get(key)
                    if old_best is not None and old_best <= arrive:
                        continue
                    seen[key] = arrive

                    candidates.append({
                        "hub": ride.to_hub,
                        "time": arrive,
                        "mask": new_mask,
                        "route": route,
                        "last_line": ride.line_id,
                        "score": (arrive - start_time) + self.optimistic_remaining(new_mask) - 20 * new_mask.bit_count(),
                    })

            if not candidates:
                break

            candidates.sort(key=lambda x: (x["score"], x["time"], -x["mask"].bit_count(), len(x["route"])))
            states = candidates[:beam_width]

        for st in states:
            if st["mask"] == self.full_mask:
                duration = st["time"] - start_time
                if duration < best_finish_duration:
                    best_finish_duration = duration
                    best_finish = {
                        "start_time": start_time,
                        "duration": duration,
                        "route": st["route"],
                    }

        return best_finish


def handle_round(payload: dict) -> dict:
    solver = SubwaySolver(payload)
    return solver.solve()


def main():
    with socket.create_connection((HOST, PORT)) as sock:
        sock_file = sock.makefile("rwb")
        sock_file.write((BOT_NAME + "\n").encode("utf-8"))
        sock_file.flush()

        while True:
            try:
                line1 = recv_line(sock_file)
            except EOFError:
                break

            if not line1:
                continue

            if line1.startswith("ROUND "):
                line2 = recv_line(sock_file)
                if not line2.startswith("SIZE "):
                    raise ValueError(f"expected SIZE line, got: {line2}")
                size = int(line2.split()[1])
                payload_bytes = recv_exact(sock_file, size)
                payload = json.loads(payload_bytes.decode("utf-8"))

                result = handle_round(payload)
                out = json.dumps(result, separators=(",", ":")) + "\n"
                sock_file.write(out.encode("utf-8"))
                sock_file.flush()

                reply = recv_line(sock_file)
                print(reply, file=sys.stderr)

            elif line1.startswith("VALID ") or line1.startswith("INVALID ") or line1 == "TIMEOUT":
                print(line1, file=sys.stderr)
            else:
                print(line1, file=sys.stderr)


if __name__ == "__main__":
    main()
