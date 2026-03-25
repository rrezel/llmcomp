# Tournament Specification: Noisy Soviet Postal Code Reader

**Task:** Write a Python 3.10 client that reads noisy Soviet-style numerical postal codes from PPM images sent over TCP.

---

### 1. Overview

Each round, the server sends an ASCII P3 PPM image containing a six-digit Soviet postal code. The digits are drawn by connecting dots on a 52-dot grid with straight lines. Your bot must decode the image and reply with the six digits.

---

### 2. Connection & Registration

* Connect via TCP to `localhost:7474`.
* Send your bot name followed by a newline: `{model_name}_bot\n`

---

### 3. Round Sequence

**Server sends:**
```
ROUND {n}\n
SIZE {bytes}\n
{ASCII PPM P3 data}
```

**You reply:**
```
{six digits}\n
```
For example: `482901\n`

**Server responds:**
* `CORRECT\n` — all six digits matched. You score +1 point.
* `WRONG {answer}\n` — your answer was wrong. `{answer}` is the correct six-digit code. No points, but you stay in the tournament.
* `ELIMINATED\n` — you sent malformed input or timed out.

---

### 4. Image Properties

* **Format:** ASCII PPM (P3), RGB, 8 bits per channel.
* **Content:** Six digits (0–9) arranged left-to-right, each in a rectangular cell on a 52-dot grid.
* **Noise:** 5% of all pixels are randomly flipped (black↔white).
* **Scale:** The image may be scaled ±10% from the base size.
* **Rotation:** The image may be rotated ±10 degrees. Background fill for rotation is white.
* **Colors:** Glyphs are black on white background (before noise).
* **Cell layout:** 6 cells with ~16px gaps between them. Each cell is approximately 60px wide × 100px tall before scaling.

---

### 5. The 52-Dot Grid

Each digit cell contains a grid of 52 dots. The dots are positioned at the following **normalized coordinates** (0.0 = left/top edge of cell, 1.0 = right/bottom edge):

```
Dot  1: (0.000, 0.000)    Dot  2: (0.197, 0.000)    Dot  3: (0.401, 0.000)
Dot  4: (0.602, 0.000)    Dot  5: (0.803, 0.000)    Dot  6: (0.995, 0.003)
Dot  7: (0.000, 0.091)    Dot  8: (0.858, 0.070)    Dot  9: (1.000, 0.091)
Dot 10: (0.725, 0.133)    Dot 11: (0.000, 0.182)    Dot 12: (0.593, 0.196)
Dot 13: (1.000, 0.182)    Dot 14: (0.459, 0.260)    Dot 15: (0.000, 0.273)
Dot 16: (1.000, 0.273)    Dot 17: (0.325, 0.324)    Dot 18: (0.000, 0.364)
Dot 19: (1.000, 0.364)    Dot 20: (0.194, 0.387)    Dot 21: (0.000, 0.454)
Dot 22: (0.062, 0.450)    Dot 23: (1.000, 0.454)    Dot 24: (0.017, 0.511)
Dot 25: (0.204, 0.512)    Dot 26: (0.394, 0.512)    Dot 27: (0.580, 0.511)
Dot 28: (0.768, 0.512)    Dot 29: (0.976, 0.517)    Dot 30: (0.000, 0.545)
Dot 31: (1.000, 0.545)    Dot 32: (0.858, 0.585)    Dot 33: (0.000, 0.636)
Dot 34: (0.725, 0.648)    Dot 35: (1.000, 0.636)    Dot 36: (0.000, 0.727)
Dot 37: (0.593, 0.711)    Dot 38: (1.000, 0.727)    Dot 39: (0.459, 0.775)
Dot 40: (0.000, 0.818)    Dot 41: (1.000, 0.818)    Dot 42: (0.325, 0.839)
Dot 43: (0.194, 0.902)    Dot 44: (0.000, 0.909)    Dot 45: (1.000, 0.909)
Dot 46: (0.062, 0.965)    Dot 47: (0.000, 1.000)    Dot 48: (0.197, 1.000)
Dot 49: (0.401, 1.000)    Dot 50: (0.602, 1.000)    Dot 51: (0.803, 1.000)
Dot 52: (1.000, 1.000)
```

The dots themselves are always present as small black marks in every cell. The digit strokes are thicker lines drawn between specific dots.

---

### 6. Digit Stroke Sequences

Each digit is drawn by connecting dots in sequence with straight lines. A dash-separated list means "draw a line from dot A to dot B to dot C..." Some digits have multiple separate strokes.

* **0:** `1-2-3-4-5-6-9-13-16-19-23-29-31-35-38-41-45-52-51-50-49-48-47-44-40-36-33-30-24-21-18-15-11-7-1`
* **1:** `24-22-20-17-14-12-10-8-6-9-13-16-19-23-29-31-35-38-41-45-52`
* **2:** `1-2-3-4-5-6-9-13-16-19-23-29-32-34-37-39-42-43-46-47-48-49-50-51-52`
* **3:** `1-2-3-4-5-6-8-10-12-14-17-20-22-24-25-26-27-28-29-32-34-37-39-42-43-46-47`
* **4:**
    * Stroke 1: `1-7-11-15-18-21-24-25-26-27-28-29`
    * Stroke 2: `6-9-13-16-19-23-29-31-35-38-41-45-52`
* **5:** `6-5-4-3-2-1-7-11-15-18-21-24-25-26-27-28-29-31-35-38-41-45-52-51-50-49-48-47`
* **6:**
    * Stroke 1: `6-8-10-12-14-17-20-22-24`
    * Stroke 2: `24-30-33-36-40-44-47-48-49-50-51-52-45-41-38-35-31-29-28-27-26-25-24`
* **7:** `1-2-3-4-5-6-8-10-12-14-17-20-22-24-30-33-36-40-44-47`
* **8:**
    * Stroke 1: `1-2-3-4-5-6-9-13-16-19-23-29-31-35-38-41-45-52-51-50-49-48-47-44-40-36-33-30-24-21-18-15-11-7-1`
    * Stroke 2: `24-25-26-27-28-29`
* **9:**
    * Stroke 1: `24-21-18-15-11-7-1-2-3-4-5-6-9-13-16-19-23-29-28-27-26-25-24`
    * Stroke 2: `29-32-34-37-39-42-43-46-47`

---

### 7. Scoring & Elimination

* +1 point per fully correct six-digit answer.
* Wrong answers score 0 but do not eliminate.
* Timeout (10 seconds per round) or malformed response → `ELIMINATED`.
* 100 rounds total. Difficulty increases progressively (noise is fixed at 5%, scale and rotation ramp up).

---

### 8. Provided Files

* **`reference_digits.png`** — Clean PNG showing all 10 digits (0–9) on the dot grid. *(For visual reference only.)*
* **`reference_grid.png`** — Clean PNG showing 6 empty dot-grid cells. *(For visual reference only.)*
* **`example.png`** — A sample noisy image containing the code `345678`. *(For visual reference only.)*

The actual images sent by the server during the tournament are **ASCII PPM (P3)** format over TCP.

---

### 9. Constraints

* **Language:** Standalone Python 3.10 script using only the **Standard Library**.
* **Timeout:** 10 seconds per round.
