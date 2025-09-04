# Fixed Hyperplexity animation
# - Preserves center black seam
# - No green "kink" (uses true inner rectangles per half, not self-intersecting polys)
# - Green opacity respected
# - Edge-on line robust at any SCALE_FACTOR
#
# Exports: /mnt/data/hyperplexity_animation_fix.gif

from PIL import Image, ImageDraw
import math

# ========= Tunables =========
SCALE_FACTOR = 4
BASE_SIZE = 140
CANVAS_SIZE = BASE_SIZE * SCALE_FACTOR
CENTER = CANVAS_SIZE // 2
SQUARE_SIZE = 100 * SCALE_FACTOR
FLAG_SIZE = 100 * SCALE_FACTOR

FRAME_COUNT = 120
FRAME_DURATION_MS = 28  # ~36 fps

VIEWING_ANGLE = 45  # degrees (camera pitched downward)
MIN_EDGE_THICKNESS = 6 * SCALE_FACTOR  # visible when edge-on
WHEEL_SPOKES = 8

# Colors
GREEN_RGB = (45, 255, 69)
GREEN_ALPHA = 150  # respect this for all green fills
BLACK = (0, 0, 0, 255)
WHITE = (255, 255, 255, 255)
BORDER_WIDTH = 8 * SCALE_FACTOR

# ========= Helpers =========
def transform_point(cx, cy, x, y, z, rot_y_deg):
    """Rotate a 3D point about Y, then apply a simple camera tilt to screen coords."""
    ry = math.radians(rot_y_deg)
    va = math.radians(VIEWING_ANGLE)
    xr = x * math.cos(ry) - z * math.sin(ry)
    yr = y
    zr = x * math.sin(ry) + z * math.cos(ry)
    sx = cx + xr
    sy = cy + yr * math.cos(va) + zr * math.sin(va)
    return (sx, sy), zr

def rect_to_poly(cx, cy, left, top, right, bottom, rot_y_deg):
    """Project an axis-aligned rectangle (z=0 plane) to a 4-pt polygon and return (poly, avg_z)."""
    corners = [(left, top, 0), (right, top, 0), (right, bottom, 0), (left, bottom, 0)]
    poly = []
    zs = []
    for x,y,z in corners:
        p, zval = transform_point(cx, cy, x, y, z, rot_y_deg)
        poly.append(p)
        zs.append(zval)
    return poly, sum(zs)/4.0

def draw_edge_strip(cx, cy, size, opacity=255):
    """Draw a vertical 'edge-on' strip so the logo never disappears."""
    img = Image.new('RGBA', (CANVAS_SIZE, CANVAS_SIZE), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)

    va = math.radians(VIEWING_ANGLE)
    half_h = size // 2
    visual_half_h = half_h * math.cos(va)
    top_y = cy - visual_half_h
    bot_y = cy + visual_half_h

    # Outer black strip
    x0 = cx - MAX_EDGE_THICKNESS // 2
    x1 = cx + MAX_EDGE_THICKNESS // 2
    d.rectangle([x0, top_y, x1, bot_y], fill=(0,0,0,opacity))

    # Inner green line (70% height)
    inner_h = (bot_y - top_y) * 0.7
    gy0 = cy - inner_h / 2
    gy1 = cy + inner_h / 2
    inner_w = max(2, MAX_EDGE_THICKNESS // 3)
    gx0 = cx - inner_w/2
    gx1 = cx + inner_w/2
    green_alpha = int(min(255, GREEN_ALPHA * (opacity/255)))
    d.rectangle([gx0, gy0, gx1, gy1], fill=(GREEN_RGB[0], GREEN_RGB[1], GREEN_RGB[2], green_alpha))

    return img, 0.0

# Clamp to ensure we never draw too thin a strip
MAX_EDGE_THICKNESS = max(2, MIN_EDGE_THICKNESS)

def draw_half_flag(cx, cy, size, rot_y_deg, is_left, opacity=255):
    """Draw one half using object-space rectangles to avoid self-intersection kinks."""
    # Edge-on check
    angle = (rot_y_deg % 360 + 360) % 360
    if (87 < angle < 93) or (267 < angle < 273):
        return draw_edge_strip(cx, cy, size, opacity)

    hw = size // 2
    hh = size // 2

    # Define object-space rectangles for this half
    if is_left:
        # outer half [-hw, 0]
        outer = (-hw, -hh, 0, hh)
        # inner white gap leaves a center seam of BORDER_WIDTH
        inner_gap = (-hw + BORDER_WIDTH, -hh + BORDER_WIDTH, -BORDER_WIDTH, hh - BORDER_WIDTH)
        # green inner inset (same from all sides, including center seam)
        inner = size - 2 * BORDER_WIDTH
        border = inner * 0.15
        inset = BORDER_WIDTH + border
        green_rect = (-hw + inset, -hh + inset, -inset, hh - inset)
    else:
        outer = (0, -hh, hw, hh)
        inner_gap = (BORDER_WIDTH, -hh + BORDER_WIDTH, hw - BORDER_WIDTH, hh - BORDER_WIDTH)
        inner = size - 2 * BORDER_WIDTH
        border = inner * 0.15
        inset = BORDER_WIDTH + border
        green_rect = (inset, -hh + inset, hw - inset, hh - inset)

    # Compose
    img = Image.new('RGBA', (CANVAS_SIZE, CANVAS_SIZE), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)

    # Outer black
    poly, avg_z = rect_to_poly(CENTER, CENTER, *outer, rot_y_deg)
    d.polygon(poly, fill=(0,0,0,opacity))

    # Inner white (opaque so it actually covers interior)
    poly_gap, _ = rect_to_poly(CENTER, CENTER, *inner_gap, rot_y_deg)
    d.polygon(poly_gap, fill=WHITE)

    # Green center (respect global opacity & configured GREEN_ALPHA)
    poly_green, _ = rect_to_poly(CENTER, CENTER, *green_rect, rot_y_deg)
    green_alpha = int(min(255, GREEN_ALPHA * (opacity/255)))
    d.polygon(poly_green, fill=(GREEN_RGB[0], GREEN_RGB[1], GREEN_RGB[2], green_alpha))

    return img, avg_z

def draw_flag(cx, cy, size, rot_y_deg, opacity=255):
    """Two halves composed with simple painter's order by Z."""
    left_img, left_z = draw_half_flag(cx, cy, size, rot_y_deg, True, opacity)
    right_img, right_z = draw_half_flag(cx, cy, size, rot_y_deg, False, opacity)

    comp = Image.new('RGBA', (CANVAS_SIZE, CANVAS_SIZE), (255, 255, 255, 0))
    if left_z < right_z:
        comp = Image.alpha_composite(comp, left_img)
        comp = Image.alpha_composite(comp, right_img)
    else:
        comp = Image.alpha_composite(comp, right_img)
        comp = Image.alpha_composite(comp, left_img)
    return comp

def draw_eliyahu_square(draw, cx, cy, size):
    """Original square (parent logo)."""
    hs = size // 2
    # black outer
    draw.rectangle([cx-hs, cy-hs, cx+hs, cy+hs], fill=(0,0,0,255))
    # white inner gap
    draw.rectangle([cx-hs+BORDER_WIDTH, cy-hs+BORDER_WIDTH, cx+hs-BORDER_WIDTH, cy+hs-BORDER_WIDTH], fill=(255,255,255,255))
    # green center
    inner = size - 2 * BORDER_WIDTH
    border = inner * 0.15
    inset = BORDER_WIDTH + border
    green_alpha = GREEN_ALPHA
    draw.rectangle([cx-hs+inset, cy-hs+inset, cx+hs-inset, cy+hs-inset], fill=(GREEN_RGB[0], GREEN_RGB[1], GREEN_RGB[2], green_alpha))

def draw_rotating_square(draw, cx, cy, size, rot_y_deg, opacity=255):
    """Billboard-y rotation with minimum edge thickness clamp."""
    ry = math.radians(rot_y_deg)
    hs = size // 2
    apparent = hs * abs(math.cos(ry))

    img = Image.new('RGBA', (CANVAS_SIZE, CANVAS_SIZE), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)

    if apparent < MAX_EDGE_THICKNESS / 2:
        strip, _ = draw_edge_strip(cx, cy, size, opacity)
        return strip

    # Draw squeezed outer black
    corners = [(cx-apparent, cy-hs), (cx+apparent, cy-hs), (cx+apparent, cy+hs), (cx-apparent, cy+hs)]
    d.polygon(corners, fill=(0,0,0,opacity))

    if apparent > BORDER_WIDTH:
        # Inner white gap
        gap = [(cx-apparent+BORDER_WIDTH, cy-hs+BORDER_WIDTH),
               (cx+apparent-BORDER_WIDTH, cy-hs+BORDER_WIDTH),
               (cx+apparent-BORDER_WIDTH, cy+hs-BORDER_WIDTH),
               (cx-apparent+BORDER_WIDTH, cy+hs-BORDER_WIDTH)]
        d.polygon(gap, fill=(255,255,255,255))

        # Green center
        inner = size - 2 * BORDER_WIDTH
        border = inner * 0.15
        inset = BORDER_WIDTH + border
        gw = max(0.0, apparent - inset)
        if gw > 0:
            green = [(cx-gw, cy-hs+inset), (cx+gw, cy-hs+inset), (cx+gw, cy+hs-inset), (cx-gw, cy+hs-inset)]
            green_alpha = int(min(255, GREEN_ALPHA * (opacity/255)))
            d.polygon(green, fill=(GREEN_RGB[0], GREEN_RGB[1], GREEN_RGB[2], green_alpha))
    return img

# ========= Animation schedule =========
def angle_schedule(progress):
    if progress <= 0.12:        # static parent
        return 0.0
    elif progress <= 0.22:      # rotate to edge-on (kept brisk as requested)
        t = (progress - 0.12) / 0.10
        return t * 90
    elif progress <= 0.28:      # emerge as flag
        t = (progress - 0.22) / 0.06
        return 90 * (1 - t)
    elif progress <= 0.52:      # two full rotations
        t = (progress - 0.28) / 0.24
        return t * 720
    elif progress <= 0.66:      # accelerate hard
        t = (progress - 0.52) / 0.14
        return 720 + (t * t) * 2160
    elif progress <= 0.80:      # very fast + motion blur
        t = (progress - 0.66) / 0.14
        return 2880 + t * 5400
    elif progress <= 0.90:      # strobe/wagon wheel illusion
        t = (progress - 0.80) / 0.10
        return -t * 45
    else:                        # settle into spokes
        return 0.0

def create_frame(i):
    progress = i / FRAME_COUNT
    img = Image.new('RGBA', (CANVAS_SIZE, CANVAS_SIZE), WHITE)
    d = ImageDraw.Draw(img)

    if progress <= 0.12:
        draw_eliyahu_square(d, CENTER, CENTER, SQUARE_SIZE)
        return img.convert('RGB')

    if progress <= 0.22:
        t = (progress - 0.12) / 0.10
        rot = t * 90
        sq = draw_rotating_square(d, CENTER, CENTER, SQUARE_SIZE, rot, 255)
        img = Image.alpha_composite(img, sq)
        return img.convert('RGB')

    if progress <= 0.28:
        t = (progress - 0.22) / 0.06
        rot = 90 * (1 - t)
        fl = draw_flag(CENTER, CENTER, FLAG_SIZE, rot, int(255 * t))
        img = Image.alpha_composite(img, fl)
        return img.convert('RGB')

    if progress <= 0.52:
        t = (progress - 0.28) / 0.24
        rot = t * 720
        fl = draw_flag(CENTER, CENTER, FLAG_SIZE, rot, 255)
        img = Image.alpha_composite(img, fl)
        return img.convert('RGB')

    if progress <= 0.66:
        t = (progress - 0.52) / 0.14
        rot = 720 + (t * t) * 2160
        fl = draw_flag(CENTER, CENTER, FLAG_SIZE, rot, 255)
        img = Image.alpha_composite(img, fl)
        return img.convert('RGB')

    if progress <= 0.80:
        t = (progress - 0.66) / 0.14
        base = 2880 + t * 5400
        num = 24
        layers = []
        for j in range(num):
            ang = base + (360 / num) * j
            op = int(30 + (1 - j/num) * 30)
            LH, _ = draw_half_flag(CENTER, CENTER, FLAG_SIZE, ang, True, op)
            RH, _ = draw_half_flag(CENTER, CENTER, FLAG_SIZE, ang, False, op)
            lay = Image.new('RGBA', (CANVAS_SIZE, CANVAS_SIZE), (255, 255, 255, 0))
            lay = Image.alpha_composite(lay, LH)
            lay = Image.alpha_composite(lay, RH)
            layers.append(lay)
        for lay in layers:
            img = Image.alpha_composite(img, lay)
        return img.convert('RGB')

    if progress <= 0.90:
        t = (progress - 0.80) / 0.10
        base = -t * 45
        num = WHEEL_SPOKES
        pairs = []
        for k in range(num):
            ang = base + k * (360 / num)
            LH, lz = draw_half_flag(CENTER, CENTER, FLAG_SIZE, ang, True, 200)
            RH, rz = draw_half_flag(CENTER, CENTER, FLAG_SIZE, ang, False, 200)
            pairs.append((lz, LH)); pairs.append((rz, RH))
        pairs.sort(key=lambda x: x[0])
        for _, layer in pairs:
            img = Image.alpha_composite(img, layer)
        return img.convert('RGB')

    # Final spokes (render halves sorted by depth)
    final = [0, 45, 90, 135, 180, 225, 270, 315]
    halves = []
    for ang in final:
        LH, lz = draw_half_flag(CENTER, CENTER, FLAG_SIZE, ang, True, 255)
        RH, rz = draw_half_flag(CENTER, CENTER, FLAG_SIZE, ang, False, 255)
        halves.append((lz, LH)); halves.append((rz, RH))
    halves.sort(key=lambda x: x[0])
    for _, h in halves:
        img = Image.alpha_composite(img, h)
    return img.convert('RGB')

# ========= Render =========
frames = [create_frame(i) for i in range(FRAME_COUNT)]
frames = frames + [frames[-1]] * 8

out_path = "frontend/hyperplexity_animation_fix.gif"
frames[0].save(out_path, save_all=True, append_images=frames[1:], duration=FRAME_DURATION_MS, loop=0)

out_path
