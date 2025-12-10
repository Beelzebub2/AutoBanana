import math
import time
import shutil
import os
import sys
import threading

# Global animation state
_animation_frame = 0
_animation_lock = threading.Lock()

def get_terminal_size():
    """Get the current terminal size."""
    try:
        size = shutil.get_terminal_size()
        return size.columns, size.lines
    except:
        return 120, 32

def center_text(text, width=None):
    """Center text based on terminal width."""
    if width is None:
        width, _ = get_terminal_size()
    lines = text.splitlines()
    centered = []
    for line in lines:
        # Strip ANSI codes for length calculation
        clean_line = strip_ansi(line)
        padding = max(0, (width - len(clean_line)) // 2)
        centered.append(" " * padding + line)
    return "\n".join(centered)

def strip_ansi(text):
    """Remove ANSI escape codes from text."""
    import re
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def scale_logo(text, max_width=None):
    """Scale logo to fit terminal width if needed."""
    if max_width is None:
        max_width, _ = get_terminal_size()
    max_width = max_width - 4  # Leave some margin
    
    lines = text.splitlines()
    max_line_len = max(len(strip_ansi(line)) for line in lines) if lines else 0
    
    if max_line_len <= max_width:
        return text
    
    # If logo is too wide, truncate lines
    scaled = []
    for line in lines:
        if len(strip_ansi(line)) > max_width:
            scaled.append(line[:max_width])
        else:
            scaled.append(line)
    return "\n".join(scaled)

def get_animation_frame():
    """Get current animation frame for synchronized animations."""
    global _animation_frame
    with _animation_lock:
        return _animation_frame

def advance_animation_frame():
    """Advance the animation frame counter."""
    global _animation_frame
    with _animation_lock:
        _animation_frame = (_animation_frame + 1) % 360

def fire(text, animate=True):
    '''Fire theme with animated flickering effect.'''
    frame = get_animation_frame() if animate else 0
    fade = ""
    green = 250
    lines = text.splitlines()
    
    for i, line in enumerate(lines):
        # Add flickering effect
        flicker = int(20 * math.sin(frame * 0.15 + i * 0.5)) if animate else 0
        g = max(0, min(255, green + flicker))
        r = 255
        fade += f"\033[38;2;{r};{g};0m{line}\033[0m\n"
        green = max(0, green - 25)
    
    return scale_logo(fade)

def ice(text, animate=True):
    '''Ice theme with shimmering frozen effect.'''
    frame = get_animation_frame() if animate else 0
    fade = ""
    blue = 255
    lines = text.splitlines()
    
    for i, line in enumerate(lines):
        # Add shimmer effect
        shimmer = int(30 * math.sin(frame * 0.1 + i * 0.3)) if animate else 0
        b = max(100, min(255, blue))
        g = max(0, min(255, blue - 100 + shimmer))
        fade += f"\033[38;2;{shimmer + 100};{g};{b}m{line}\033[0m\n"
        blue = max(100, blue - 20)
    
    return scale_logo(fade)

def pinkneon(text, animate=True):
    '''Pink neon theme with pulsing glow effect.'''
    frame = get_animation_frame() if animate else 0
    fade = ""
    lines = text.splitlines()
    
    for i, line in enumerate(lines):
        # Pulsing neon effect
        pulse = int(50 * math.sin(frame * 0.08 + i * 0.2)) if animate else 0
        blue = max(100, min(255, 255 - 20 * i + pulse))
        r = 255
        g = max(0, min(100, pulse + 50))
        fade += f"\033[38;2;{r};{g};{blue}m{line}\033[0m\n"
    
    return scale_logo(fade)

def rainbow(text, animate=True):
    '''Rainbow theme with cycling colors.'''
    frame = get_animation_frame() if animate else 0
    fade = ""
    lines = text.splitlines()
    
    for i, line in enumerate(lines):
        # Rainbow cycling
        hue = (frame * 2 + i * 30) % 360 if animate else (i * 30) % 360
        r, g, b = hsv_to_rgb(hue / 360, 1.0, 1.0)
        fade += f"\033[38;2;{r};{g};{b}m{line}\033[0m\n"
    
    return scale_logo(fade)

def matrix(text, animate=True):
    '''Matrix theme with digital rain effect.'''
    frame = get_animation_frame() if animate else 0
    fade = ""
    lines = text.splitlines()
    
    for i, line in enumerate(lines):
        # Matrix green with brightness variation
        brightness = int(50 * math.sin(frame * 0.2 + i * 0.8)) if animate else 0
        g = max(100, min(255, 200 + brightness))
        fade += f"\033[38;2;0;{g};0m{line}\033[0m\n"
    
    return scale_logo(fade)

def sunset(text, animate=True):
    '''Sunset theme with warm gradient animation.'''
    frame = get_animation_frame() if animate else 0
    fade = ""
    lines = text.splitlines()
    total_lines = len(lines)
    
    for i, line in enumerate(lines):
        # Sunset gradient from orange to purple
        progress = i / max(1, total_lines - 1)
        wave = int(20 * math.sin(frame * 0.1 + i * 0.3)) if animate else 0
        r = 255
        g = max(0, min(255, int(180 - progress * 150) + wave))
        b = max(0, min(255, int(50 + progress * 150) + wave))
        fade += f"\033[38;2;{r};{g};{b}m{line}\033[0m\n"
    
    return scale_logo(fade)

def hsv_to_rgb(h, s, v):
    """Convert HSV to RGB."""
    if s == 0.0:
        return int(v * 255), int(v * 255), int(v * 255)
    
    i = int(h * 6.0)
    f = (h * 6.0) - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    i = i % 6
    
    if i == 0: r, g, b = v, t, p
    elif i == 1: r, g, b = q, v, p
    elif i == 2: r, g, b = p, v, t
    elif i == 3: r, g, b = p, q, v
    elif i == 4: r, g, b = t, p, v
    elif i == 5: r, g, b = v, p, q
    
    return int(r * 255), int(g * 255), int(b * 255)

def default_theme(text, animate=False):
    return scale_logo(text)

# Animation helper functions
def create_progress_bar(progress, width=30, filled_char="█", empty_char="░", 
                        color_start=(0, 255, 100), color_end=(0, 100, 255)):
    """Create an animated progress bar."""
    filled = int(width * progress)
    empty = width - filled
    
    bar = ""
    for i in range(filled):
        # Gradient color for filled portion
        ratio = i / max(1, width)
        r = int(color_start[0] + (color_end[0] - color_start[0]) * ratio)
        g = int(color_start[1] + (color_end[1] - color_start[1]) * ratio)
        b = int(color_start[2] + (color_end[2] - color_start[2]) * ratio)
        bar += f"\033[38;2;{r};{g};{b}m{filled_char}\033[0m"
    
    bar += f"\033[38;2;100;100;100m{empty_char * empty}\033[0m"
    return bar

def create_spinner(frame, style="dots"):
    """Create an animated spinner."""
    spinners = {
        "dots": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
        "line": ["-", "\\", "|", "/"],
        "arrow": ["←", "↖", "↑", "↗", "→", "↘", "↓", "↙"],
        "bounce": ["⠁", "⠂", "⠄", "⠂"],
        "pulse": ["◐", "◓", "◑", "◒"],
        "star": ["✶", "✸", "✹", "✺", "✹", "✸"],
    }
    chars = spinners.get(style, spinners["dots"])
    return chars[frame % len(chars)]

def create_wave_text(text, frame, amplitude=2):
    """Create text with a wave animation effect."""
    result = ""
    for i, char in enumerate(text):
        offset = int(amplitude * math.sin(frame * 0.3 + i * 0.5))
        if offset > 0:
            result += f"\033[{offset}A{char}\033[{offset}B"
        elif offset < 0:
            result += f"\033[{-offset}B{char}\033[{-offset}A"
        else:
            result += char
    return result

def typing_effect(text, delay=0.02):
    """Generator for typing effect animation."""
    for i in range(len(text) + 1):
        yield text[:i]
        
def pulse_color(base_color, frame, intensity=50):
    """Create a pulsing color effect."""
    r, g, b = base_color
    pulse = int(intensity * math.sin(frame * 0.1))
    return (
        max(0, min(255, r + pulse)),
        max(0, min(255, g + pulse)),
        max(0, min(255, b + pulse))
    )