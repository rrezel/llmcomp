from PIL import Image, ImageDraw
import sys

# Grid and layout parameters
CELL_W = 10      # width of one grid step
CELL_H = 10      # height of one grid step
DIGIT_W = 4      # grid width of a digit box
DIGIT_H = 8      # grid height of a digit box
MARGIN = 2       # grid margin around digit
SPACING = 2      # grid spacing between digits
STROKE = 2       # line thickness

# Each digit is defined as a list of polylines.
# Points are in digit-local grid coordinates (0..DIGIT_W, 0..DIGIT_H).
DIGITS = {
    '0': [[(0, 0), (0, DIGIT_H), (DIGIT_W, DIGIT_H), (DIGIT_W, 0), (0, 0)]],
    '1': [[(0, DIGIT_H), (DIGIT_W, 0)]],
    '2': [[(0, DIGIT_H), (DIGIT_W, DIGIT_H), (DIGIT_W, DIGIT_H//2),
           (0, 0), (DIGIT_W, 0)]],
    '3': [[(0, DIGIT_H), (DIGIT_W, DIGIT_H), (DIGIT_W, DIGIT_H//2),
           (0, DIGIT_H//2), (DIGIT_W, DIGIT_H//2),
           (DIGIT_W, 0), (0, 0)]],
    '4': [[(0, DIGIT_H), (0, DIGIT_H//2),
           (DIGIT_W, DIGIT_H//2), (DIGIT_W, DIGIT_H)],
          [(DIGIT_W, 0), (DIGIT_W, DIGIT_H//2)]],
    '5': [[(DIGIT_W, DIGIT_H), (0, DIGIT_H),
           (0, DIGIT_H//2), (DIGIT_W, DIGIT_H//2),
           (DIGIT_W, 0), (0, 0)]],
    '6': [[(DIGIT_W, DIGIT_H), (0, DIGIT_H),
           (0, 0), (DIGIT_W, 0), (DIGIT_W, DIGIT_H//2),
           (0, DIGIT_H//2)]],
    '7': [[(0, DIGIT_H), (DIGIT_W, 0)]],
    '8': [[(0, 0), (0, DIGIT_H), (DIGIT_W, DIGIT_H),
           (DIGIT_W, 0), (0, 0)],
          [(0, DIGIT_H//2), (DIGIT_W, DIGIT_H//2)]],
    '9': [[(DIGIT_W, 0), (DIGIT_W, DIGIT_H),
           (0, DIGIT_H), (0, DIGIT_H//2),
           (DIGIT_W, DIGIT_H//2)]],
}

def render_postal_code(code: str, out_file: str) -> None:
    if len(code) != 6 or not code.isdigit():
        raise ValueError("Postal code must be exactly 6 digits")

    # Compute image size in pixels
    digit_grid_w = DIGIT_W + 2 * MARGIN
    total_grid_w = 6 * digit_grid_w + (6 - 1) * SPACING
    total_grid_h = DIGIT_H + 2 * MARGIN
    img_w = total_grid_w * CELL_W
    img_h = total_grid_h * CELL_H

    img = Image.new("L", (img_w, img_h), 255)  # white background
    draw = ImageDraw.Draw(img)

    for idx, ch in enumerate(code):
        digit = DIGITS[ch]
        # left-top corner of digit box in grid coords
        offset_x = idx * (digit_grid_w + SPACING) + MARGIN
        offset_y = MARGIN

        for poly in digit:
            pts = []
            for x, y in poly:
                gx = (offset_x + x) * CELL_W
                gy = (offset_y + y) * CELL_H
                pts.append((gx, gy))
            draw.line(pts, fill=0, width=STROKE)

    img.save(out_file)
    print(f"Saved {code} to {out_file}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python soviet_postal_code.py <6-digit-code> <output.png>")
        sys.exit(1)
    render_postal_code(sys.argv[1], sys.argv[2])
