import socket
import sys
import math

dot_coords = [
    (0.000, 0.000), (0.197, 0.000), (0.401, 0.000), (0.602, 0.000), (0.803, 0.000), (0.995, 0.003),
    (0.000, 0.091), (0.858, 0.070), (1.000, 0.091), (0.725, 0.133), (0.000, 0.182), (0.593, 0.196),
    (1.000, 0.182), (0.459, 0.260), (0.000, 0.273), (1.000, 0.273), (0.325, 0.324), (0.000, 0.364),
    (1.000, 0.364), (0.194, 0.387), (0.000, 0.454), (0.062, 0.450), (1.000, 0.454), (0.017, 0.511),
    (0.204, 0.512), (0.394, 0.512), (0.580, 0.511), (0.768, 0.512), (0.976, 0.517), (0.000, 0.545),
    (1.000, 0.545), (0.858, 0.585), (0.000, 0.636), (0.725, 0.648), (1.000, 0.636), (0.000, 0.727),
    (0.593, 0.711), (1.000, 0.727), (0.459, 0.775), (0.000, 0.818), (1.000, 0.818), (0.325, 0.839),
    (0.194, 0.902), (0.000, 0.909), (1.000, 0.909), (0.062, 0.965), (0.000, 1.000), (0.197, 1.000),
    (0.401, 1.000), (0.602, 1.000), (0.803, 1.000), (1.000, 1.000)
]

def get_strokes():
    strokes = {}
    # 0
    s0 = [0,1,2,3,4,5,8,12,15,18,22,28,30,34,37,40,44,51,50,49,48,47,46,43,39,35,32,29,23,20,17,14,10,6,0]
    strokes[0] = [s0]
    # 1
    s1 = [23,21,19,16,13,11,9,7,5,8,12,15,18,22,28,30,34,37,40,44,51]
    strokes[1] = [s1]
    # 2
    s2 = [0,1,2,3,4,5,8,12,15,18,22,28,31,33,36,38,41,42,45,46,47,48,49,50,51]
    strokes[2] = [s2]
    # 3
    s3 = [0,1,2,3,4,5,7,9,11,13,16,19,21,23,24,25,26,27,28,31,33,36,38,41,42,45,46]
    strokes[3] = [s3]
    # 4
    s41 = [0,6,10,14,17,20,23,24,25,26,27,28]
    s42 = [5,8,12,15,18,22,28,30,34,37,40,44,51]
    strokes[4] = [s41, s42]
    # 5
    s5 = [5,4,3,2,1,0,6,10,14,17,20,23,24,25,26,27,28,30,34,37,40,44,51,50,49,48,47,46]
    strokes[5] = [s5]
    # 6
    s61 = [5,7,9,11,13,16,19,21,23]
    s62 = [23,29,32,35,39,43,46,47,48,49,50,51,44,40,37,34,30,28,27,26,25,24,23]
    strokes[6] = [s61, s62]
    # 7
    s7 = [0,1,2,3,4,5,7,9,11,13,16,19,21,23,29,32,35,39,43,46]
    strokes[7] = [s7]
    # 8
    s81 = [0,1,2,3,4,5,8,12,15,18,22,28,30,34,37,40,44,51,50,49,48,47,46,43,39,35,32,29,23,20,17,14,10,6,0]
    s82 = [23,24,25,26,27,28]
    strokes[8] = [s81, s82]
    # 9
    s91 = [23,20,17,14,10,6,0,1,2,3,4,5,8,12,15,18,22,28,27,26,25,24,23]
    s92 = [28,31,33,36,38,41,42,45,46]
    strokes[9] = [s91, s92]
    return strokes

# Precompute all unique segments across all digits for forbidden-stroke penalty
def get_all_segments(strokes_dict):
    segments = set()
    for d_strokes in strokes_dict.values():
        for stroke in d_strokes:
            for i in range(len(stroke) - 1):
                a, b = stroke[i], stroke[i + 1]
                segments.add((min(a, b), max(a, b)))
    return segments

def load_ppm(ppm_data):
    text = ppm_data.decode('ascii')
    tokens = text.split()
    idx = 0
    assert tokens[idx] == 'P3'
    idx += 1
    width = int(tokens[idx])
    idx += 1
    height = int(tokens[idx])
    idx += 1
    maxval = int(tokens[idx])
    idx += 1
    pixels = []
    for _ in range(height):
        row = []
        for _ in range(width):
            r = int(tokens[idx])
            g = int(tokens[idx + 1])
            b = int(tokens[idx + 2])
            idx += 3
            is_black = (r + g + b) < (maxval * 1.5)
            row.append(is_black)
        pixels.append(row)
    return width, height, pixels

def get_line_points(x1, y1, x2, y2):
    points = []
    length = math.hypot(x2 - x1, y2 - y1)
    if length == 0:
        return [(x1, y1)]
    steps = int(length) + 1
    for i in range(steps + 1):
        t = i / steps
        x = x1 + t * (x2 - x1)
        y = y1 + t * (y2 - y1)
        points.append((x, y))
    return points

def find_cells(pixels, width, height):
    col_counts = [0] * width
    for y in range(height):
        for x in range(width):
            if pixels[y][x]:
                col_counts[x] += 1
    max_col = max(col_counts) if col_counts else 0
    col_thresh = max_col * 0.25 if max_col > 0 else 5
    cells_x = []
    start = -1
    in_cell = False
    for x in range(width):
        if col_counts[x] > col_thresh:
            if not in_cell:
                in_cell = True
                start = x
        else:
            if in_cell:
                in_cell = False
                if x - start > 30:
                    cells_x.append((start, x))
    if in_cell and width - start > 30:
        cells_x.append((start, width))
    row_counts = [sum(1 for x in range(width) if pixels[y][x]) for y in range(height)]
    max_row = max(row_counts) if row_counts else 0
    row_thresh = max_row * 0.25 if max_row > 0 else 5
    top = 0
    for y in range(height):
        if row_counts[y] > row_thresh:
            top = y
            break
    bottom = height
    for y in range(height - 1, -1, -1):
        if row_counts[y] > row_thresh:
            bottom = y + 1
            break
    cells = [(l, r, top, bottom) for l, r in cells_x[:6]]
    return cells

def recognize_digit(pixels, width, height, left, right, top, bottom, dot_coords, strokes, all_segments):
    cell_w = right - left
    cell_h = bottom - top
    if cell_w < 20 or cell_h < 20:
        return 0
    scales = [0.92 + i * 0.04 for i in range(5)]
    thetas_deg = [-8, -4, 0, 4, 8]
    dxs = [-6, -3, 0, 3, 6]
    dys = [-6, -3, 0, 3, 6]
    best_score = -1.0
    best_s = best_cth = best_sth = best_cx = best_cy = 0.0
    for s in scales:
        for tdeg in thetas_deg:
            theta = math.radians(tdeg)
            cth = math.cos(theta)
            sth = math.sin(theta)
            for dx in dxs:
                for dy in dys:
                    cx = left + cell_w * 0.5 + dx
                    cy = top + cell_h * 0.5 + dy
                    score = 0.0
                    for nx, ny in dot_coords:
                        rx = (nx - 0.5) * cell_w * s
                        ry = (ny - 0.5) * cell_h * s
                        rx2 = rx * cth - ry * sth
                        ry2 = rx * sth + ry * cth
                        px = cx + rx2
                        py = cy + ry2
                        dark = 0
                        cnt = 0
                        for ddy in range(-1, 2):
                            for ddx in range(-1, 2):
                                px2 = int(px + ddx)
                                py2 = int(py + ddy)
                                if 0 <= px2 < width and 0 <= py2 < height and pixels[py2][px2]:
                                    dark += 1
                                cnt += 1
                        score += dark / cnt
                    if score > best_score:
                        best_score = score
                        best_s = s
                        best_cth = cth
                        best_sth = sth
                        best_cx = cx
                        best_cy = cy
    # Digit recognition with required vs forbidden stroke penalty
    max_score = -float('inf')
    best_d = 0
    for d in range(10):
        if d not in strokes:
            continue
        req_segs = set()
        for stroke in strokes[d]:
            for i in range(len(stroke) - 1):
                a = stroke[i]
                b = stroke[i + 1]
                req_segs.add((min(a, b), max(a, b)))
        forb_segs = all_segments - req_segs
        # required fill
        fill_req = samp_req = 0
        for stroke in strokes[d]:
            for i in range(len(stroke) - 1):
                d1 = stroke[i]
                d2 = stroke[i + 1]
                nx1, ny1 = dot_coords[d1]
                rx = (nx1 - 0.5) * cell_w * best_s
                ry = (ny1 - 0.5) * cell_h * best_s
                rx2 = rx * best_cth - ry * best_sth
                ry2 = rx * best_sth + ry * best_cth
                p1x = best_cx + rx2
                p1y = best_cy + ry2
                nx2, ny2 = dot_coords[d2]
                rx = (nx2 - 0.5) * cell_w * best_s
                ry = (ny2 - 0.5) * cell_h * best_s
                rx2 = rx * best_cth - ry * best_sth
                ry2 = rx * best_sth + ry * best_cth
                p2x = best_cx + rx2
                p2y = best_cy + ry2
                pts = get_line_points(p1x, p1y, p2x, p2y)
                for px, py in pts:
                    ipx = int(px + 0.5)
                    ipy = int(py + 0.5)
                    if 0 <= ipx < width and 0 <= ipy < height and pixels[ipy][ipx]:
                        fill_req += 1
                    samp_req += 1
        req_ratio = fill_req / samp_req if samp_req > 0 else 0.0
        # forbidden fill
        fill_forb = samp_forb = 0
        for a, b in forb_segs:
            nx1, ny1 = dot_coords[a]
            rx = (nx1 - 0.5) * cell_w * best_s
            ry = (ny1 - 0.5) * cell_h * best_s
            rx2 = rx * best_cth - ry * best_sth
            ry2 = rx * best_sth + ry * best_cth
            p1x = best_cx + rx2
            p1y = best_cy + ry2
            nx2, ny2 = dot_coords[b]
            rx = (nx2 - 0.5) * cell_w * best_s
            ry = (ny2 - 0.5) * cell_h * best_s
            rx2 = rx * best_cth - ry * best_sth
            ry2 = rx * best_sth + ry * best_cth
            p2x = best_cx + rx2
            p2y = best_cy + ry2
            pts = get_line_points(p1x, p1y, p2x, p2y)
            for px, py in pts:
                ipx = int(px + 0.5)
                ipy = int(py + 0.5)
                if 0 <= ipx < width and 0 <= ipy < height and pixels[ipy][ipx]:
                    fill_forb += 1
                samp_forb += 1
        forb_ratio = fill_forb / samp_forb if samp_forb > 0 else 0.0
        score = req_ratio - forb_ratio
        if score > max_score:
            max_score = score
            best_d = d
    return best_d

def main():
    HOST = 'localhost'
    PORT = 7474
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    sock.sendall(b"GrokSovietBot\n")

    strokes = get_strokes()
    all_segments = get_all_segments(strokes)

    while True:
        try:
            line = b''
            while True:
                chunk = sock.recv(1)
                if not chunk:
                    return
                line += chunk
                if chunk == b'\n':
                    break
            line = line.decode('ascii').strip()
            if not line.startswith('ROUND'):
                continue
            line = b''
            while True:
                chunk = sock.recv(1)
                if not chunk:
                    return
                line += chunk
                if chunk == b'\n':
                    break
            size_str = line.decode('ascii').strip()
            if size_str.startswith('SIZE'):
                img_size = int(size_str.split()[1])
            else:
                continue
            ppm_data = b''
            while len(ppm_data) < img_size:
                to_read = min(4096, img_size - len(ppm_data))
                chunk = sock.recv(to_read)
                if not chunk:
                    break
                ppm_data += chunk
            if len(ppm_data) < img_size:
                continue
            width, height, pixels = load_ppm(ppm_data)
            cells = find_cells(pixels, width, height)
            answer = ''
            for cell in cells[:6]:
                left, right, top, bottom = cell
                dig = recognize_digit(pixels, width, height, left, right, top, bottom, dot_coords, strokes, all_segments)
                answer += str(dig)
            if len(answer) == 6:
                sock.sendall((answer + '\n').encode())
            else:
                sock.sendall(b'000000\n')
            resp_line = b''
            while True:
                chunk = sock.recv(1)
                if not chunk:
                    return
                resp_line += chunk
                if chunk == b'\n':
                    break
            resp = resp_line.decode('ascii').strip()
            if 'ELIMINATED' in resp:
                print("Eliminated")
                break
        except Exception as e:
            print("Error:", e)
            break

if __name__ == "__main__":
    main()