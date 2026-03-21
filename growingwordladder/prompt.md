# Tournament Specification: The Growing Word Ladder (Multi-Round Sprint)

**Task:** Write a Python 3.10 client for a high-speed, competitive "Growing Word Ladder" tournament.

### 1. Network Protocol
* **Connection:** Connect via TCP to `localhost:7474`.
* **Identification:** Upon connection, send your bot name followed by a newline (`\n`). The name of the bot is the "{name of your model}_bot", e.g, claude_bot.
* **Challenge Reception:** The server sends a single line containing a **Start Word** and a **Goal Word**, separated by a comma (e.g., `RED,GREEN\n`).
* **Sequence Submission:** Once a path is found, the client must transmit the **entire ladder sequence** as a single block of data. Each word in the sequence must be a UTF-8 string followed by a newline (`\n`).
    * **Sequence Content:** The submission must include the **Start Word**, all intermediate steps, and the **Goal Word**.
* **Server Response:** After the sequence is transmitted, the server evaluates the ladder and replies:
    * `0\n`: **Sequence Accepted.** Your path is valid and you have successfully completed the round.
    * `1\n`: **Disqualified / Game Over.** This is sent if your sequence is invalid, a word is not in the dictionary, or—critically—if you failed to submit a valid path within **5 seconds** of the round winner.
* **Multi-Round Loop:** The tournament is persistent. Immediately after all "still standing" clients (those who received a `0\n`) have responded, the server will broadcast the next `START,GOAL` challenge.

### 2. Game Rules
* **Transformation Mechanics:** Each consecutive word in the sequence must be achievable from the previous word by:
    1.  **Changing** exactly 1 letter (e.g., `COT` $\rightarrow$ `HOT`).
    2.  **Adding** exactly 1 letter (e.g., `RED` $\rightarrow$ `REED`).
    3.  **Removing** exactly 1 letter (e.g., `COLD` $\rightarrow$ `COD`).
* **Vocabulary:** All words must exist in the provided `dictionary.txt` (1,000,000 uppercase words). 
* **The Race (The 5-Second Rule):** This is a real-time competition. While the first bot to submit a valid sequence wins the round's top points, all other bots must submit their valid sequence within **5 seconds of the winner** to remain in the tournament. Failing this results in an immediate `1\n` and disconnection.


### 3. Deliverable & Constraints
* **Language:** Standalone Python 3.10 script using only the **Standard Library**.
* **Graceful Exit:** The client must terminate immediately upon receiving a `1\n` or if the server closes the connection.

