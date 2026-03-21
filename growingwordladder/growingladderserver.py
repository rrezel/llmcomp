import socket
import threading
import time

# Configuration
HOST = 'localhost'
PORT = 7474
DICT_PATH = 'dictionary.txt'
CHALLENGE_PATH = 'challenges.txt'
LOG_PATH = 'results.log'
MIN_WORD_LEN = 2
ROUND_TIMEOUT = 5.0
MAX_ROUNDS = 100
REGISTRATION_WINDOW = 10.0


class LadderServer:
    def __init__(self):
        self.dictionary_set = set()
        self.challenges = []
        self.clients = []  # List of [socket, name, score]
        self.lock = threading.Lock()
        self.winner_found = threading.Event()
        self.round_winner_sock = None
        self.results = {}
        self.round_start_time = 0.0
        self.submission_times = {}
        self.submission_lengths = {}
        self.log_file = open(LOG_PATH, 'w', encoding='utf-8')

    def load_dictionary(self):
        print(f"Loading {DICT_PATH}...")
        try:
            with open(DICT_PATH, 'r', encoding='utf-8') as f:
                self.dictionary_set = set(
                    line.strip().upper() for line in f if len(line.strip()) >= MIN_WORD_LEN
                )
            print(f"Dictionary loaded: {len(self.dictionary_set)} words.")
        except FileNotFoundError:
            print("Error: dictionary.txt not found.")
            exit(1)

    def load_challenges(self):
        print(f"Loading {CHALLENGE_PATH}...")
        try:
            with open(CHALLENGE_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if ',' not in line:
                        continue
                    start, goal = line.split(',', 1)
                    self.challenges.append((start.strip().upper(), goal.strip().upper()))
            print(f"Loaded {len(self.challenges)} challenges.")
        except FileNotFoundError:
            print(f"Error: {CHALLENGE_PATH} not found.")
            exit(1)

    def validate_ladder(self, sequence, start_goal):
        start_target, goal_target = start_goal
        if not sequence or sequence[0] != start_target or sequence[-1] != goal_target:
            return False
        for i in range(len(sequence) - 1):
            w1, w2 = sequence[i], sequence[i + 1]
            if w2 not in self.dictionary_set:
                return False
            l1, l2 = len(w1), len(w2)
            valid = False
            if l1 == l2:
                valid = sum(1 for a, b in zip(w1, w2) if a != b) == 1
            elif l2 == l1 + 1:
                valid = any(w1 == w2[:j] + w2[j + 1:] for j in range(l2))
            elif l2 == l1 - 1:
                valid = any(w2 == w1[:j] + w1[j + 1:] for j in range(l1))
            if not valid:
                return False
        return True

    def handle_client_round(self, client_sock, start_goal):
        try:
            sequence = []
            buffer = b""
            while True:
                chunk = client_sock.recv(65536)
                if not chunk:
                    return
                buffer += chunk
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    word = line.decode('utf-8').strip().upper()
                    sequence.append(word)
                    if word == start_goal[1]:
                        finish_time = time.monotonic()
                        success = self.validate_ladder(sequence, start_goal)
                        with self.lock:
                            self.submission_times[client_sock] = finish_time - self.round_start_time
                            self.submission_lengths[client_sock] = len(sequence)
                            if success:
                                if not self.winner_found.is_set():
                                    self.winner_found.set()
                                    self.round_winner_sock = client_sock
                                self.results[client_sock] = True
                            else:
                                self.results[client_sock] = False
                        return
        except Exception:
            with self.lock:
                self.results[client_sock] = False

    def run_tournament(self):
        self.load_dictionary()
        self.load_challenges()

        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((HOST, PORT))
        server_sock.listen(10)
        server_sock.settimeout(1.0)

        print(f"Server open for registration ({REGISTRATION_WINDOW}s)...")
        start_reg = time.time()
        while time.time() - start_reg < REGISTRATION_WINDOW:
            try:
                conn, addr = server_sock.accept()
                conn.settimeout(None)
                name = conn.recv(1024).decode('utf-8').strip()
                print(f"Bot '{name}' joined.")
                self.clients.append([conn, name, 0])
            except socket.timeout:
                continue

        if not self.clients:
            print("No participants.")
            return

        num_rounds = min(MAX_ROUNDS, len(self.challenges))

        for round_num in range(1, num_rounds + 1):
            start_word, goal_word = self.challenges[round_num - 1]
            challenge = f"{start_word},{goal_word}\n"

            print(f"\n--- ROUND {round_num}: {start_word} -> {goal_word} ---")
            self.winner_found.clear()
            self.round_winner_sock = None
            self.results = {c[0]: None for c in self.clients}
            self.submission_times = {}
            self.submission_lengths = {}

            self.round_start_time = time.monotonic()
            for conn, name, score in self.clients:
                try:
                    conn.sendall(challenge.encode('utf-8'))
                    threading.Thread(
                        target=self.handle_client_round,
                        args=(conn, (start_word, goal_word)),
                        daemon=True
                    ).start()
                except Exception:
                    pass

            if self.winner_found.wait(timeout=60):
                time.sleep(ROUND_TIMEOUT)

            still_standing = []
            round_log_lines = []
            with self.lock:
                for client in self.clients:
                    conn, name, score = client
                    if self.results.get(conn) is True:
                        points = 1 if conn == self.round_winner_sock else 0
                        client[2] += points
                        conn.sendall(b"0\n")
                        still_standing.append(client)

                        status = "WINNER (+1)" if points else "SURVIVED (+0)"
                        elapsed = self.submission_times.get(conn, -1)
                        path_len = self.submission_lengths.get(conn, 0)
                        print(f"{name}: {status} | Total Score: {client[2]}")
                        round_log_lines.append(
                            f"  {name:<20} {status:<14} | time: {elapsed * 1000:>8.1f}ms | path: {path_len:>3} steps | total: {client[2]}")
                    else:
                        try:
                            conn.sendall(b"1\n")
                            conn.close()
                        except Exception:
                            pass
                        elapsed = self.submission_times.get(conn, -1)
                        path_len = self.submission_lengths.get(conn, 0)
                        print(f"{name}: ELIMINATED")
                        if elapsed >= 0:
                            round_log_lines.append(
                                f"  {name:<20} ELIMINATED     | time: {elapsed * 1000:>8.1f}ms | path: {path_len:>3} steps (invalid)")
                        else:
                            round_log_lines.append(
                                f"  {name:<20} ELIMINATED     | no submission")

            self.log_file.write(f"--- ROUND {round_num}: {start_word} -> {goal_word} ---\n")
            round_log_lines.sort()
            for line in round_log_lines:
                self.log_file.write(line + "\n")
            self.log_file.write("\n")
            self.log_file.flush()

            self.clients = still_standing
            if not self.clients:
                break
            time.sleep(1)

        final_header = "=" * 60 + "\nFINAL TOURNAMENT RESULTS\n" + "=" * 60
        print("\n" + final_header)
        self.log_file.write("\n" + final_header + "\n")
        self.clients.sort(key=lambda x: x[2], reverse=True)
        for i, (_, name, score) in enumerate(self.clients):
            line = f"{i + 1:2d}. {name:<20} : {score} Points"
            print(line)
            self.log_file.write(line + "\n")
        self.log_file.close()


if __name__ == "__main__":
    LadderServer().run_tournament()
