# bot author: Grok Expert 4.20
import os
import socket
import sys

# bot author: Grok (xAI) + Lucas/Harper/Benjamin collab — optimal trie+DP strategy

class TrieNode:
    def __init__(self):
        self.children = [None] * 2
        self.words = []

def main():
    botname = os.environ.get('BOTNAME')
    if not botname:
        print("BOTNAME environment variable is required", file=sys.stderr)
        sys.exit(1)
    botname = botname.strip()
    
    # Letter to bits
    char_to_bits = {chr(ord('a') + i): format(i, 'b') for i in range(26)}
    
    # Build trie with words len >=4
    root = TrieNode()
    try:
        with open('dictionary.txt', encoding='utf-8') as f:
            for raw_line in f:
                word_lower = raw_line.strip().lower()
                if len(word_lower) < 4 or not word_lower.isalpha():
                    continue
                word_upper = word_lower.upper()
                enc = ''.join(char_to_bits.get(c, '') for c in word_lower)
                if not enc:
                    continue
                node = root
                for ch in enc:
                    b = int(ch)
                    if node.children[b] is None:
                        node.children[b] = TrieNode()
                    node = node.children[b]
                if word_upper not in node.words:
                    node.words.append(word_upper)
    except Exception as e:
        print(f"Failed to load dictionary: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Connect
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    
    def send_line(msg):
        sock.sendall((msg + '\n').encode('ascii'))
    
    send_line(botname)
    
    # Use makefile for reading lines
    sock_file = sock.makefile('r')
    
    while True:
        line = sock_file.readline()
        if not line:
            break
        line = line.rstrip('\n')
        
        if line.startswith('ROUND '):
            # Parse ROUND <n> <bits>
            parts = line.split(' ', 2)
            round_n = int(parts[1])
            bitstream = parts[2]
            L = len(bitstream)
            
            # Collect matches by end position
            ends_at = [[] for _ in range(L + 1)]
            
            for start in range(L):
                node = root
                pos = start
                while pos < L:
                    b = int(bitstream[pos])
                    if node.children[b] is None:
                        break
                    node = node.children[b]
                    pos += 1
                    # Check for words ending here
                    for w in node.words:
                        e = pos
                        contrib = len(w) - 3
                        ends_at[e].append((start, contrib, w))
            
            # DP for max score non-overlapping
            dp = [0] * (L + 1)
            prev_pos = [-1] * (L + 1)
            used = [None] * (L + 1)
            
            for j in range(1, L + 1):
                # default skip
                dp[j] = dp[j - 1]
                prev_pos[j] = j - 1
                used[j] = None
                
                # check matches ending at j
                for s, contrib, w in ends_at[j]:
                    if s <= j:
                        candidate = dp[s] + contrib
                        if candidate > dp[j]:
                            dp[j] = candidate
                            prev_pos[j] = s
                            used[j] = (w, s)
            
            # Reconstruct selection
            selected = []
            current = L
            while current > 0:
                if used[current] is not None:
                    w, offset = used[current]
                    selected.append((w, offset))
                    current = prev_pos[current]
                else:
                    current = prev_pos[current]
            selected.reverse()
            
            # Submit
            for w, offset in selected:
                send_line(f"WORD {w} {offset}")
            send_line("END")
        
        elif line == 'TOURNAMENT_END':
            break
        # ignore other lines like OK, INVALID, END_ROUND
    
    sock_file.close()
    sock.close()

if __name__ == "__main__":
    main()