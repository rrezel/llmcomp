"""
Generate Soviet postal code PPM images with noise, scale, and rotation.
Digits drawn by connecting dots on the 52-dot grid extracted from the reference image.
"""
import random
import math

random.seed(42)

# 52 dot positions (normalized 0-1), extracted from the reference image
DOT_GRID = [
    (0.000, 0.000), (0.197, 0.000), (0.401, 0.000), (0.602, 0.000), (0.803, 0.000), (0.995, 0.003),  # 1-6
    (0.000, 0.091), (0.858, 0.070), (1.000, 0.091),  # 7-9
    (0.725, 0.133),  # 10
    (0.000, 0.182), (0.593, 0.196), (1.000, 0.182),  # 11-13
    (0.459, 0.260),  # 14
    (0.000, 0.273), (1.000, 0.273),  # 15-16
    (0.325, 0.324),  # 17
    (0.000, 0.364), (1.000, 0.364),  # 18-19
    (0.194, 0.387),  # 20
    (0.000, 0.454), (0.062, 0.450), (1.000, 0.454),  # 21-23
    (0.017, 0.511), (0.204, 0.512), (0.394, 0.512), (0.580, 0.511), (0.768, 0.512), (0.976, 0.517),  # 24-29
    (0.000, 0.545), (1.000, 0.545),  # 30-31
    (0.858, 0.585),  # 32
    (0.000, 0.636), (0.725, 0.648), (1.000, 0.636),  # 33-35
    (0.000, 0.727), (0.593, 0.711), (1.000, 0.727),  # 36-38
    (0.459, 0.775),  # 39
    (0.000, 0.818), (1.000, 0.818),  # 40-41
    (0.325, 0.839),  # 42
    (0.194, 0.902),  # 43
    (0.000, 0.909), (1.000, 0.909),  # 44-45
    (0.062, 0.965),  # 46
    (0.000, 1.000), (0.197, 1.000), (0.401, 1.000), (0.602, 1.000), (0.803, 1.000), (1.000, 1.000),  # 47-52
]

# Digit stroke sequences from sequences.md (1-based dot indices)
# Each digit is a list of strokes; each stroke is a list of dot indices to connect in order.
DIGIT_STROKES = {
    0: [[1,2,3,4,5,6,9,13,16,19,23,29,31,35,38,41,45,52,51,50,49,48,47,44,40,36,33,30,24,21,18,15,11,7,1]],
    1: [[24,22,20,17,14,12,10,8,6,9,13,16,19,23,29,31,35,38,41,45,52]],
    2: [[1,2,3,4,5,6,9,13,16,19,23,29,32,34,37,39,42,43,46,47,48,49,50,51,52]],
    3: [[1,2,3,4,5,6,8,10,12,14,17,20,22,24,25,26,27,28,29,32,34,37,39,42,43,46,47]],
    4: [
        [1,7,11,15,18,21,24,25,26,27,28,29],       # left + middle
        [6,9,13,16,19,23,29,31,35,38,41,45,52],     # right vertical
    ],
    5: [[6,5,4,3,2,1,7,11,15,18,21,24,25,26,27,28,29,31,35,38,41,45,52,51,50,49,48,47]],
    6: [
        [6,8,10,12,14,17,20,22,24],                                          # diagonal
        [24,30,33,36,40,44,47,48,49,50,51,52,45,41,38,35,31,29,28,27,26,25,24],  # bottom loop
    ],
    7: [[1,2,3,4,5,6,8,10,12,14,17,20,22,24,30,33,36,40,44,47]],
    8: [
        [1,2,3,4,5,6,9,13,16,19,23,29,31,35,38,41,45,52,51,50,49,48,47,44,40,36,33,30,24,21,18,15,11,7,1],  # outer
        [24,25,26,27,28,29],  # crossbar
    ],
    9: [
        [24,21,18,15,11,7,1,2,3,4,5,6,9,13,16,19,23,29,28,27,26,25,24],  # top loop
        [29,32,34,37,39,42,43,46,47],  # bottom diagonal
    ],
}

# Cell dimensions
CELL_W = 60
CELL_H = 100
LINE_THICKNESS = 7
CELL_PAD = 16
BORDER = 24

def get_dot_px(dot_idx, cell_x, cell_y):
    """Get pixel position of a dot (1-based index) within a cell."""
    nx, ny = DOT_GRID[dot_idx - 1]
    return (cell_x + nx * CELL_W, cell_y + ny * CELL_H)

def draw_thick_line(pixels, img_w, img_h, x0, y0, x1, y1, thickness):
    margin = thickness + 2
    min_x = max(0, int(min(x0, x1) - margin))
    max_x = min(img_w - 1, int(max(x0, x1) + margin))
    min_y = max(0, int(min(y0, y1) - margin))
    max_y = min(img_h - 1, int(max(y0, y1) + margin))
    dx, dy = x1 - x0, y1 - y0
    seg_len_sq = dx * dx + dy * dy
    for py in range(min_y, max_y + 1):
        for px in range(min_x, max_x + 1):
            if seg_len_sq == 0:
                dist = math.sqrt((px - x0) ** 2 + (py - y0) ** 2)
            else:
                t = max(0, min(1, ((px - x0) * dx + (py - y0) * dy) / seg_len_sq))
                proj_x = x0 + t * dx
                proj_y = y0 + t * dy
                dist = math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)
            if dist <= thickness / 2:
                pixels[py * img_w + px] = [0, 0, 0]

DOT_RADIUS = 3  # radius of background grid dots

def render_dots(pixels, img_w, img_h, cell_x, cell_y):
    """Draw all 52 background grid dots for a cell."""
    for i in range(52):
        px, py = get_dot_px(i + 1, cell_x, cell_y)
        ipx, ipy = int(px), int(py)
        for dy in range(-DOT_RADIUS, DOT_RADIUS + 1):
            for dx in range(-DOT_RADIUS, DOT_RADIUS + 1):
                if dx * dx + dy * dy <= DOT_RADIUS * DOT_RADIUS:
                    nx, ny = ipx + dx, ipy + dy
                    if 0 <= nx < img_w and 0 <= ny < img_h:
                        pixels[ny * img_w + nx] = [0, 0, 0]

def render_digit(pixels, img_w, img_h, digit, cell_x, cell_y):
    """Draw grid dots + digit strokes for a cell."""
    render_dots(pixels, img_w, img_h, cell_x, cell_y)
    if digit is not None:
        for stroke in DIGIT_STROKES[digit]:
            for i in range(len(stroke) - 1):
                x0, y0 = get_dot_px(stroke[i], cell_x, cell_y)
                x1, y1 = get_dot_px(stroke[i + 1], cell_x, cell_y)
                draw_thick_line(pixels, img_w, img_h, x0, y0, x1, y1, LINE_THICKNESS)

def generate_grid_image(n_cells):
    """Generate an image with n_cells empty dot grids (no digits)."""
    img_w = BORDER * 2 + n_cells * CELL_W + (n_cells - 1) * CELL_PAD
    img_h = BORDER * 2 + CELL_H
    pixels = [[255, 255, 255] for _ in range(img_w * img_h)]
    for i in range(n_cells):
        cx = BORDER + i * (CELL_W + CELL_PAD)
        cy = BORDER
        render_dots(pixels, img_w, img_h, cx, cy)
    return pixels, img_w, img_h

def generate_code_image(code, noise=0.05, scale_range=0.10, rotation_range=10.0):
    n_digits = len(code)
    img_w = BORDER * 2 + n_digits * CELL_W + (n_digits - 1) * CELL_PAD
    img_h = BORDER * 2 + CELL_H
    pixels = [[255, 255, 255] for _ in range(img_w * img_h)]

    for i, ch in enumerate(code):
        cx = BORDER + i * (CELL_W + CELL_PAD)
        cy = BORDER
        render_digit(pixels, img_w, img_h, int(ch), cx, cy)

    # Scale
    scale = 1.0 + random.uniform(-scale_range, scale_range)
    new_w = max(1, int(img_w * scale))
    new_h = max(1, int(img_h * scale))
    scaled = [[255, 255, 255] for _ in range(new_w * new_h)]
    for ny in range(new_h):
        for nx in range(new_w):
            ix, iy = int(nx / scale), int(ny / scale)
            if 0 <= ix < img_w and 0 <= iy < img_h:
                scaled[ny * new_w + nx] = list(pixels[iy * img_w + ix])

    # Rotate
    angle_deg = random.uniform(-rotation_range, rotation_range)
    angle = math.radians(angle_deg)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    diag = int(math.sqrt(new_w ** 2 + new_h ** 2)) + 4
    out_w, out_h = diag, diag
    cx_src, cy_src = new_w / 2, new_h / 2
    cx_dst, cy_dst = out_w / 2, out_h / 2
    rotated = [[255, 255, 255] for _ in range(out_w * out_h)]
    for oy in range(out_h):
        for ox in range(out_w):
            dx, dy = ox - cx_dst, oy - cy_dst
            sx = cos_a * dx + sin_a * dy + cx_src
            sy = -sin_a * dx + cos_a * dy + cy_src
            ix, iy = int(sx), int(sy)
            if 0 <= ix < new_w and 0 <= iy < new_h:
                rotated[oy * out_w + ox] = list(scaled[iy * new_w + ix])

    # Noise
    for i in range(len(rotated)):
        if random.random() < noise:
            rotated[i] = [0, 0, 0] if rotated[i][0] > 128 else [255, 255, 255]

    return rotated, out_w, out_h, scale, angle_deg

def write_ppm(path, pixels, w, h):
    """Write ASCII PPM (P3)."""
    with open(path, "w") as f:
        f.write(f"P3\n{w} {h}\n255\n")
        for i, px in enumerate(pixels):
            f.write(f"{px[0]} {px[1]} {px[2]}")
            f.write("\n" if (i + 1) % w == 0 else " ")

if __name__ == "__main__":
    # 1. reference_digits.ppm — all 10 digits, clean, with dot grid visible
    random.seed(100)
    ref_pixels, rw, rh, _, _ = generate_code_image("0123456789", noise=0.0, scale_range=0.0, rotation_range=0.0)
    write_ppm("reference_digits.ppm", ref_pixels, rw, rh)
    print(f"Generated reference_digits.ppm: {rw}x{rh}")

    # 2. reference_grid.ppm — 6 empty cells, dots only, no digits
    grid_pixels, gw, gh = generate_grid_image(6)
    write_ppm("reference_grid.ppm", grid_pixels, gw, gh)
    print(f"Generated reference_grid.ppm: {gw}x{gh}")

    # 3. example.ppm — 345678, noisy with scale/rotation
    random.seed(42)
    CODE = "345678"
    pixels, w, h, scale, rot = generate_code_image(CODE)
    write_ppm("example.ppm", pixels, w, h)
    print(f"Generated example.ppm: {w}x{h}, code={CODE}, scale={scale:.2f}, rotation={rot:.1f}°")
