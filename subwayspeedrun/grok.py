import socket
import json
from collections import defaultdict

def time_to_minutes(t_str):
    h, m = map(int, t_str.split(':'))
    return h * 60 + m

HOST = 'localhost'
PORT = 7474
BOT_NAME = "grok_bot\n"

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((HOST, PORT))
sock.sendall(BOT_NAME.encode('utf-8'))

file = sock.makefile('r', encoding='utf-8')

round_count = 0
while round_count < 20:
    line = file.readline().strip()
    if not line:
        break
    if line.startswith('ROUND'):
        round_num = int(line.split()[1])
        size_line = file.readline().strip()
        size = int(size_line.split()[1])
        json_str = file.read(size)
        data = json.loads(json_str)
        
        # Build graph and station info
        station_to_line = {}
        graph = defaultdict(list)
        all_stations = set()
        for line_dict in data.get("lines", []):
            lid = line_dict["id"]
            stns = line_dict["stations"]
            for st in stns:
                station_to_line[st] = lid
                all_stations.add(st)
            for i in range(len(stns)-1):
                a, b = stns[i], stns[i+1]
                if b not in graph[a]:
                    graph[a].append(b)
                if a not in graph[b]:
                    graph[b].append(a)
        
        for tr in data.get("transfers", []):
            a, b = tr
            if b not in graph[a]:
                graph[a].append(b)
            if a not in graph[b]:
                graph[b].append(a)
        
        # DFS for covering path (prefers same-line neighbors)
        def dfs(curr, visited, path):
            path.append(curr)
            visited.add(curr)
            neighs = sorted(graph[curr], 
                          key=lambda n: 0 if station_to_line.get(n, '') == station_to_line.get(curr, '') else 1)
            for neigh in neighs:
                if neigh not in visited:
                    dfs(neigh, visited, path)
                    path.append(curr)
        
        # Try multiple starts for shortest path
        best_path = None
        min_len = float('inf')
        station_list = sorted(all_stations)
        num_tries = min(10, len(station_list))
        for i in range(num_tries):
            start = station_list[i]
            visited = set()
            path = []
            dfs(start, visited, path)
            if len(visited) == len(all_stations) and len(path) < min_len:
                min_len = len(path)
                best_path = path[:]
        
        if best_path is None:
            start = station_list[0]
            visited = set()
            path = []
            dfs(start, visited, path)
            best_path = path
        
        # Start time: earliest line start (safe for all schedules)
        min_minutes = min((time_to_minutes(l["start_time"]) for l in data.get("lines", [])), default=360)
        sh = min_minutes // 60
        sm = min_minutes % 60
        start_time = f"{sh:02d}:{sm:02d}"
        
        response = {
            "start_time": start_time,
            "route": best_path
        }
        resp_str = json.dumps(response) + "\n"
        sock.sendall(resp_str.encode('utf-8'))
        
        server_resp = file.readline().strip()
        print(f"Round {round_num}: {server_resp}")
        round_count += 1

sock.close()