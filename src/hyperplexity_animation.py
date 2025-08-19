#!/usr/bin/env python3
"""
Hyperplexity Logo Animation Generator - Final Version
Looking DOWN from above - flags appear vertically compressed
"""

import numpy as np
from PIL import Image, ImageDraw
import math

# Animation parameters
SCALE_FACTOR = 2  # Smaller scale for compact GIF
BASE_SIZE = 140  # Smaller base to reduce whitespace
CANVAS_SIZE = BASE_SIZE * SCALE_FACTOR  # Actual render size = 280px
CENTER = CANVAS_SIZE // 2
SQUARE_SIZE = 100 * SCALE_FACTOR  # Scale all elements
FLAG_SIZE = 100 * SCALE_FACTOR  # Flag size
FRAME_COUNT = 180  # More frames for smoother animation
VIEWING_ANGLE = 45  # degrees - looking DOWN from above

# Colors - match HTML exactly
GREEN = (45, 255, 69, 204)  # #2DFF45 with 80% opacity
BLACK = (0, 0, 0, 255)
WHITE = (255, 255, 255)

# Proportions from HTML - all scaled
BORDER_WIDTH = 8 * SCALE_FACTOR  # Black border width
MIN_THICKNESS = 6 * SCALE_FACTOR  # Thicker minimum for edge-on flags
GREEN_SIZE_RATIO = 0.7  # Green is 70% of inner area (ratio stays the same)


def draw_half_flag(center_x, center_y, size, rotation_y, is_left_half, opacity=255, debug=False):
    """Draw HALF of a 3D flag - either left or right half"""
    
    viewing_angle_rad = math.radians(VIEWING_ANGLE)
    rotation_y_rad = math.radians(rotation_y)
    
    half_width = size // 2
    half_height = size // 2
    
    # Create temporary image
    temp_img = Image.new('RGBA', (CANVAS_SIZE, CANVAS_SIZE), (255, 255, 255, 0))
    temp_draw = ImageDraw.Draw(temp_img)
    
    def transform_point(x, y, z):
        # Rotate around Y-axis
        rotated_x = x * math.cos(rotation_y_rad) - z * math.sin(rotation_y_rad)
        rotated_y = y
        rotated_z = x * math.sin(rotation_y_rad) + z * math.cos(rotation_y_rad)
        
        # Apply viewing angle (looking DOWN from above)
        screen_x = center_x + rotated_x
        screen_y = center_y + rotated_y * math.cos(viewing_angle_rad) + rotated_z * math.sin(viewing_angle_rad)
        
        return (screen_x, screen_y), rotated_z
    
    # Check if this half would be edge-on
    angle_normalized = (rotation_y % 360 + 360) % 360
    
    if (87 < angle_normalized < 93) or (267 < angle_normalized < 273):
        return temp_img, 0  # Return empty for edge-on
    
    # Normal (non-edge-on) rendering
    # Define the half we're drawing
    if is_left_half:
        half_corners_3d = [
            (-half_width, -half_height, 0),  # top left
            (0, -half_height, 0),            # top center
            (0, half_height, 0),             # bottom center
            (-half_width, half_height, 0)    # bottom left
        ]
    else:  # right half
        half_corners_3d = [
            (0, -half_height, 0),            # top center
            (half_width, -half_height, 0),   # top right
            (half_width, half_height, 0),    # bottom right
            (0, half_height, 0)              # bottom center
        ]
    
    # Transform corners and calculate average Z
    corners = []
    z_values = []
    for x, y, z in half_corners_3d:
        point, z_val = transform_point(x, y, z)
        corners.append(point)
        z_values.append(z_val)
    
    avg_z = sum(z_values) / len(z_values)
    
    # Determine color for debug mode
    if debug:
        # Color based on Z-depth for debugging
        if avg_z < -30:
            border_color = (150, 0, 0, opacity)  # Dark red for far back
        elif avg_z < 0:
            border_color = (100, 50, 0, opacity)  # Brown for back
        elif avg_z < 30:
            border_color = (0, 50, 100, opacity)  # Dark blue for front
        else:
            border_color = (0, 0, 150, opacity)  # Bright blue for very front
    else:
        border_color = (BLACK[0], BLACK[1], BLACK[2], opacity)
    
    # Draw black border
    temp_draw.polygon(corners, fill=border_color)
    
    # Draw transparent interior
    inner_corners_3d = []
    for x, y, z in half_corners_3d:
        if x == 0:  # Center line
            inner_x = 0
        else:
            inner_x = x + (BORDER_WIDTH if x < 0 else -BORDER_WIDTH)
        inner_y = y + (BORDER_WIDTH if y < 0 else -BORDER_WIDTH)
        inner_corners_3d.append((inner_x, inner_y, z))
    
    inner_corners = []
    for x, y, z in inner_corners_3d:
        point, _ = transform_point(x, y, z)
        inner_corners.append(point)
    
    temp_draw.polygon(inner_corners, fill=(255, 255, 255, 0))
    
    # Draw green center
    green_corners_3d = []
    for x, y, z in half_corners_3d:
        if x == 0:
            green_x = 0
        else:
            green_x = x * 0.7
        green_y = y * 0.7
        green_corners_3d.append((green_x, green_y, z))
    
    green_corners = []
    for x, y, z in green_corners_3d:
        point, _ = transform_point(x, y, z)
        green_corners.append(point)
    
    green_alpha = int(opacity * 0.8)
    temp_draw.polygon(green_corners, fill=(GREEN[0], GREEN[1], GREEN[2], green_alpha))
    
    return temp_img, avg_z

def draw_3d_flag(center_x, center_y, size, rotation_y, opacity=255, debug=False):
    """Draw a 3D flag by combining two halves - for compatibility"""
    
    # Check if edge-on
    angle_normalized = (rotation_y % 360 + 360) % 360
    is_edge_on = (87 < angle_normalized < 93) or (267 < angle_normalized < 273)
    
    if is_edge_on:
        # Return empty image for edge-on flags (no rendering during animation)
        temp_img = Image.new('RGBA', (CANVAS_SIZE, CANVAS_SIZE), (255, 255, 255, 0))
        return temp_img, 0
    
    # Draw left half
    left_img, left_z = draw_half_flag(center_x, center_y, size, rotation_y, 
                                      is_left_half=True, opacity=opacity, debug=debug)
    
    # Draw right half
    right_img, right_z = draw_half_flag(center_x, center_y, size, rotation_y, 
                                        is_left_half=False, opacity=opacity, debug=debug)
    
    # Combine based on Z-depth
    combined = Image.new('RGBA', (CANVAS_SIZE, CANVAS_SIZE), (255, 255, 255, 0))
    if left_z < right_z:
        # Left is behind right
        combined = Image.alpha_composite(combined, left_img)
        combined = Image.alpha_composite(combined, right_img)
    else:
        # Right is behind left
        combined = Image.alpha_composite(combined, right_img)
        combined = Image.alpha_composite(combined, left_img)
    
    avg_z = (left_z + right_z) / 2
    return combined, avg_z

def draw_static_square(draw, x, y, size):
    """Draw the original eliyahu square logo"""
    half_size = size // 2
    
    # Black outer border
    corners = [
        (x - half_size, y - half_size),
        (x + half_size, y - half_size),
        (x + half_size, y + half_size),
        (x - half_size, y + half_size)
    ]
    draw.polygon(corners, fill=BLACK[:3])
    
    # Transparent gap
    gap_corners = [
        (x - half_size + BORDER_WIDTH, y - half_size + BORDER_WIDTH),
        (x + half_size - BORDER_WIDTH, y - half_size + BORDER_WIDTH),
        (x + half_size - BORDER_WIDTH, y + half_size - BORDER_WIDTH),
        (x - half_size + BORDER_WIDTH, y + half_size - BORDER_WIDTH)
    ]
    draw.polygon(gap_corners, fill=(255, 255, 255, 0))
    
    # Green center (70% of inner area)
    inner_size = size - 2 * BORDER_WIDTH
    green_border = inner_size * 0.15
    green_inset = BORDER_WIDTH + green_border
    
    green_corners = [
        (x - half_size + green_inset, y - half_size + green_inset),
        (x + half_size - green_inset, y - half_size + green_inset),
        (x + half_size - green_inset, y + half_size - green_inset),
        (x - half_size + green_inset, y + half_size - green_inset)
    ]
    draw.polygon(green_corners, fill=GREEN[:3])

def draw_rotating_square(draw, x, y, size, rotation_y, opacity=255):
    """Draw the logo rotating to become edge-on"""
    
    rotation_rad = math.radians(rotation_y)
    half_size = size // 2
    
    # Calculate apparent width based on rotation
    apparent_width = half_size * abs(math.cos(rotation_rad))
    
    if apparent_width < 1:
        return None
    
    # Draw rotating square
    corners = [
        (x - apparent_width, y - half_size),
        (x + apparent_width, y - half_size),
        (x + apparent_width, y + half_size),
        (x - apparent_width, y + half_size)
    ]
    
    temp_img = Image.new('RGBA', (CANVAS_SIZE, CANVAS_SIZE), (255, 255, 255, 0))
    temp_draw = ImageDraw.Draw(temp_img)
    
    # Black border
    temp_draw.polygon(corners, fill=(BLACK[0], BLACK[1], BLACK[2], opacity))
    
    if apparent_width > BORDER_WIDTH:
        # Transparent gap
        gap_corners = [
            (x - apparent_width + BORDER_WIDTH, y - half_size + BORDER_WIDTH),
            (x + apparent_width - BORDER_WIDTH, y - half_size + BORDER_WIDTH),
            (x + apparent_width - BORDER_WIDTH, y + half_size - BORDER_WIDTH),
            (x - apparent_width + BORDER_WIDTH, y + half_size - BORDER_WIDTH)
        ]
        temp_draw.polygon(gap_corners, fill=(255, 255, 255, 0))
        
        # Green center
        if apparent_width > BORDER_WIDTH + 8:
            inner_size = size - 2 * BORDER_WIDTH
            green_border = inner_size * 0.15
            green_inset = BORDER_WIDTH + green_border
            green_width = apparent_width - green_inset if apparent_width > green_inset else 0
            
            if green_width > 0:
                green_corners = [
                    (x - green_width, y - half_size + green_inset),
                    (x + green_width, y - half_size + green_inset),
                    (x + green_width, y + half_size - green_inset),
                    (x - green_width, y + half_size - green_inset)
                ]
                temp_draw.polygon(green_corners, fill=GREEN)
    
    return temp_img

def create_frame(frame_num):
    """Create a single frame of the animation"""
    img = Image.new('RGBA', (CANVAS_SIZE, CANVAS_SIZE), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    progress = frame_num / FRAME_COUNT
    
    if progress <= 0.1:  # Initial state - static square
        draw_static_square(draw, CENTER, CENTER, SQUARE_SIZE)
        
    elif progress <= 0.2:  # Square rotates to edge-on and disappears
        t = (progress - 0.1) / 0.1
        rotation = t * 90  # Rotate to edge-on
        
        rotating_img = draw_rotating_square(draw, CENTER, CENTER, SQUARE_SIZE, rotation, 255)
        if rotating_img:
            img = Image.alpha_composite(img, rotating_img)
            
    elif progress <= 0.25:  # Flag emerges from edge-on position
        t = (progress - 0.2) / 0.05
        # Start from 90° (edge-on) and rotate to 0° (facing us)
        rotation = 90 * (1 - t)
        
        flag_img, _ = draw_3d_flag(CENTER, CENTER, FLAG_SIZE, rotation, int(255 * t))
        if flag_img:
            img = Image.alpha_composite(img, flag_img)
            
    elif progress <= 0.5:  # Steady rotation in one direction
        t = (progress - 0.25) / 0.25
        # Continue from 0° and make 2 full rotations
        rotation = t * 720
        
        flag_img, _ = draw_3d_flag(CENTER, CENTER, FLAG_SIZE, rotation, 255)
        if flag_img:
            img = Image.alpha_composite(img, flag_img)
            
    elif progress <= 0.65:  # Acceleration - FASTER
        t = (progress - 0.5) / 0.15
        # Stronger quadratic acceleration
        rotation = 720 + t * t * 2160  # Double the acceleration
        
        flag_img, _ = draw_3d_flag(CENTER, CENTER, FLAG_SIZE, rotation, 255)
        if flag_img:
            img = Image.alpha_composite(img, flag_img)
            
    elif progress <= 0.8:  # Blur phase - MUCH faster rotation
        t = (progress - 0.65) / 0.15
        base_rotation = 2880 + t * 5400  # Much faster
        
        # Motion blur with many overlapping flags
        blur_flags = []
        num_blur_flags = 32
        for i in range(num_blur_flags):
            angle = base_rotation + (360 / num_blur_flags) * i
            opacity = int(30 + (1 - i/num_blur_flags) * 30)  # Intentional low opacity for blur
            
            flag_img, z_val = draw_3d_flag(CENTER, CENTER, FLAG_SIZE, angle, opacity)
            if flag_img:
                blur_flags.append((flag_img, z_val))
        
        # Sort by Z (back to front)
        blur_flags.sort(key=lambda x: x[1])
        for flag_img, _ in blur_flags:
            img = Image.alpha_composite(img, flag_img)
            
    elif progress <= 0.9:  # Strobe effect - appears to reverse
        t = (progress - 0.8) / 0.1
        # Wagon wheel effect - slow backward rotation
        base_rotation = -t * 45
        
        # 8 flags appearing
        flags_with_depth = []
        for i in range(8):
            angle = base_rotation + i * 45
            flag_img, z_val = draw_3d_flag(CENTER, CENTER, FLAG_SIZE, angle, 200)  # Intentional lower opacity
            if flag_img:
                flags_with_depth.append((flag_img, z_val))
        
        # Sort by depth (back to front)
        flags_with_depth.sort(key=lambda x: x[1])
        for flag_img, _ in flags_with_depth:
            img = Image.alpha_composite(img, flag_img)
            
    else:  # Final state - 8 spokes with vertical line
        # Final 8-spoke pattern - collect ALL halves from ALL flags
        final_angles = [0, 45, 90, 135, 180, 225, 270, 315]
        
        # Enable debug for final frame
        debug_mode = False  # Set to True to see debug colors
        
        # Collect ALL halves with their Z-depths
        all_halves = []
        
        for angle in final_angles:
            # Get left half
            left_img, left_z = draw_half_flag(CENTER, CENTER, FLAG_SIZE, angle, 
                                             is_left_half=True, opacity=255, debug=debug_mode)
            all_halves.append((left_img, left_z, angle, "L"))
            
            # Get right half
            right_img, right_z = draw_half_flag(CENTER, CENTER, FLAG_SIZE, angle, 
                                               is_left_half=False, opacity=255, debug=debug_mode)
            all_halves.append((right_img, right_z, angle, "R"))
        
        # Sort ALL halves by Z-depth (back to front)
        all_halves.sort(key=lambda x: x[1])
        
        # Draw them all in order from back to front with FULL opacity
        for half_img, z_val, angle, side in all_halves:
            img = Image.alpha_composite(img, half_img)
        
        # NOW draw the rectangle AFTER everything else is rendered
        # Create a fresh draw object for the composited image
        draw = ImageDraw.Draw(img)
        
        # Calculate the actual visual height using the same 3D transform as facing panels
        viewing_angle_rad = math.radians(VIEWING_ANGLE)
        half_height = FLAG_SIZE // 2
        
        # For a panel facing us (0° rotation), the corners are at:
        # Top: (0, -half_height, 0) -> screen_y = center_y + (-half_height) * cos(45°) = center_y - half_height * 0.707
        # Bottom: (0, half_height, 0) -> screen_y = center_y + half_height * cos(45°) = center_y + half_height * 0.707
        
        # So the actual visual height from top to bottom is:
        visual_half_height = half_height * math.cos(viewing_angle_rad)
        
        # But wait, that's the compressed height. For edge-on, we want the FULL panel height
        # The edge-on line should extend to the same Y coordinates as the facing panel corners
        top_y = CENTER - visual_half_height
        bottom_y = CENTER + visual_half_height
        actual_visual_height = visual_half_height
        
        # Draw the vertical line to match the exact coordinates of the facing panels
        line_thickness = 6 * SCALE_FACTOR
        draw.line(
            [(CENTER, top_y),
             (CENTER, bottom_y)],
            fill=BLACK[:3],
            width=line_thickness
        )
        
        # Draw green center line
        green_range = (bottom_y - top_y) * 0.7  # 70% of total height
        green_center_top = CENTER - green_range / 2
        green_center_bottom = CENTER + green_range / 2
        green_thickness = 3 * SCALE_FACTOR
        draw.line(
            [(CENTER, green_center_top),
             (CENTER, green_center_bottom)],
            fill=GREEN[:3],
            width=green_thickness
        )
        print(f"Drew vertical line from ({CENTER}, {top_y}) to ({CENTER}, {bottom_y}), thickness={line_thickness}")
        
        # Convert and add this final frame
        final_frame = img.convert('RGB')
        frames.append(final_frame)
        
        # Hold this frame longer - add extra copies
        for _ in range(20):
            frames.append(final_frame)
    
    return img.convert('RGB')

def generate_gif():
    """Generate the complete animation as a GIF"""
    global frames  # Make frames accessible to final state
    frames = []
    
    print("Generating frames...")
    for i in range(FRAME_COUNT):
        if i % 10 == 0:
            print(f"Frame {i}/{FRAME_COUNT}")
        frame = create_frame(i)
        
        # Add all frames normally
        frames.append(frame)
    
    # Hold final frame
    for _ in range(10):
        frames.append(frames[-1])
    
    print("Saving GIF...")
    frames[0].save(
        'hyperplexity_animation.gif',
        save_all=True,
        append_images=frames[1:],
        duration=80,
        loop=0
    )
    print("Animation saved as 'hyperplexity_animation.gif'")

if __name__ == "__main__":
    generate_gif()