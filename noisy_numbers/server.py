"""
Noisy Soviet Postal Code Tournament Server.

Generates 6-digit postal codes as noisy PPM images, sends them to connected bots,
scores their responses, and logs results.
"""
import socket
import threading
import time
import random
import os

from generate_example import (
    generate_code_image, write_ppm, DOT_GRID, DIGIT_STROKES,
    CELL_W, CELL_H, CELL_PAD, BORDER
)

# Configuration
HOST = 'localhost'
PORT = 7474
MAX_ROUNDS = 100
REGISTRATION_WINDOW = 10.0
ROUND_TIMEOUT = 10.0
LOG_PATH = 'results.log'


def generate_ppm_string(pixels, w, h):
    """Generate PPM P3 as a string."""
    lines = [f"P3\n{w} {h}\n255"]
    for row_start in range(0, len(pixels), w):
        row = pixels[row_start:row_start + w]
        lines.append(" ".join(f"{px[0]} {px[1]} {px[2]}" for px in row))
    return "\n".join(lines) + "\n"


class Client:
    def __init__(self, sock, name):
        self.sock = sock
        self.name = name
        self.score = 0
        self.alive = True
        self.f = sock.makefile('r', encoding='utf-8')

    def send(self, data):
        try:
            self.sock.sendall(data.encode('utf-8'))
        except OSError:
            self.alive = False

    def readline(self, timeout=None):
        if timeout:
            self.sock.settimeout(timeout)
        try:
            line = self.f.readline()
            if not line:
                self.alive = False
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


IMG_DIR = 'images'

def run_tournament():
    os.makedirs(IMG_DIR, exist_ok=True)
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
        alive_clients = [c for c in clients if c.alive]
        if not alive_clients:
            break

        # Generate random 6-digit code
        code = ''.join(str(random.randint(0, 9)) for _ in range(6))

        # Progressive difficulty: noise fixed at 5%, scale and rotation ramp up
        progress = (round_num - 1) / (MAX_ROUNDS - 1)  # 0.0 to 1.0
        noise = 0.05                     # fixed 5%
        scale_range = progress * 0.10    # 0% -> ±10%
        rotation_range = progress * 10.0 # 0° -> ±10°

        pixels, w, h, scale, rot = generate_code_image(
            code, noise=noise, scale_range=scale_range, rotation_range=rotation_range
        )
        ppm_data = generate_ppm_string(pixels, w, h)
        ppm_bytes = len(ppm_data)

        # Save image to disk
        img_path = os.path.join(IMG_DIR, f"round_{round_num:03d}_{code}.ppm")
        with open(img_path, 'w') as img_f:
            img_f.write(ppm_data)

        print(f"--- ROUND {round_num}: {code} (noise={noise:.1%} scale=±{scale_range:.0%} rot=±{rotation_range:.0f}°, {w}x{h}) ---")
        log.write(f"--- ROUND {round_num}: {code} (noise={noise:.1%} scale=±{scale_range:.0%} rot=±{rotation_range:.0f}°) ---\n")

        round_start = time.monotonic()

        # Send to all alive clients
        for client in alive_clients:
            client.send(f"ROUND {round_num}\n")
            client.send(f"SIZE {ppm_bytes}\n")
            client.send(ppm_data)

        # Collect responses
        results = {}
        for client in alive_clients:
            answer = client.readline(timeout=ROUND_TIMEOUT)
            elapsed = (time.monotonic() - round_start) * 1000

            if answer is None:
                # Timeout or disconnect
                client.send("ELIMINATED\n")
                client.alive = False
                status = "ELIMINATED (timeout)"
                results[client.name] = (None, elapsed, status)
            elif len(answer) != 6 or not answer.isdigit():
                # Malformed
                client.send("ELIMINATED\n")
                client.alive = False
                status = f"ELIMINATED (malformed: '{answer}')"
                results[client.name] = (answer, elapsed, status)
            elif answer == code:
                client.score += 1
                client.send("CORRECT\n")
                status = f"CORRECT  +1 (total: {client.score})"
                results[client.name] = (answer, elapsed, status)
            else:
                client.send(f"WRONG {code}\n")
                status = f"WRONG (sent '{answer}', correct '{code}')"
                results[client.name] = (answer, elapsed, status)

        # Log results sorted by time
        for name, (answer, elapsed, status) in sorted(results.items(), key=lambda x: x[1][1]):
            line = f"  {name:<20} | time: {elapsed:>8.1f}ms | {status}"
            print(line)
            log.write(line + "\n")
        log.write("\n")
        log.flush()

        time.sleep(0.5)

    # Final standings
    header = "=" * 60 + "\nFINAL TOURNAMENT RESULTS\n" + "=" * 60
    print("\n" + header)
    log.write("\n" + header + "\n")

    all_clients = sorted(clients, key=lambda c: -c.score)
    for i, client in enumerate(all_clients):
        status = "active" if client.alive else "eliminated"
        line = f"  #{i+1}  {client.name:<20} {client.score:>3} points  {status}"
        print(line)
        log.write(line + "\n")

    log.close()
    server_sock.close()
    for c in clients:
        c.close()


if __name__ == "__main__":
    run_tournament()
