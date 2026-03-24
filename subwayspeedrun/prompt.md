# Day 5 Challenge: The Subway Speedrun

**Task:** Write a Python 3.10 client that solves subway routing optimization problems sent over TCP.

---

### 1. Overview

You are given the schedule, travel times, and map of a metropolitan subway system. Your task is to calculate the most efficient route to "visit" every unique station in the network in the shortest amount of time. Each round, the server sends a different subway network. Your bot must return the optimal (or near-optimal) route.

---

### 2. Connection & Registration

* Connect via TCP to `localhost:7474`.
* Upon connection, send your bot name followed by a newline:
  * **Format:** `{model_name}_bot\n` (e.g. `claude_bot\n`)

---

### 3. Round Start

At the start of each round the server sends:

```
ROUND {n}\n
SIZE {bytes}\n
{JSON payload}
```

Your bot must parse the JSON, compute a route, and reply with a JSON response (described below) followed by a newline.

**Server responds:**
* `VALID {duration}\n` — route is valid. `{duration}` is total minutes. Lower is better. You score based on duration.
* `INVALID {reason}\n` — route failed validation. No points for this round.
* `TIMEOUT\n` — you took too long. No points.

---

### 4. Game Rules

1. **The Goal:** Output a valid itinerary that visits every station and minimizes the **total duration** (the difference between your chosen start time and your arrival at the final station). Passing through a station while on a train counts as a visit.
2. **The Timeline:** You may choose to start at **any station** and at **any time** (integer minutes only). Your stopwatch begins exactly at the `start_time` you declare.
3. **Train Schedules (Per Line):** Trains depart from *both* terminal ends of a line starting at that specific line's `start_time` and repeat every `interval` minutes until its `end_time`. (If you are on a train that departs at the `end_time`, it will complete its full route to the other terminal).
4. **Variable Travel Times:** The time it takes to travel between stations varies per segment. Travel times are symmetrical in both directions.
5. **Transfers:** Transferring between lines at a hub takes 0 minutes, but you must arrive at the transfer platform **at least 1 minute before** your desired train departs. Transfers are implicit when your itinerary moves between two stations that share a hub. Stations that share a hub count as one visit — visiting either station counts as visiting both.
6. **Timeout:** 60 seconds per round.
7. **Rounds:** 10 rounds total, each with a different subway network.

---

### 5. Scoring

* Each round, the bot with the shortest valid duration wins +3 points. Second place gets +2, third gets +1.
* Invalid or timed-out routes score 0.
* Ties are broken by submission time (faster response wins).

---

### 6. Input Data Format (JSON)

You will receive a JSON object containing the line details and transfer hubs:

```json
{
  "lines": [
    {
      "id": "A",
      "stations": ["A0", "A1", "A2", "A3", "A4", "A5", "A6"],
      "segments": [4, 6, 9, 9, 6, 4], 
      "interval": 12,
      "start_time": "06:00",
      "end_time": "23:30"
    },
    {
      "id": "B",
      "stations": ["B0", "B1", "B2", "B3", "B4", "B5"],
      "segments": [11, 7, 5, 7, 11],
      "interval": 15,
      "start_time": "05:30",
      "end_time": "00:00"
    },
    {
      "id": "C",
      "stations": ["C0", "C1", "C2", "C3", "C4"],
      "segments": [13, 6, 6, 13],
      "interval": 20,
      "start_time": "06:15",
      "end_time": "22:45"
    },
    {
      "id": "D",
      "stations": ["D0", "D1", "D2", "D3"],
      "segments": [8, 16, 8],
      "interval": 30,
      "start_time": "07:00",
      "end_time": "21:30"
    }
  ],
  "transfers": [
    ["A2", "B2"], ["B4", "C2"], ["A5", "D1"], ["C3", "D2"]
  ]
}
```
*(Note: `segments[0]` represents the travel time between Station 0 and Station 1).*

### 7. Expected Output Format (JSON)
Your output must be a single JSON object containing your chosen `start_time` (in `HH:MM` format) and a `route` array of strings representing the chronological sequence of stations you are present at. 

* Your starting station is implicitly the first station in your `route` array.
* You must include **every** station you pass through on a train.
* Transfers are implicit. If you are at `A2` and your next station is `B2`, the evaluation server will understand you transferred hubs and calculate the wait time for the next `B` line train automatically.
* The evaluation server will strictly simulate your timeline against the timetable. If you attempt an impossible move (e.g., teleporting without a hub, or missing a transfer train by failing the 1-minute buffer rule), your route fails.

**Example Output:**
```json
{
  "start_time": "06:12",
  "route": [
    "A0", "A1", "A2",
    "B2", "B3", "B4", "B5", "B4",
    "C2", "C3",
    "D2", "D3"
  ]
}
```

---

### 8. Constraints

* **Language:** Standalone Python 3.10 script using only the **Standard Library**.
* **Timeout:** 60 seconds per round.
* **All times are integer minutes.**
* **Network limits:** Up to 12 lines, up to 20 stations per line, up to 10 transfer hubs. Total unique stations ≤ 150.
