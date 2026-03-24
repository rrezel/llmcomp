import socket
import json
import time
import heapq
import random

HOST = 'localhost'
PORT = 7474
BOT_NAME = 'gemini_speedrun_bot\n'
TIME_LIMIT_PER_ROUND_SEC = 55.0  # 5s buffer for network latency

def parse_time(t_str, is_end=False):
    """Converts HH:MM string to integer minutes from midnight."""
    h, m = map(int, t_str.split(':'))
    mins = h * 60 + m
    # Handle end times that wrap past midnight (e.g., 00:00 -> 1440)
    if is_end and mins <= 180:
        mins += 1440
    elif is_end and mins == 0:
        mins = 1440
    return mins

def compute_route(data):
    start_compute_time = time.time()
    
    lines = {}
    station_lines = {}
    all_stations = set()
    
    # 1. Precompute static line data and offsets
    for l in data['lines']:
        lid = l['id']
        l['start_time_m'] = parse_time(l['start_time'])
        l['end_time_m'] = parse_time(l['end_time'], is_end=True)
        
        # Forward travel offsets
        offsets_fwd = [0]
        curr = 0
        for seg in l['segments']:
            curr += seg
            offsets_fwd.append(curr)
        l['offset_fwd'] = offsets_fwd
        
        # Reverse travel offsets
        offsets_rev = [0] * len(l['stations'])
        curr = 0
        for i in range(len(l['segments'])-1, -1, -1):
            curr += l['segments'][i]
            offsets_rev[i] = curr
        l['offset_rev'] = offsets_rev
        
        l['station_idx'] = {st: i for i, st in enumerate(l['stations'])}
        
        lines[lid] = l
        for st in l['stations']:
            all_stations.add(st)
            if st not in station_lines:
                station_lines[st] = []
            station_lines[st].append(lid)
            
    # 2. Build connected components for transfer hubs
    hub_map = {st: {st} for st in all_stations}
    if 'transfers' in data:
        for u, v in data['transfers']:
            if u in hub_map and v in hub_map:
                merged = hub_map[u].union(hub_map[v])
                for node in merged:
                    hub_map[node] = merged
                    
    # Map each station to a canonical hub ID to track unique visits
    hub_id_map = {st: min(hub_map[st]) for st in all_stations}
    all_hub_ids = set(hub_id_map.values())
    total_hubs = len(all_hub_ids)
    
    # 3. Find the absolute earliest start time to maximize available running trains
    earliest_network_start = min([l['start_time_m'] for l in lines.values()])
    
    def get_earliest_departure(st):
        best = float('inf')
        for lid in station_lines[st]:
            l = lines[lid]
            for d, offsets in [(1, l['offset_fwd']), (-1, l['offset_rev'])]:
                offset = offsets[l['station_idx'][st]]
                dep = l['start_time_m'] + offset
                if dep < best:
                    best = dep
        return best if best != float('inf') else earliest_network_start
        
    station_start_times = {st: get_earliest_departure(st) for st in all_stations}
    stations_list = list(all_stations)
    
    best_duration = float('inf')
    best_route = []
    best_start_time_str = "06:00"
    
    # 4. GRASP Engine (Greedy Randomized Adaptive Search Procedure)
    while time.time() - start_compute_time < TIME_LIMIT_PER_ROUND_SEC:
        start_st = random.choice(stations_list)
        global_start_time = station_start_times[start_st]
        
        current_time = global_start_time
        route = [start_st]
        visited_hubs = set([hub_id_map[start_st]])
        
        curr_u, curr_L, curr_D = start_st, None, None
        possible = True
        
        while len(visited_hubs) < total_hubs:
            # A. Run Time-Dependent Dijkstra
            pq = [(current_time, curr_u, curr_L, curr_D)]
            dist = {(curr_u, curr_L, curr_D): current_time}
            parent = {(curr_u, curr_L, curr_D): None}
            
            while pq:
                t, u, L, D = heapq.heappop(pq)
                if t > dist.get((u, L, D), float('inf')):
                    continue
                    
                # Action 1: Transfer hub (0 minute cost)
                for v in hub_map[u]:
                    if v != u:
                        next_state = (v, None, None)
                        if t < dist.get(next_state, float('inf')):
                            dist[next_state] = t
                            parent[next_state] = (u, L, D)
                            heapq.heappush(pq, (t, v, None, None))
                            
                        
                # Action 2: Travel on adjacent line segments
                for line_id in station_lines[u]:
                    l = lines[line_id]
                    idx = l['station_idx'][u]
                    
                    # Check Forward (1) and Reverse (-1)
                    for nxt_idx, direction, offsets in [
                        (idx + 1, 1, l['offset_fwd']), 
                        (idx - 1, -1, l['offset_rev'])
                    ]:
                        if 0 <= nxt_idx < len(l['stations']):
                            v = l['stations'][nxt_idx]
                            
                            # Are we staying on the exact same train?
                            if line_id == L and direction == D:
                                segment_time = l['segments'][idx] if direction == 1 else l['segments'][idx - 1]
                                next_t = t + segment_time
                            else:
                                # New train: Calculate arrival based on timetable & buffer
                                buffer = 1 if (L is not None or t > global_start_time) else 0
                                offset = offsets[idx]
                                diff = (t + buffer) - offset - l['start_time_m']
                                k = 0 if diff <= 0 else (diff + l['interval'] - 1) // l['interval']
                                term_t = l['start_time_m'] + k * l['interval']
                                
                                if term_t <= l['end_time_m']:
                                    segment_time = l['segments'][idx] if direction == 1 else l['segments'][idx - 1]
                                    next_t = term_t + offset + segment_time
                                else:
                                    next_t = float('inf')
                                    
                            if next_t < float('inf'):
                                next_state = (v, line_id, direction)
                                if next_t < dist.get(next_state, float('inf')):
                                    dist[next_state] = next_t
                                    parent[next_state] = (u, L, D)
                                    heapq.heappush(pq, (next_t, v, line_id, direction))
                                    
            # B. Evaluate Dijkstra results for unvisited hubs
            hub_best_times = {}
            hub_best_states = {}
            
            for state, t in dist.items():
                u = state[0]
                hid = hub_id_map[u]
                if hid not in visited_hubs:
                    if hid not in hub_best_times or t < hub_best_times[hid]:
                        hub_best_times[hid] = t
                        hub_best_states[hid] = state
                        
            if not hub_best_times:
                possible = False
                break # Graph disconnected or trains halted for the night
                
            # C. Random Greedy Choice (Pick from Top 3 closest hubs)
            sorted_hubs = sorted(hub_best_times.keys(), key=lambda h: hub_best_times[h])
            top_k = min(3, len(sorted_hubs))
            chosen_hub = sorted_hubs[random.randint(0, top_k - 1)]
            target_state = hub_best_states[chosen_hub]
            
            # D. Reconstruct Path and Update Simulation state
            path = []
            curr = target_state
            while curr is not None:
                path.append(curr[0])
                curr = parent[curr]
            path.reverse()
            
            for st in path[1:]:
                route.append(st)
                visited_hubs.add(hub_id_map[st])
                
            current_time = dist[target_state]
            curr_u, curr_L, curr_D = target_state
            
        # 5. Record best configuration
        if possible:
            duration = current_time - global_start_time
            if duration < best_duration:
                best_duration = duration
                best_route = list(route)
                best_start_time_str = f"{(global_start_time // 60) % 24:02d}:{global_start_time % 60:02d}"
                
    return {
        "start_time": best_start_time_str,
        "route": best_route
    }

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((HOST, PORT))
        sock.sendall(BOT_NAME.encode())
        print(f"Connected to {HOST}:{PORT} as {BOT_NAME.strip()}")
        
        def read_line():
            buf = bytearray()
            while True:
                char = sock.recv(1)
                if not char:
                    return None
                buf.extend(char)
                if char == b'\n':
                    return buf.decode()
                    
        while True:
            line1 = read_line()
            if not line1:
                break
                
            if not line1.startswith('ROUND'):
                continue
            
            print(f"\n--- {line1.strip()} ---")
            
            line2 = read_line()
            size = int(line2.split()[1])
            
            # Read exact byte payload (prevents TCP fragmentation issues)
            payload_bytes = bytearray()
            while len(payload_bytes) < size:
                chunk = sock.recv(size - len(payload_bytes))
                if not chunk:
                    break
                payload_bytes.extend(chunk)
                
            data = json.loads(payload_bytes.decode())
            print(f"Data received. Total Lines: {len(data['lines'])}. Simulating paths...")
            
            response = compute_route(data)
            
            sock.sendall((json.dumps(response) + '\n').encode())
            print(f"Submitted route. Start: {response['start_time']}, Stations: {len(response['route'])}")
            
            resp = read_line()
            print("Server Evaluation:", resp.strip())
            
    except ConnectionRefusedError:
        print(f"Could not connect to server at {HOST}:{PORT}")
    finally:
        sock.close()

if __name__ == "__main__":
    main()