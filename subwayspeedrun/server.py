"""
Subway Speedrun Tournament Server.

Generates random subway networks, sends them to bots over TCP,
validates routes, scores results.
"""
import socket
import threading
import time
import random
import json
import string

# Configuration
HOST = 'localhost'
PORT = 7474
MAX_ROUNDS = 10
REGISTRATION_WINDOW = 10.0
ROUND_TIMEOUT = 60.0
LOG_PATH = 'results.log'

# Network generation limits
MAX_LINES = 12
MAX_STATIONS_PER_LINE = 20
MAX_TRANSFERS = 10
MAX_TOTAL_STATIONS = 150


# ─── Network Generation ──────────────────────────────────────────────────────

def generate_network(difficulty):
    """Generate a random subway network. Difficulty 0.0-1.0 scales size."""
    n_lines = random.randint(3, max(3, int(3 + difficulty * (MAX_LINES - 3))))

    lines = []
    all_stations = set()
    line_ids = list(string.ascii_uppercase[:n_lines])

    for lid in line_ids:
        n_stations = random.randint(4, max(4, int(4 + difficulty * (MAX_STATIONS_PER_LINE - 4))))
        # Cap total stations
        if len(all_stations) + n_stations > MAX_TOTAL_STATIONS:
            n_stations = max(4, MAX_TOTAL_STATIONS - len(all_stations))

        stations = [f"{lid}{i}" for i in range(n_stations)]
        segments = [random.randint(3, 15) for _ in range(n_stations - 1)]
        interval = random.choice([8, 10, 12, 15, 20, 25, 30])

        # Start time between 05:00 and 07:30
        start_h = random.randint(5, 7)
        start_m = random.choice([0, 15, 30, 45])
        if start_h == 7:
            start_m = random.choice([0, 15, 30])

        # End time between 21:00 and 00:30
        end_h = random.randint(21, 23)
        end_m = random.choice([0, 15, 30, 45])

        lines.append({
            "id": lid,
            "stations": stations,
            "segments": segments,
            "interval": interval,
            "start_time": f"{start_h:02d}:{start_m:02d}",
            "end_time": f"{end_h:02d}:{end_m:02d}",
        })
        all_stations.update(stations)

    # Generate transfers (connect lines at random interior stations)
    min_transfers = max(1, n_lines - 1)
    max_transfers = min(MAX_TRANSFERS, n_lines * 2)
    if max_transfers < min_transfers:
        max_transfers = min_transfers
    n_transfers = random.randint(min_transfers, max_transfers)
    transfers = []
    used_stations = set()

    # Ensure connectivity: connect each line to at least one other
    shuffled_lines = list(range(n_lines))
    random.shuffle(shuffled_lines)
    for i in range(len(shuffled_lines) - 1):
        l1 = lines[shuffled_lines[i]]
        l2 = lines[shuffled_lines[i + 1]]
        # Pick interior stations (not terminals)
        s1_choices = [s for s in l1["stations"][1:-1] if s not in used_stations]
        s2_choices = [s for s in l2["stations"][1:-1] if s not in used_stations]
        if s1_choices and s2_choices:
            s1 = random.choice(s1_choices)
            s2 = random.choice(s2_choices)
            transfers.append([s1, s2])
            used_stations.add(s1)
            used_stations.add(s2)

    # Add more random transfers up to n_transfers
    attempts = 0
    while len(transfers) < n_transfers and attempts < 100:
        attempts += 1
        l1, l2 = random.sample(range(n_lines), 2)
        s1_choices = [s for s in lines[l1]["stations"][1:-1] if s not in used_stations]
        s2_choices = [s for s in lines[l2]["stations"][1:-1] if s not in used_stations]
        if s1_choices and s2_choices:
            s1 = random.choice(s1_choices)
            s2 = random.choice(s2_choices)
            transfers.append([s1, s2])
            used_stations.add(s1)
            used_stations.add(s2)

    return {"lines": lines, "transfers": transfers}


# ─── Time Helpers ─────────────────────────────────────────────────────────────

def parse_time(s):
    """Parse HH:MM to minutes since midnight."""
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def fmt_time(minutes):
    """Format minutes since midnight to HH:MM."""
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


# ─── Route Validation ─────────────────────────────────────────────────────────

def build_line_info(network):
    """Precompute line data for validation."""
    info = {}
    for line in network["lines"]:
        lid = line["id"]
        stations = line["stations"]
        segments = line["segments"]
        interval = line["interval"]
        start = parse_time(line["start_time"])
        end = parse_time(line["end_time"])
        if end < start:
            end += 24 * 60  # handle past midnight

        # Cumulative distances from station 0
        cum = [0]
        for s in segments:
            cum.append(cum[-1] + s)
        total_time = cum[-1]

        # Station index lookup
        idx = {s: i for i, s in enumerate(stations)}

        info[lid] = {
            "stations": stations,
            "segments": segments,
            "interval": interval,
            "start": start,
            "end": end,
            "cum": cum,
            "total_time": total_time,
            "idx": idx,
        }
    return info


def build_hub_map(network):
    """Map station -> set of equivalent stations at the same hub."""
    hubs = {}
    for t in network["transfers"]:
        s1, s2 = t[0], t[1]
        # Merge hub groups
        g1 = hubs.get(s1, {s1})
        g2 = hubs.get(s2, {s2})
        merged = g1 | g2
        for s in merged:
            hubs[s] = merged
    return hubs


def station_line(station, line_info):
    """Find which line a station belongs to."""
    for lid, info in line_info.items():
        if station in info["idx"]:
            return lid
    return None


def next_train_at(line_info, lid, station, direction, arrive_time, need_buffer=False):
    """
    Find the next train on line `lid` at `station` going in `direction`
    ('fwd' = toward last station, 'rev' = toward first station)
    that the passenger can board, arriving at `arrive_time`.

    If need_buffer=True, passenger must arrive at least 1 minute before departure.

    Returns (board_time, arrival_at_next_station) or None if no train available.
    """
    info = line_info[lid]
    idx = info["idx"][station]
    interval = info["interval"]
    start = info["start"]
    end = info["end"]
    cum = info["cum"]
    total_time = info["total_time"]
    n = len(info["stations"])

    if direction == 'fwd':
        # Train departs terminal 0 at start + k*interval
        # Arrives at station `idx` at departure + cum[idx]
        travel_to_station = cum[idx]
    else:
        # Train departs terminal (n-1) at start + k*interval
        # Arrives at station `idx` at departure + (total_time - cum[idx])
        travel_to_station = total_time - cum[idx]

    min_board = arrive_time + (1 if need_buffer else 0)

    # Find first k where start + k*interval + travel_to_station >= min_board
    # and start + k*interval <= end
    first_departure = start
    if travel_to_station + first_departure < min_board:
        # Need a later train
        k = max(0, (min_board - travel_to_station - first_departure + interval - 1) // interval)
        first_departure = start + k * interval

    if first_departure > end:
        return None  # No more trains

    train_at_station = first_departure + travel_to_station
    if train_at_station < min_board:
        first_departure += interval
        if first_departure > end:
            return None
        train_at_station = first_departure + travel_to_station

    return train_at_station  # Time when train is at this station


def validate_route(network, start_time_str, route):
    """
    Validate a route and compute total duration.
    Returns (True, duration, message) or (False, 0, error_message).
    """
    if not route:
        return False, 0, "Empty route"

    line_info = build_line_info(network)
    hub_map = build_hub_map(network)

    # Collect all stations that need visiting
    all_stations = set()
    for line in network["lines"]:
        all_stations.update(line["stations"])

    # Track visited stations (hub-aware)
    visited = set()

    def mark_visited(station):
        visited.add(station)
        if station in hub_map:
            visited.update(hub_map[station])

    current_time = parse_time(start_time_str)
    start_time = current_time

    # Mark first station as visited
    mark_visited(route[0])

    i = 0
    while i < len(route) - 1:
        current_station = route[i]
        next_station = route[i + 1]

        # Check if next_station is on the same line and adjacent
        current_line = station_line(current_station, line_info)
        next_line = station_line(next_station, line_info)

        if current_line is None:
            return False, 0, f"Station {current_station} not found in any line"

        # Case 1: Same line, find direction and ride
        if current_line == next_line:
            info = line_info[current_line]
            ci = info["idx"][current_station]
            ni = info["idx"][next_station]

            if abs(ci - ni) != 1:
                return False, 0, f"Stations {current_station} and {next_station} are not adjacent on line {current_line}"

            direction = 'fwd' if ni > ci else 'rev'

            # Find the train we're on or need to board
            # Check if we're already on a moving train (continuing a ride)
            # For the first station or after a transfer, we need to board
            need_buffer = (i == 0) or (station_line(route[i-1], line_info) != current_line if i > 0 else True)

            # Actually check if previous move was a transfer
            if i > 0:
                prev_station = route[i - 1]
                prev_line = station_line(prev_station, line_info)
                if prev_line == current_line:
                    prev_idx = info["idx"][prev_station]
                    prev_dir = 'fwd' if ci > prev_idx else 'rev'
                    if prev_dir == direction:
                        # Continuing on same train, same direction
                        need_buffer = False

            if need_buffer:
                # Need to board a new train
                train_time = next_train_at(line_info, current_line, current_station, direction, current_time, need_buffer=True)
                if train_time is None:
                    return False, 0, f"No train available at {current_station} on line {current_line} direction {direction} after {fmt_time(current_time)}"
                current_time = train_time

            # Travel to next station
            segment_time = info["segments"][min(ci, ni)]
            current_time += segment_time
            mark_visited(next_station)
            i += 1

        # Case 2: Transfer (different lines, must share a hub)
        elif next_line is not None:
            # Check hub connection
            hub_connected = False
            if current_station in hub_map and next_station in hub_map.get(current_station, set()):
                hub_connected = True
            else:
                # Check transfers list directly
                for t in network["transfers"]:
                    if (current_station == t[0] and next_station == t[1]) or \
                       (current_station == t[1] and next_station == t[0]):
                        hub_connected = True
                        break

            if not hub_connected:
                return False, 0, f"No transfer connection between {current_station} and {next_station}"

            # Transfer is instant (0 minutes), but need 1-minute buffer for next train
            mark_visited(next_station)
            i += 1
        else:
            return False, 0, f"Station {next_station} not found in any line"

    # Check all stations visited
    unvisited = all_stations - visited
    if unvisited:
        return False, 0, f"Unvisited stations: {sorted(unvisited)}"

    duration = current_time - start_time
    return True, duration, "OK"


# ─── Client Handling ──────────────────────────────────────────────────────────

class Client:
    def __init__(self, sock, name):
        self.sock = sock
        self.name = name
        self.score = 0
        self.f = sock.makefile('r', encoding='utf-8')

    def send(self, data):
        try:
            self.sock.sendall(data.encode('utf-8'))
        except OSError:
            pass

    def readline(self, timeout=None):
        if timeout:
            self.sock.settimeout(timeout)
        try:
            line = self.f.readline()
            if not line:
                return None
            return line.strip()
        except (OSError, socket.timeout):
            return None
        finally:
            if timeout:
                self.sock.settimeout(None)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ─── Tournament ───────────────────────────────────────────────────────────────

def rotate_log():
    """Rotate results.log -> results.log.1, results.log.1 -> results.log.2, etc."""
    import os
    if not os.path.exists(LOG_PATH):
        return
    # Find highest existing number
    n = 1
    while os.path.exists(f"{LOG_PATH}.{n}"):
        n += 1
    # Rename from highest down
    for i in range(n - 1, 0, -1):
        os.rename(f"{LOG_PATH}.{i}", f"{LOG_PATH}.{i+1}")
    os.rename(LOG_PATH, f"{LOG_PATH}.1")


def verify_solvable(network):
    """Check that all stations are reachable via lines + transfers."""
    # Build adjacency: stations connected on same line or via transfer
    adj = {}
    for line in network["lines"]:
        for i, s in enumerate(line["stations"]):
            if s not in adj:
                adj[s] = set()
            if i > 0:
                adj[s].add(line["stations"][i-1])
            if i < len(line["stations"]) - 1:
                adj[s].add(line["stations"][i+1])
    for t in network["transfers"]:
        s1, s2 = t[0], t[1]
        if s1 not in adj: adj[s1] = set()
        if s2 not in adj: adj[s2] = set()
        adj[s1].add(s2)
        adj[s2].add(s1)

    # BFS from any station
    all_stations = set(adj.keys())
    if not all_stations:
        return False
    start = next(iter(all_stations))
    visited = set()
    queue = [start]
    visited.add(start)
    while queue:
        s = queue.pop()
        for n in adj.get(s, []):
            if n not in visited:
                visited.add(n)
                queue.append(n)
    return visited == all_stations


def generate_solvable_network(difficulty, max_attempts=50):
    """Generate networks until we get one that's fully connected."""
    for _ in range(max_attempts):
        network = generate_network(difficulty)
        if verify_solvable(network):
            return network
    # Fallback: return last attempt anyway
    return network


def run_tournament():
    rotate_log()
    log = open(LOG_PATH, 'w', encoding='utf-8')

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(10)
    server_sock.settimeout(1.0)

    clients = []

    print(f"[*] Server live on {HOST}:{PORT}. Registration: {REGISTRATION_WINDOW}s")
    start_reg = time.time()
    while time.time() - start_reg < REGISTRATION_WINDOW:
        try:
            conn, addr = server_sock.accept()
            conn.settimeout(None)
            name_line = conn.makefile('r').readline().strip()
            if name_line:
                client = Client(conn, name_line)
                clients.append(client)
                print(f"[*] Bot '{name_line}' joined.")
        except socket.timeout:
            continue

    if not clients:
        print("[!] No participants.")
        log.close()
        return

    print(f"[*] {len(clients)} bots registered. Starting tournament.\n")

    for round_num in range(1, MAX_ROUNDS + 1):
        # Generate solvable network with increasing difficulty
        difficulty = (round_num - 1) / (MAX_ROUNDS - 1)
        network = generate_solvable_network(difficulty)

        n_stations = sum(len(l["stations"]) for l in network["lines"])
        n_lines = len(network["lines"])
        n_transfers = len(network["transfers"])

        payload = json.dumps(network)
        payload_bytes = len(payload.encode('utf-8'))

        print(f"--- ROUND {round_num}: {n_lines} lines, {n_stations} stations, {n_transfers} transfers ---")
        log.write(f"--- ROUND {round_num}: {n_lines} lines, {n_stations} stations, {n_transfers} transfers ---\n")
        log.write(f"NETWORK:\n{json.dumps(network, indent=2)}\n\n")

        round_start = time.monotonic()

        # Send to all clients
        for client in clients:
            client.send(f"ROUND {round_num}\n")
            client.send(f"SIZE {payload_bytes}\n")
            client.send(payload)

        # Collect responses in parallel
        results = {}     # name -> (duration, route_len, elapsed_ms, status)
        solutions = {}   # name -> answer dict (for logging)
        result_lock = threading.Lock()

        def collect_response(client):
            response = client.readline(timeout=ROUND_TIMEOUT)
            elapsed = (time.monotonic() - round_start) * 1000

            if response is None:
                status = "TIMEOUT" if elapsed > ROUND_TIMEOUT * 900 else "DISCONNECTED"
                with result_lock:
                    results[client.name] = (None, 0, elapsed, status)
                try:
                    client.send(f"{status}\n")
                except:
                    pass
                return

            try:
                answer = json.loads(response)
                route_start = answer.get("start_time", "06:00")
                route = answer.get("route", [])

                valid, duration, msg = validate_route(network, route_start, route)

                with result_lock:
                    if valid:
                        results[client.name] = (duration, len(route), elapsed, "VALID")
                        solutions[client.name] = answer
                    else:
                        results[client.name] = (None, 0, elapsed, f"INVALID: {msg}")
                        solutions[client.name] = answer

                if valid:
                    client.send(f"VALID {duration}\n")
                else:
                    client.send(f"INVALID {msg}\n")
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                with result_lock:
                    results[client.name] = (None, 0, elapsed, f"INVALID: parse error: {e}")
                client.send(f"INVALID parse error\n")

        threads = []
        for client in clients:
            t = threading.Thread(target=collect_response, args=(client,), daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join(timeout=ROUND_TIMEOUT + 5)

        # Score: +3/+2/+1 for top 3 shortest valid durations
        valid_results = [(name, dur, rt) for name, (dur, _, rt, status) in results.items()
                        if dur is not None]
        valid_results.sort(key=lambda x: (x[1], x[2]))  # sort by duration, then response time

        points = [3, 2, 1]
        for i, (name, dur, rt) in enumerate(valid_results):
            if i < len(points):
                for c in clients:
                    if c.name == name:
                        c.score += points[i]

        # Log results
        for name, (dur, route_len, elapsed, status) in sorted(results.items(),
                key=lambda x: (x[1][0] if x[1][0] is not None else 99999, x[1][2])):
            if dur is not None:
                rank = next((i+1 for i, (n, _, _) in enumerate(valid_results) if n == name), 0)
                pts = points[rank-1] if rank <= len(points) else 0
                client_score = next(c.score for c in clients if c.name == name)
                line = f"  {name:<20} | {dur:>4}min | {elapsed:>8.0f}ms | +{pts} | total: {client_score}"
            else:
                client_score = next(c.score for c in clients if c.name == name)
                line = f"  {name:<20} | {status:<30} | {elapsed:>8.0f}ms | +0 | total: {client_score}"
            print(line)
            log.write(line + "\n")

        # Log solutions
        log.write("\nSOLUTIONS:\n")
        for name in sorted(solutions.keys()):
            dur = results[name][0]
            status = "VALID" if dur is not None else results[name][3]
            sol = solutions[name]
            log.write(f"  {name} ({status}{f', {dur}min' if dur else ''}):\n")
            log.write(f"    start_time: {sol.get('start_time', '?')}\n")
            route = sol.get('route', [])
            log.write(f"    route ({len(route)} stations): {json.dumps(route)}\n")

        log.write("\n")
        log.flush()
        time.sleep(1)

    # Final standings
    header = "=" * 60 + "\nFINAL TOURNAMENT RESULTS\n" + "=" * 60
    print("\n" + header)
    log.write("\n" + header + "\n")

    sorted_clients = sorted(clients, key=lambda c: -c.score)
    for i, client in enumerate(sorted_clients):
        line = f"  #{i+1}  {client.name:<20} {client.score:>3} points"
        print(line)
        log.write(line + "\n")

    log.close()
    server_sock.close()
    for c in clients:
        c.close()


if __name__ == "__main__":
    run_tournament()
