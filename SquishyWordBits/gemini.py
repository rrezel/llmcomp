# bot author: Gemini Pro 3.1
import os
import sys
import socket

# We implement an extremely memory-efficient and fast parallel-array Trie.
# This prevents out-of-memory errors on large dictionaries and ensures 
# blazingly fast bitstream parsing to win time-based tie-breakers.
trie_0 = [0]
trie_1 = [0]
trie_word = [None]

def build_trie():
    """
    Parses the dictionary, converts valid words to their bit representations, 
    and inserts them into the Trie. We exclusively store words of length >= 4 
    because 1, 2, and 3 letter words contribute negative or zero points and 
    only consume valuable bitstream real-estate/time.
    """
    with open("dictionary.txt", "r", encoding="ascii") as f:
        for line in f:
            word = line.strip()
            # Must be purely lowercase alphabetic. 
            # Skip short words that score <= 0.
            if len(word) < 4 or not word.isalpha() or not word.islower():
                continue
                
            # Compute bit representation using the minimum number of bits
            # (No leading zeros, except 'a' = '0')
            bits = "".join(bin(ord(c) - ord('a'))[2:] if c != 'a' else '0' for c in word)
            
            node = 0
            for b in bits:
                if b == '0':
                    if trie_0[node] == 0:
                        trie_0.append(0)
                        trie_1.append(0)
                        trie_word.append(None)
                        trie_0[node] = len(trie_0) - 1
                    node = trie_0[node]
                else:
                    if trie_1[node] == 0:
                        trie_0.append(0)
                        trie_1.append(0)
                        trie_word.append(None)
                        trie_1[node] = len(trie_1) - 1
                    node = trie_1[node]
            
            # If multiple words encode to the exact same bit string, 
            # we keep the one that gives the maximum score (longest length).
            if trie_word[node] is None or len(word) > len(trie_word[node]):
                trie_word[node] = word

def solve_and_submit(sock, bits):
    """
    Finds all valid dictionary words embedded in the bitstream, computes
    the optimal non-overlapping sequence via Dynamic Programming, and 
    transmits the solution.
    """
    N = len(bits)
    # intervals[i] will store a list of (start_index, score, word) 
    # for valid words ending exactly at bit index `i` (exclusive bound).
    intervals = [[] for _ in range(N + 1)]
    
    for start in range(N):
        node = 0
        for end in range(start, N):
            if bits[end] == '0':
                node = trie_0[node]
            else:
                node = trie_1[node]
            
            if node == 0:  # Invalid prefix path, break early
                break
            
            w = trie_word[node]
            if w is not None:
                score = len(w) - 3
                intervals[end + 1].append((start, score, w))
                
    # dp[i] represents the maximum score achievable using the first i bits
    dp = [0] * (N + 1)
    
    # choice[i] stores the backpointer to reconstruct the optimal sequence.
    # It stores tuples: (previous_optimal_index, word_chosen_or_None)
    choice = [(0, None)] * (N + 1)
    
    for i in range(1, N + 1):
        # Base case: We can always just inherit the optimal score from i-1 
        # (meaning bit i-1 is left unused).
        dp[i] = dp[i-1]
        choice[i] = (i-1, None)
        
        # Consider all words that end exactly at this position `i`.
        for start, score, w in intervals[i]:
            if dp[start] + score > dp[i]:
                dp[i] = dp[start] + score
                choice[i] = (start, w)
                
    # Reconstruct the sequence by tracing back from N to 0
    curr = N
    results = []
    while curr > 0:
        prev, w = choice[curr]
        if w is not None:
            # prev represents the index where the word began (offset)
            results.append((w, prev))
        curr = prev
        
    # Build wire output. 
    # Order of submitted words does not matter based on specs.
    out_lines = []
    for w, offset in results:
        out_lines.append(f"WORD {w.upper()} {offset}\n")
    out_lines.append("END\n")
    
    # Flush entire submission payload immediately
    sock.sendall("".join(out_lines).encode('ascii'))

def main():
    # 1. Verification of identity configuration
    bot_name = os.environ.get('BOTNAME', '').strip('\n')
    if not bot_name:
        sys.exit(1)
        
    # 2. Precompute dictionary search space once before any rounds begin
    build_trie()
    
    # 3. Connection and handshake
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock_file = sock.makefile('r', encoding='ascii')
    
    sock.sendall((bot_name + '\n').encode('ascii'))
    
    # 4. Await and act upon rounds serially
    for line in sock_file:
        line = line.strip('\n')
        if line.startswith("ROUND"):
            parts = line.split(" ")
            if len(parts) >= 3:
                bits = parts[2]
                solve_and_submit(sock, bits)
        elif line == "TOURNAMENT_END":
            break

if __name__ == "__main__":
    main()