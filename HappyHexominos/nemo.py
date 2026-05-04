# bot author: Nemotron 3 Super (nvidia/nemotron-3-super-120b-a12b via OpenRouter)
# bot author: gpt-4o
import os
import sys
import socket

def main():
    bot_name = os.environ.get('BOTNAME', '')
    if not bot_name:
        # Misconfigured; do not connect
        return
    # Remove a single trailing newline if present (shouldn't be any)
    bot_name = bot_name.rstrip('\n')
    if not (1 <= len(bot_name) <= 32):
        # Invalid per spec; still try? We'll just not connect.
        return
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")
    if any(ch not in allowed for ch in bot_name):
        return

    try:
        sock = socket.create_connection(('localhost', 7474))
    except Exception:
        return

    # Send bot name
    try:
        sock.sendall((bot_name + '\n').encode())
    except Exception:
        sock.close()
        return

    file = sock.makefile('r')
    try:
        while True:
            line = file.readline()
            if not line:
                break
            if line.endswith('\n'):
                line = line[:-1]
            # Ignore any empty lines (shouldn't occur)
            if not line:
                continue
            if line.startswith('ROUND'):
                # ROUND <n> <w> <h>
                parts = line.split()
                if len(parts) != 3:
                    continue
                try:
                    w = int(parts[2])
                    h = int(parts[3])
                except ValueError:
                    continue
                # Compute tiling
                grid = [[-1] * w for _ in range(h)]
                piece_id = 0
                if w % 6 == 0:
                    # Horizontal 1x6 strips per row
                    for r in range(h):
                        for c in range(0, w, 6):
                            for dc in range(6):
                                grid[r][c + dc] = piece_id
                            piece_id += 1
                elif h % 6 == 0:
                    # Vertical 1x6 strips per column
                    for c in range(w):
                        for r in range(0, h, 6):
                            for dr in range(6):
                                grid[r + dr][c] = piece_id
                            piece_id += 1
                elif w % 2 == 0 and h % 3 == 0:
                    # Vertical 2x3 bricks (width 2, height 3)
                    for c0 in range(0, w, 2):
                        for r0 in range(0, h, 3):
                            for dr in range(3):
                                for dc in range(2):
                                    grid[r0 + dr][c0 + dc] = piece_id
                            piece_id += 1
                else:
                    # Must be h%2==0 and w%3==0: horizontal 3x2 bricks (width 3, height 2)
                    for r0 in range(0, h, 2):
                        for c0 in range(0, w, 3):
                            for dr in range(2):
                                for dc in range(3):
                                    grid[r0 + dr][c0 + dc] = piece_id
                            piece_id += 1
                # Send submission
                for r in range(h):
                    row_str = ''.join(f'[{grid[r][c]}]' for c in range(w))
                    try:
                        sock.sendall((row_str + '\n').encode())
                    except Exception:
                        return
                try:
                    sock.sendall(('END\n').encode())
                except Exception:
                    return
                # Read server response: OK/INVALID line
                resp = file.readline()
                if not resp:
                    break
                # Read END_ROUND line
                end_round = file.readline()
                if not end_round:
                    break
            elif line.startswith('TOURNAMENT_END'):
                break
            # Other lines ignored per spec
    finally:
        sock.close()

if __name__ == '__main__':
    main()
