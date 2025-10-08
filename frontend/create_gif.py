from PIL import Image, ImageEnhance
import numpy as np

# Load and resize image to 50%
img = Image.open('montage.png').convert('RGBA')
original_size = img.size
img = img.resize((original_size[0] // 2, original_size[1] // 2), Image.LANCZOS)
width, height = img.size

print(f"Image size: {width}x{height}")

# Composite onto white background
img_array = np.array(img)
white_bg = np.ones((height, width, 3), dtype=np.uint8) * 255
alpha_normalized = img_array[:, :, 3:4] / 255.0
composited = (img_array[:, :, :3] * alpha_normalized + white_bg * (1 - alpha_normalized)).astype(np.uint8)

# Sharpen
base_img = Image.fromarray(composited, 'RGB')
sharpener = ImageEnhance.Sharpness(base_img)
base_img = sharpener.enhance(2.0)
base_composited = np.array(base_img)

# Find the 4 sections by dividing height (user said first 3 are equal, last is ~60% larger)
# Total = 3x + 1.5x = 4.5x, so x = height/4.5
section_height = int(height / 4.5)
sections = [
    (0, section_height),
    (section_height, 2 * section_height),
    (2 * section_height, 3 * section_height),
    (3 * section_height - 50, height)  # Move up 50 pixels to cover text at top
]

print("Sections:")
for i, (start, end) in enumerate(sections):
    print(f"  Panel {i+1}: rows {start}-{end}")

# Create frames
frames = []
frames_per_transition = 30  # More frames for smoother transitions
hold_frames = 10  # More hold frames
fade_level = 0.75  # How faded the muted panels are (75% faded to white for more dramatic effect)

print("\nCreating frames...")

# Panel 1 is always fully visible, panels 2-4 fade in sequentially
for panel_idx in range(4):
    print(f"Panel {panel_idx + 1}:")

    # Fade-in transition (skip for panel 0 which starts visible)
    if panel_idx == 0:
        # First panel starts fully visible, just show it
        composited = base_composited.copy()

        # Fade panels 2, 3, 4
        for p in range(1, 4):
            start, end = sections[p]
            blend = fade_level
            composited[start:end] = (composited[start:end] * (1 - blend) + 255 * blend).astype(np.uint8)

        # Hold for full duration
        for _ in range(frames_per_transition + hold_frames):
            frames.append(Image.fromarray(composited.copy(), 'RGB'))
    else:
        # Fade-in transition for panels 2, 3, 4
        for frame_idx in range(frames_per_transition):
            t = frame_idx / frames_per_transition
            composited = base_composited.copy()

            # Apply fade to each panel
            for p in range(4):
                start, end = sections[p]

                if p == 0:
                    # Panel 1 always fully visible
                    pass
                elif p < panel_idx:
                    # Already revealed - full saturation
                    pass
                elif p == panel_idx:
                    # Currently fading in - more dramatic
                    blend = fade_level * (1 - t)  # Goes from fade_level to 0
                    composited[start:end] = (composited[start:end] * (1 - blend) + 255 * blend).astype(np.uint8)
                else:
                    # Not yet revealed - very muted
                    blend = fade_level
                    composited[start:end] = (composited[start:end] * (1 - blend) + 255 * blend).astype(np.uint8)

            frames.append(Image.fromarray(composited, 'RGB'))

        # Hold frames
        for _ in range(hold_frames):
            composited = base_composited.copy()

            for p in range(4):
                start, end = sections[p]

                if p == 0 or p <= panel_idx:
                    # Fully visible
                    pass
                else:
                    # Muted
                    blend = fade_level
                    composited[start:end] = (composited[start:end] * (1 - blend) + 255 * blend).astype(np.uint8)

            frames.append(Image.fromarray(composited, 'RGB'))

# Save as GIF
print(f"\nSaving GIF with {len(frames)} frames...")
frame_duration = 75  # 75ms × 30 frames = 2.25 seconds per transition
frames[0].save(
    'montage.gif',
    save_all=True,
    append_images=frames[1:],
    duration=frame_duration,
    loop=0,
    disposal=2
)
print("[SUCCESS] Created montage.gif")

# Save as MP4
print("\nCreating MP4...")
try:
    import cv2
    h, w = base_composited.shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    fps = 1000.0 / frame_duration  # Match GIF frame rate
    out = cv2.VideoWriter('montage.mp4', fourcc, fps, (w, h))

    for frame in frames:
        frame_bgr = cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR)
        out.write(frame_bgr)

    out.release()
    print("[SUCCESS] Created montage.mp4")
except ImportError:
    print("[WARNING] opencv-python not installed, skipping MP4")
