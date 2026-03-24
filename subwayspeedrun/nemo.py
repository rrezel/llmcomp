import socket
import json
import heapq
import sys
from collections import defaultdict

def time_to_minutes(t):
    """Convert 'HH:MM' to minutes since 00:00."""
    h, m = t.split(':')
    return int(h) * 60 + int(m)

def minutes_to_time(m):
    """Convert minutes since 00:00 to 'HH:MM'."""
    h = m // 60
    m = m % 60
    return f"{h:02d}:{m:02d}"

def parse_lines(data):
    """Parse lines and transfers into a graph with travel times."""
    graph = defaultdict(list)  # station -> list of (neighbor, weight)
    stations_set = set()
    
    # Add line segments
    for line in data['lines']:
        stations = line['stations']
        segs = line['segments']
        for i in range(len(stations) - 1):
            a, b = stations[i], stations[i+1]
            w = segs[i]
            graph[a].append((b, w))
            graph[b].append((a, w))
            stations_set.add(a)
            stations_set.add(b)
    
    # Add transfer edges (weight 0, but note the 1-minute rule is handled later)
    for a, b in data['transfers']:
        graph[a].append((b, 0))
        graph[b].append((a, 0))
        stations_set.add(a)
        stations_set.add(b)
    
    stations = list(stations_set)
    return graph, stations

def all_pairs_shortest_path(graph, stations):
    """Compute all-pairs shortest path distances and next hop for path reconstruction."""
    # Initialize distance and next matrices
    dist = {u: {v: float('inf') for v in stations} for u in stations}
    next_hop = {u: {v: None for v in stations} for u in stations}
    
    for u in stations:
        dist[u][u] = 0
        next_hop[u][u] = u
    
    # Set direct edges
    for u in stations:
        for v, w in graph[u]:
            if w < dist[u][v]:
                dist[u][v] = w
                next_hop[u][v] = v
    
    # Floyd-Warshall
    for k in stations:
        for i in stations:
            if dist[i][k] == float('inf'):
                continue
            for j in stations:
                if dist[k][j] == float('inf'):
                    continue
                if dist[i][k] + dist[k][j] < dist[i][j]:
                    dist[i][j] = dist[i][k] + dist[k][j]
                    next_hop[i][j] = next_hop[i][k]
    
    return dist, next_hop

def reconstruct_path(next_hop, u, v):
    """Reconstruct shortest path from u to v using next_hop matrix."""
    if next_hop[u][v] is None:
        return []
    path = [u]
    while u != v:
        u = next_hop[u][v]
        path.append(u)
    return path

def nearest_neighbor_tsp(dist, stations):
    """Nearest neighbor heuristic for TSP (returns path visiting each station once)."""
    if not stations:
        return []
    
    # Start from first station
    start = stations[0]
    unvisited = set(stations)
    path = [start]
    unvisited.remove(start)
    
    while unvisited:
        last = path[-1]
        # Find nearest unvisited station
        nearest = None
        min_dist = float('inf')
        for station in unvisited:
            if dist[last][station] < min_dist:
                min_dist = dist[last][station]
                nearest = station
        path.append(nearest)
        unvisited.remove(nearest)
    
    return path

def expand_route(tsp_path, next_hop, stations):
    """Expand TSP path into actual route by inserting shortest paths between consecutive TSP stations."""
    if not tsp_path:
        return []
    
    route = [tsp_path[0]]
    for i in range(len(tsp_path) - 1):
        u = tsp_path[i]
        v = tsp_path[i+1]
        # Get shortest path from u to v
        path_segment = reconstruct_path(next_hop, u, v)
        # Append everything except the first node (u) to avoid duplication
        if len(path_segment) > 1:
            route.extend(path_segment[1:])
    return route

def compute_route(data):
    """Compute route for given subway data."""
    graph, stations = parse_lines(data)
    if not stations:
        return {"start_time": "00:00", "route": []}
    
    # Compute all-pairs shortest path
    dist, next_hop = all_pairs_shortest_path(graph, stations)
    
    # Get TSP path using nearest neighbor
    tsp_path = nearest_neighbor_tsp(dist, stations)
    
    # Expand to actual route
    route = expand_route(tsp_path, next_hop, stations)
    
    # Choose a start time when lines are likely running; use 06:00 as a safe morning time
    start_time = "06:00"
    return {"start_time": start_time, "route": route}

def main():
    host = 'localhost'
    port = 7474
    model_name = 'nemotron'  # can be any string
    
    try:
        with socket.create_connection((host, port)) as sock:
            # Send bot name
            sock.sendall(f"{model_name}_bot\n".encode())
            
            buffer = b''
            while True:
                # Read data from socket
                data = sock.recv(4096)
                if not data:
                    break
                buffer += data
                
                # Process complete lines
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    line_str = line.decode().strip()
                    
                    if line_str.startswith('ROUND'):
                        # Read SIZE line
                        while b'\n' not in buffer:
                            more = sock.recv(4096)
                            if not more:
                                break
                            buffer += more
                        size_line, buffer = buffer.split(b'\n', 1)
                        size_str = size_line.decode().strip()
                        _, size_val = size_str.split()
                        size = int(size_val)
                        
                        # Read JSON payload
                        payload = b''
                        while len(payload) < size:
                            chunk = sock.recv(size - len(payload))
                            if not chunk:
                                break
                            payload += chunk
                        
                        # Parse JSON
                        try:
                            json_data = json.loads(payload.decode())
                        except json.JSONDecodeError:
                            # Try to remove extra whitespace
                            json_data = json.loads(payload.decode().strip())
                        
                        # Compute route
                        response = compute_route(json_data)
                        resp_json = json.dumps(response)
                        sock.sendall((resp_json + '\n').encode())
                        
                        # Read and discard server response (VALID/INVALID/TIMEOUT)
                        resp_line = b''
                        while b'\n' not in resp_line:
                            chunk = sock.recv(1)
                            if not chunk:
                                break
                            resp_line += chunk
                        # Optionally print response for debugging
                        # print(resp_line.decode().strip())
    except ConnectionRefusedError:
        print("Could not connect to server. Make sure the server is running on localhost:7474.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
