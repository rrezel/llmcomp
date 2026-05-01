#!/usr/bin/env python3
import os
import socket
import sys

# bot author: gpt-4o

# Precomputed neighbors for each vertex (r,i) -> list of (nr,ni)
def build_neighbors():
    neigh = [[] for _ in range(24)]  # 4*6
    for r in range(4):
        for i in range(6):
            idx = r * 6 + i
            # same-ring neighbors
            neigh[idx].append(((r, (i + 1) % 6)))
            neigh[idx].append(((r, (i - 1) % 6)))
            # radial spokes
            if r > 0:
                neigh[idx].append(((r - 1, i)))
            if r < 3:
                neigh[idx].append(((r + 1, i)))
    return neigh

NEIGHBORS = build_neighbors()


def parse_coords(s: str):
    """'r,i' -> (r,i)"""
    r, i = s.split(',')
    return int(r), int(i)


def format_coords(r: int, i: int) -> str:
    return f"{r},{i}"


def apply_move(board, move_line: str):
    """Update board in-place with a legal move line (starting with 'MOVE')."""
    assert move_line.startswith('MOVE ')
    rest = move_line[5:]  # after 'MOVE '
    parts = rest.split(' -> ')
    coords = [parse_coords(p) for p in parts]
    # The piece moving is whatever is at the start coordinate
    player = board[coords[0][0] * 6 + coords[0][1]]
    enemy = 'B' if player == 'A' else 'A'
    for idx in range(len(coords) - 1):
        sr, si = coords[idx]
        dr, di = coords[idx + 1]
        # Determine if this segment is a jump
        rd = dr - sr
        cd = (di - si) % 6
        jumped = None
        if rd == 0 and cd in (2, 4):          # same-ring jump
            ji = si + (1 if cd == 2 else -1)
            ji %= 6
            jumped = (sr, ji)
        elif cd == 0 and abs(rd) == 2:        # radial jump
            jr = sr + (1 if rd > 0 else -1)
            jumped = (jr, si)
        # Remove jumper from source
        board[sr * 6 + si] = '.'
        # Remove jumped piece if any
        if jumped is not None:
            jr, ji = jumped
            board[jr * 6 + ji] = '.'
        # Place jumper at destination
        board[dr * 6 + di] = player


def find_capture_chains(board, player):
    """Return list of chains (list of (r,i)) each representing a maximal capture sequence."""
    enemy = 'B' if player == 'A' else 'A'
    all_chains = []

    # Depth-first search from a given position
    def dfs(pos, path, b):
        r, i = pos
        made = False
        jumps = []
        # same-ring cw
        ti = (i + 2) % 6
        ji = (i + 1) % 6
        if b[r * 6 + ji] == enemy and b[r * 6 + ti] == '.':
            jumps.append(((r, ti), (r, ji)))
        # same-ring ccw
        ti = (i - 2) % 6
        ji = (i - 1) % 6
        if b[r * 6 + ji] == enemy and b[r * 6 + ti] == '.':
            jumps.append(((r, ti), (r, ji)))
        # radial outward
        if r <= 1:
            tr = r + 2
            jr = r + 1
            if b[tr * 6 + i] == enemy and b[jr * 6 + i] == '.':
                jumps.append(((tr, i), (jr, i)))
        # radial inward
        if r >= 2:
            tr = r - 2
            jr = r - 1
            if b[tr * 6 + i] == enemy and b[jr * 6 + i] == '.':
                jumps.append(((tr, i), (jr, i)))

        for (dst, jumped) in jumps:
            made = True
            nb = b.copy()
            nb[pos[0] * 6 + pos[1]] = '.'          # jumper leaves source
            nb[jumped[0] * 6 + jumped[1]] = '.'    # remove jumped enemy
            nb[dst[0] * 6 + dst[1]] = player       # jumper lands
            dfs(dst, path + [dst], nb)

        if not made:
            if len(path) >= 2:   # at least one jump performed
                all_chains.append(path)

    for idx, cell in enumerate(board):
        if cell == player:
            r = idx // 6
            i = idx % 6
            dfs((r, i), [(r, i)], board.copy())
    return all_chains


def generate_move(board, player):
    """Return a legal move line for the given player."""
    enemy = 'B' if player == 'A' else 'A'
    chains = find_capture_chains(board, player)
    if chains:
        # Choose chain with most captures (longest)
        best = max(chains, key=lambda c: len(c) - 1)
        move_parts = [format_coords(r, i) for (r, i) in best]
        return "MOVE " + " -> ".join(move_parts)

    # No capture available: make a slide
    best_score = -1
    best_move = None  # (src_r, src_i, dst_r, dst_i)
    for idx, cell in enumerate(board):
        if cell == player:
            r = idx // 6
            i = idx % 6
            for (nr, ni) in NEIGHBORS[r * 6 + i]:
                if board[nr * 6 + ni] == '.':
                    # Prefer moving inward (smaller r)
                    score = -nr  # larger score for smaller r
                    if score > best_score:
                        best_score = score
                        best_move = (r, i, nr, ni)
    if best_move is None:
        # Should not happen if there is any legal move; fallback to any slide
        for idx, cell in enumerate(board):
            if cell == player:
                r = idx // 6
                i = idx % 6
                for (nr, ni) in NEIGHBORS[r * 6 + i]:
                    if board[nr * 6 + ni] == '.':
                        return f"MOVE {r},{i} -> {nr},{ni}"
        # As absolute last resort, resign (send illegal move to lose)
        return "MOVE 0,0 -> 0,0"
    sr, si, dr, di = best_move
    return f"MOVE {sr},{si} -> {dr},{di}"


def main():
    botname = os.environ.get('BOTNAME')
    if botname is None:
        sys.exit(1)
    try:
        sock = socket.create_connection(('localhost', 7474))
    except Exception as e:
        sys.exit(1)

    # Send bot name
    sock.sendall((botname + '\n').encode())
    file = sock.makefile('r', newline='\n')

    my_color = None
    board = ['.'] * 24

    try:
        while True:
            line = file.readline()
            if not line:
                break
            line = line.rstrip('\n')
            if line.startswith('MATCH'):
                # MATCH <m> <opponent>
                _, _, opp = line.split()
                # opponent name not needed for logic
                my_color = None
            elif line.startswith('GAME'):
                # GAME <g> <your_color>
                _, _, color = line.split()
                my_color = color
            elif line.startswith('BOARD'):
                # BOARD <24 tokens>
                parts = line.split()
                if len(parts) >= 25:
                    board = parts[1:25]
            elif line == 'TURN':
                if my_color is None:
                    continue
                mv = generate_move(board, my_color)
                sock.sendall((mv + '\n').encode())
            elif line.startswith('OPP'):
                # OPP MOVE ...
                _, mv = line.split(' ', 1)
                apply_move(board, mv)
            elif line.startswith('GAME_END'):
                # Ignore; next GAME or MATCH_END will follow
                pass
            elif line.startswith('MATCH_END'):
                pass
            elif line.startswith('TOURNAMENT_END'):
                break
            else:
                # Unexpected line; ignore
                pass
    finally:
        sock.close()


if __name__ == '__main__':
    main()
