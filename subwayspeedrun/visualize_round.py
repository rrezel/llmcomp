#!/usr/bin/env python3
"""
Visualize a subway speedrun round as an animated PNG.

Usage: python visualize_round.py results.log 5
       (visualizes round 5 from results.log)
"""
import sys
import json
import math
import re
from PIL import Image, ImageDraw

# Colors per line
LINE_COLORS = [
    (220, 50, 50),    # A - red
    (50, 100, 220),   # B - blue
    (50, 180, 50),    # C - green
    (220, 160, 30),   # D - orange
    (160, 50, 200),   # E - purple
    (30, 180, 180),   # F - teal
    (200, 100, 50),   # G - brown
    (100, 200, 100),  # H - light green
    (200, 50, 150),   # I - pink
    (80, 80, 200),    # J - indigo
    (180, 180, 50),   # K - olive
    (50, 50, 50),     # L - dark gray
]

BOT_COLORS = [
    (0, 120, 255),    # bot 1 - blue
    (255, 60, 60),    # bot 2 - red
    (0, 200, 80),     # bot 3 - green
    (255, 160, 0),    # bot 4 - orange
    (180, 0, 255),    # bot 5 - purple
    (0, 200, 200),    # bot 6 - cyan
]

STATION_R = 8
HUB_R = 12
MARGIN = 80
FPS = 5


def parse_log(log_path, round_num):
    """Extract network and solutions from results.log for a given round."""
    with open(log_path, 'r') as f:
        content = f.read()

    # Find the round
    pattern = f"--- ROUND {round_num}:"
    idx = content.find(pattern)
    if idx < 0:
        print(f"Round {round_num} not found in {log_path}")
        sys.exit(1)

    # Find next round or end
    next_round = content.find(f"--- ROUND {round_num + 1}:", idx + 1)
    if next_round < 0:
        next_round = content.find("=" * 40, idx + 1)
    if next_round < 0:
        next_round = len(content)

    block = content[idx:next_round]

    # Extract network JSON
    net_start = block.find("NETWORK:\n") + len("NETWORK:\n")
    # Find end of JSON (next blank line after closing brace)
    brace_depth = 0
    net_end = net_start
    for i in range(net_start, len(block)):
        if block[i] == '{': brace_depth += 1
        elif block[i] == '}': brace_depth -= 1
        if brace_depth == 0 and i > net_start:
            net_end = i + 1
            break

    network = json.loads(block[net_start:net_end])

    # Extract solutions
    solutions = {}
    sol_start = block.find("SOLUTIONS:")
    if sol_start >= 0:
        sol_block = block[sol_start:]
        # Parse each bot's solution
        bot_pattern = r'  (\S+) \((VALID|INVALID)[^)]*\):\n    start_time: (\S+)\n    route \((\d+) stations\): (\[.*?\])'
        for m in re.finditer(bot_pattern, sol_block):
            name = m.group(1)
            status = m.group(2)
            start_time = m.group(3)
            route = json.loads(m.group(5))
            solutions[name] = {
                "status": status,
                "start_time": start_time,
                "route": route,
            }

    # Extract scores from the round results
    scores = {}
    for line in block.split('\n'):
        m = re.match(r'\s+(\S+)\s+\|\s+(\d+)min', line)
        if m:
            scores[m.group(1)] = int(m.group(2))

    return network, solutions, scores


def layout_stations(network):
    """Compute (x, y) positions for each station using a force-directed-ish layout."""
    positions = {}
    lines = network["lines"]

    # Layout each line as a horizontal/angled strip
    n_lines = len(lines)
    total_h = 600
    line_spacing = total_h / (n_lines + 1)

    for li, line in enumerate(lines):
        stations = line["stations"]
        segments = line["segments"]
        n = len(stations)

        # Cumulative x from segments
        cum = [0]
        for s in segments:
            cum.append(cum[-1] + s)
        total_len = cum[-1]

        # Spread across width
        y_base = MARGIN + (li + 1) * line_spacing
        # Slight angle per line for visual variety
        angle = (li - n_lines / 2) * 0.05

        for si, st in enumerate(stations):
            if st not in positions:
                frac = cum[si] / max(total_len, 1)
                x = MARGIN + frac * 700
                y = y_base + angle * (frac - 0.5) * 200
                positions[st] = (x, y)

    # Pull transfer hubs together
    for _ in range(50):
        for t in network["transfers"]:
            s1, s2 = t[0], t[1]
            if s1 in positions and s2 in positions:
                x1, y1 = positions[s1]
                x2, y2 = positions[s2]
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                positions[s1] = (x1 * 0.9 + mx * 0.1, y1 * 0.9 + my * 0.1)
                positions[s2] = (x2 * 0.9 + mx * 0.1, y2 * 0.9 + my * 0.1)

    return positions


def draw_network(draw, network, positions, hub_set, w, h):
    """Draw the base subway map."""
    # Draw lines
    for li, line in enumerate(network["lines"]):
        color = LINE_COLORS[li % len(LINE_COLORS)]
        stations = line["stations"]
        for i in range(len(stations) - 1):
            s1, s2 = stations[i], stations[i + 1]
            if s1 in positions and s2 in positions:
                x1, y1 = positions[s1]
                x2, y2 = positions[s2]
                draw.line([(x1, y1), (x2, y2)], fill=color, width=3)

    # Draw transfer connections
    for t in network["transfers"]:
        s1, s2 = t[0], t[1]
        if s1 in positions and s2 in positions:
            x1, y1 = positions[s1]
            x2, y2 = positions[s2]
            draw.line([(x1, y1), (x2, y2)], fill=(150, 150, 150), width=2)

    # Draw stations
    for li, line in enumerate(network["lines"]):
        color = LINE_COLORS[li % len(LINE_COLORS)]
        for st in line["stations"]:
            if st in positions:
                x, y = positions[st]
                r = HUB_R if st in hub_set else STATION_R
                draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255), outline=color, width=2)

    # Station labels (small, offset)
    for st, (x, y) in positions.items():
        draw.text((x + STATION_R + 2, y - 5), st, fill=(80, 80, 80))


def make_animation(network, solutions, scores, output_path):
    """Generate animated PNG showing bots traversing the network."""
    positions = layout_stations(network)

    # Compute image bounds
    all_x = [p[0] for p in positions.values()]
    all_y = [p[1] for p in positions.values()]
    W = int(max(all_x) + MARGIN * 2)
    H = int(max(all_y) + MARGIN * 2 + 80)  # extra for legend

    # Build hub set
    hub_set = set()
    for t in network["transfers"]:
        hub_set.add(t[0])
        hub_set.add(t[1])

    # Build bot list (sorted by score, best first)
    bots = sorted(solutions.keys(), key=lambda b: scores.get(b, 9999))

    # Find max route length
    max_steps = max((len(s["route"]) for s in solutions.values()), default=1)

    frames = []

    # Title frame
    for _ in range(FPS * 2):
        img = Image.new('RGB', (W, H), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw_network(draw, network, positions, hub_set, W, H)

        n_stations = sum(len(l["stations"]) for l in network["lines"])
        draw.text((10, 5), f"Subway Speedrun — {len(network['lines'])} lines, {n_stations} stations, {len(network['transfers'])} transfers",
                  fill=(0, 0, 0))

        # Legend
        ly = H - 70
        for bi, name in enumerate(bots):
            color = BOT_COLORS[bi % len(BOT_COLORS)]
            dur = scores.get(name, "?")
            draw.ellipse([10, ly - 5, 22, ly + 7], fill=color)
            draw.text((26, ly - 5), f"{name} ({dur}min)", fill=color)
            ly += 18

        frames.append(img)

    # Animation frames: step through routes
    for step in range(max_steps):
        img = Image.new('RGB', (W, H), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw_network(draw, network, positions, hub_set, W, H)

        draw.text((10, 5), f"Step {step + 1}/{max_steps}", fill=(0, 0, 0))

        # Legend
        ly = H - 70
        for bi, name in enumerate(bots):
            color = BOT_COLORS[bi % len(BOT_COLORS)]
            dur = scores.get(name, "?")
            route = solutions[name]["route"]
            current = route[min(step, len(route) - 1)] if route else "?"
            draw.ellipse([10, ly - 5, 22, ly + 7], fill=color)
            draw.text((26, ly - 5), f"{name}: {current} ({dur}min)", fill=color)
            ly += 18

        # Draw bot trails and current positions
        for bi, name in enumerate(bots):
            color = BOT_COLORS[bi % len(BOT_COLORS)]
            route = solutions[name]["route"]
            trail_color = (color[0] // 3 + 170, color[1] // 3 + 170, color[2] // 3 + 170)

            # Draw trail
            for i in range(min(step, len(route) - 1)):
                s1 = route[i]
                s2 = route[i + 1]
                if s1 in positions and s2 in positions:
                    x1, y1 = positions[s1]
                    x2, y2 = positions[s2]
                    # Offset slightly per bot to avoid overlap
                    off = (bi - len(bots) / 2) * 3
                    draw.line([(x1 + off, y1 + off), (x2 + off, y2 + off)],
                              fill=trail_color, width=2)

            # Draw current position
            if step < len(route):
                st = route[step]
                if st in positions:
                    x, y = positions[st]
                    off = (bi - len(bots) / 2) * 3
                    r = 6
                    draw.ellipse([x + off - r, y + off - r, x + off + r, y + off + r], fill=color)

        frames.append(img)

    # Hold final frame
    for _ in range(FPS * 3):
        frames.append(frames[-1].copy())

    # Save
    durations = [200] * len(frames)  # 200ms per frame = 5fps
    durations[:FPS * 2] = [500] * (FPS * 2)  # title frames slower
    durations[-FPS * 3:] = [500] * (FPS * 3)  # hold last frames

    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
    )
    print(f"Saved {output_path} ({len(frames)} frames, {W}x{H})")


def main():
    if len(sys.argv) < 3:
        print("Usage: python visualize_round.py <results.log> <round_number>")
        sys.exit(1)

    log_path = sys.argv[1]
    round_num = int(sys.argv[2])

    network, solutions, scores = parse_log(log_path, round_num)

    if not solutions:
        print(f"No valid solutions found for round {round_num}")
        sys.exit(1)

    print(f"Round {round_num}: {len(network['lines'])} lines, {len(solutions)} bots with solutions")
    for name, sol in solutions.items():
        dur = scores.get(name, "?")
        print(f"  {name}: {len(sol['route'])} stations, {dur}min, start={sol['start_time']}")

    output = f"round_{round_num}.png"
    make_animation(network, solutions, scores, output)


if __name__ == '__main__':
    main()
