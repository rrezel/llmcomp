import socket
import sys
import re
import math

# --- Data Structures for Soviet Postal Codes ---

DOTS = {
    1: (0.000, 0.000), 2: (0.197, 0.000), 3: (0.401, 0.000),
    4: (0.602, 0.000), 5: (0.803, 0.000), 6: (0.995, 0.003),
    7: (0.000, 0.091), 8: (0.858, 0.070), 9: (1.000, 0.091),
    10: (0.725, 0.133), 11: (0.000, 0.182), 12: (0.593, 0.196),
    13: (1.000, 0.182), 14: (0.459, 0.260), 15: (0.000, 0.273),
    16: (1.000, 0.273), 17: (0.325, 0.324), 18: (0.000, 0.364),
    19: (1.000, 0.364), 20: (0.194, 0.387), 21: (0.000, 0.454),
    22: (0.062, 0.450), 23: (1.000, 0.454), 24: (0.017, 0.511),
    25: (0.204, 0.512), 26: (0.394, 0.512), 27: (0.580, 0.511),
    28: (0.768, 0.512), 29: (0.976, 0.517), 30: (0.000, 0.545),
    31: (1.000, 0.545), 32: (0.858, 0.585), 33: (0.000, 0.636),
    34: (0.725, 0.648), 35: (1.000, 0.636), 36: (0.000, 0.727),
    37: (0.593, 0.711), 38: (1.000, 0.727), 39: (0.459, 0.775),
    40: (0.000, 0.818), 41: (1.000, 0.818), 42: (0.325, 0.839),
    43: (0.194, 0.902), 44: (0.000, 0.909), 45: (1.000, 0.909),
    46: (0.062, 0.965), 47: (0.000, 1.000), 48: (0.197, 1.000),
    49: (0.401, 1.000), 50: (0.602, 1.000), 51: (0.803, 1.000),
    52: (1.000, 1.000)
}

STROKES = {
    0: [[1,2,3,4,5,6,9,13,16,19,23,29,31,35,38,41,45,52,51,50,49,48,47,44,40,36,33,30,24,21,18,15,11,7,1]],
    1: [[24,22,20,17,14,12,10,8,6,9,13,16,19,23,29,31,35,38,41,45,52]],
    2: [[1,2,3,4,5,6,9,13,16,19,23,29,32,34,37,39,42,43,46,47,48,49,50,51,52]],
    3: [[1,2,3,4,5,6,8,10,12,14,17,20,22,24,25,26,27,28,29,32,34,37,39,42,43,46,47]],
    4: [[1,7,11,15,18,21,24,25,26,27,28,29], [6,9,13,16,19,23,29,31,35,38,41,45,52]],
    5: [[6,5,4,3,2,1,7,11,15,18,21,24,25,26,27,28,29,31,35,38,41,45,52,51,50,49,48,47]],
    6: [[6,8,10,12,14,17,20,22,24], [24,30,33,36,40,44,47,48,49,50,51,52,45,41,38,35,31,29,28,27,26,25,24]],
    7: [[1,2,3,4,5,6,8,10,12,14,17,20,22,24,30,33,36,40,44,47]],
    8: [[1,2,3,4,5,6,9,13,16,19,23,29,31,35,38,41,45,52,51,50,49,48,47,44,40,36,33,30,24,21,18,15,11,7,1], [24,25,26,27,28,29]],
    9: [[24,21,18,15,11,7,1,2,3,4,5,6,9,13,16,19,23,29,28,27,26,25,24], [29,32,34,37,39,42,43,46,47]]
}

# --- Initialization: Pre-render 10 Templates ---

GW, GH = 15, 25
TEMPLATES = {}

def bresenham(x0, y0, x1, y1):
    points = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1: break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
    return points

for d, strokes in STROKES.items():
    t_grid = [[0]*GW for _ in range(GH)]
    for stroke in strokes:
        for i in range(len(stroke)-1):
            p1, p2 = DOTS[stroke[i]], DOTS[stroke[i+1]]
            x0, y0 = int(p1[0] * (GW - 1)), int(p1[1] * (GH - 1))
            x1, y1 = int(p2[0] * (GW - 1)), int(p2[1] * (GH - 1))
            # Draw line with + shape thickness mapping 
            for bx, by in bresenham(x0, y0, x1, y1):
                if 0 <= by < GH and 0 <= bx < GW: t_grid[by][bx] = 1
                if by > 0: t_grid[by-1][bx] = 1
                if by < GH-1: t_grid[by+1][bx] = 1
                if bx > 0: t_grid[by][bx-1] = 1
                if bx < GW-1: t_grid[by][bx+1] = 1
    TEMPLATES[d] = t_grid

# --- Core Processor ---

def process_image(ppm_bytes):
    ppm_str = ppm_bytes.decode('ascii')
    ppm_str = re.sub(r'#.*', '', ppm_str)
    tokens = ppm_str.split()
    
    width, height = int(tokens[1]), int(tokens[2])
    pixels = [int(x) for x in tokens[4:]]
    
    # Extract structural black pixels (Grayscale Red channel threshold)
    black_pixels = [(i % width, i // width) for i in range(width * height) if pixels[i*3] < 128]
            
    # Remove 5% salt-and-pepper noise by requiring 3+ black neighbors
    b_set = set(black_pixels)
    filtered = []
    for x, y in black_pixels:
        count = sum(1 for dx in [-1,0,1] for dy in [-1,0,1] if (x+dx, y+dy) in b_set)
        if count >= 4:
            filtered.append((x, y))
            
    # Projection Variance approach to estimate rotation (-12 to +12 degrees)
    best_angle, max_var = 0, -1
    for angle_deg in range(-12, 13, 1):
        theta = math.radians(angle_deg)
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        bins = {}
        for x, y in filtered:
            rx = int(x * cos_t - y * sin_t)
            bins[rx] = bins.get(rx, 0) + 1
        var = sum(v*v for v in bins.values())
        if var > max_var:
            max_var = var
            best_angle = theta
            
    # Apply optimal rotation
    cos_t, sin_t = math.cos(best_angle), math.sin(best_angle)
    rotated = [(x * cos_t - y * sin_t, x * sin_t + y * cos_t) for x, y in filtered]
        
    # Segment 6 digits via 1D K-Means on the robust X coordinates
    X_rot = sorted([p[0] for p in rotated])
    if not X_rot: return "000000"
    
    min_x, max_x = X_rot[int(len(X_rot)*0.01)], X_rot[int(len(X_rot)*0.99)]
    W = max_x - min_x
    centers = [min_x + W/12 + i * W/6 for i in range(6)]
    
    for _ in range(10): # Converges extremely fast
        clusters = [[] for _ in range(6)]
        for rx in X_rot:
            if rx < min_x or rx > max_x: continue
            best_c = min(range(6), key=lambda i: abs(rx - centers[i]))
            clusters[best_c].append(rx)
        for i in range(6):
            if clusters[i]: centers[i] = sum(clusters[i]) / len(clusters[i])
                
    centers.sort()
    
    # Group coordinates into digits
    digit_pixels = [[] for _ in range(6)]
    for rx, ry in rotated:
        if rx < min_x - W/6 or rx > max_x + W/6: continue 
        best_c = min(range(6), key=lambda i: abs(rx - centers[i]))
        digit_pixels[best_c].append((rx, ry))
        
    # Render and Match
    result_digits = []
    for i in range(6):
        pixels = digit_pixels[i]
        if not pixels:
            result_digits.append("0")
            continue
            
        xs, ys = sorted([p[0] for p in pixels]), sorted([p[1] for p in pixels])
        n = len(pixels)
        x_min, x_max = xs[int(n * 0.02)], xs[int(n * 0.98)]
        y_min, y_max = ys[int(n * 0.02)], ys[int(n * 0.98)]
        
        # Draw onto digit's local normalized grid
        grid = [[0]*GW for _ in range(GH)]
        for rx, ry in pixels:
            nx = max(0.0, min(1.0, (rx - x_min) / (x_max - x_min + 1e-5)))
            ny = max(0.0, min(1.0, (ry - y_min) / (y_max - y_min + 1e-5)))
            gx, gy = int(nx * (GW - 1)), int(ny * (GH - 1))
            
            # Thick fill extracted strokes
            grid[gy][gx] = 1
            if gy > 0: grid[gy-1][gx] = 1
            if gy < GH-1: grid[gy+1][gx] = 1
            if gx > 0: grid[gy][gx-1] = 1
            if gx < GW-1: grid[gy][gx+1] = 1
            
        # Micro-offset template matching for scale variance/offset forgiveness 
        best_score, best_digit = -1, 0
        for d in range(10):
            t_grid = TEMPLATES[d]
            for dx in [-1, 0, 1]:
                for dy in [-2, -1, 0, 1, 2]:
                    intersection, union = 0, 0
                    for y in range(GH):
                        for x in range(GW):
                            v1 = grid[y+dy][x+dx] if (0 <= y+dy < GH and 0 <= x+dx < GW) else 0
                            v2 = t_grid[y][x]
                            if v1 and v2: intersection += 1
                            if v1 or v2: union += 1
                            
                    score = intersection / (union + 1e-5)
                    if score > best_score:
                        best_score, best_digit = score, d
                        
        result_digits.append(str(best_digit))
        
    return "".join(result_digits)

# --- TCP Loop ---

def main():
    host, port = 'localhost', 7474
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    
    f = s.makefile('rwb')
    f.write(b'gemini_bot\n')
    f.flush()
    
    while True:
        line = f.readline()
        if not line: break
        line = line.decode('utf-8').strip()
        
        if line.startswith('ROUND'):
            # Read size payload
            size_line = f.readline().decode('utf-8').strip()
            size = int(size_line.split()[1])
            
            # Grab strictly exact PPM payload 
            ppm_data = f.read(size)
            
            result = process_image(ppm_data)
            
            f.write(f"{result}\n".encode('utf-8'))
            f.flush()
            
            resp = f.readline().decode('utf-8').strip()
            print(f"[{line}] Sent: {result} | Server: {resp}")
            
            if resp == 'ELIMINATED': break
        elif line == 'ELIMINATED': break

if __name__ == '__main__':
    main()