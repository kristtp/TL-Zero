"""
Auto-Crop and Stitch Survey Engine for Tavern & Legend SEA 150.
Executes mathematical step movement, clean cropping, and deterministic stitching
onto a 7200 x 7200 master canvas along a snake (boustrophedon) trajectory.
"""

import os
import sys
import time
import json
import math
import re
import argparse
import subprocess
import threading
import cv2
import numpy as np

SERIAL = '10.0.5.212:42331'

# Screen & Crop Geometry:
# Screen: 1080 x 2280
# Screen dead center: (540, 1140)
SCREEN_CX = 540
SCREEN_CY = 1140

# Clean ocean crop window (excluding all sidebars, status bars, and docks):
# X: 360 to 780 (width 420px), Y: 450 to 1550 (height 1100px)
CROP_X1, CROP_X2 = 360, 780
CROP_Y1, CROP_Y2 = 450, 1550
CROP_W = CROP_X2 - CROP_X1
CROP_H = CROP_Y2 - CROP_Y1

# Relative offset of crop top-left from screen dead center (540, 1140):
# X offset: 360 - 540 = -180px
# Y offset: 450 - 1140 = -690px
CROP_OFFSET_X = CROP_X1 - SCREEN_CX
CROP_OFFSET_Y = CROP_Y1 - SCREEN_CY

# Map & Canvas Dimensions:
# Scale: 4.0 pixels per map unit everywhere
SCALE = 4.0
MAP_SIZE = 7200

# Master 28,800 canvas (full un-downsampled resolution):
MASTER_DIM = int(MAP_SIZE * SCALE)  # 28,800
MASTER_CENTER = MASTER_DIM // 2     # 14,400

# Overview 7,200 canvas (for default zoomed-out screen fit in sea150-viewer):
OVERVIEW_DIM = MAP_SIZE             # 7,200
OVERVIEW_CENTER = OVERVIEW_DIM // 2 # 3,600

# Sea background color: BGR (108, 94, 12)
SEA_COLOR = (108, 94, 12)

# File Paths
OUTPUT_DIR = 'analysis-assets/survey-run/stitch_tiles'
CANVAS_FILE = 'analysis-assets/survey-run/stitched_map.png'
MASTER_FILE = 'analysis-assets/survey-run/stitched_map_28k.jpg'
PREVIEW_FILE = 'analysis-assets/survey-run/stitched_map_preview.jpg'
STATE_FILE = 'analysis-assets/survey-run/survey_state.json'

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Global EasyOCR reader cache (with automatic GPU acceleration)
_ocr_reader = None

def get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        import torch
        use_gpu = torch.cuda.is_available()
        _ocr_reader = easyocr.Reader(['en'], gpu=use_gpu)
    return _ocr_reader

# Persistent coordinate bar bounding box on full 1080x2280 screenshot:
# Located at lower-center: Y in [1700, 1950], X in [250, 750]
COORD_BAR_Y1, COORD_BAR_Y2 = 1700, 1950
COORD_BAR_X1, COORD_BAR_X2 = 250, 750

def parse_coordinates_from_frame(full_bgr):
    """
    Directly extracts and parses the persistent (X, Y) coordinates
    from the lower-center screen zone without tapping or interacting with the screen.
    Returns (map_x, map_y, canvas_cx, canvas_cy) or None if not found.
    """
    coord_zone = full_bgr[COORD_BAR_Y1:COORD_BAR_Y2, COORD_BAR_X1:COORD_BAR_X2]
    reader = get_ocr_reader()
    results = reader.readtext(coord_zone)

    pattern = re.compile(r'X\s*[:.;,]?\s*(-?\d+).*?Y\s*[:.;,]?\s*(-?\d+)', re.IGNORECASE)
    for r in results:
        text = r[1]
        m = pattern.search(text)
        if m:
            gx = int(m.group(1))
            gy = int(m.group(2))
            canvas_cx = CANVAS_CENTER_X + gx
            canvas_cy = CANVAS_CENTER_Y - gy
            return gx, gy, canvas_cx, canvas_cy

    return None

def capture_full_and_crop(save_tile_path=None):
    """
    Captures full frame via adb exec-out directly into memory.
    Extracts:
      1) The clean ocean crop window (X: 360..780, Y: 450..1550)
      2) The live persistent coordinates from the lower-center bar
    Returns: (crop_bgr, coord_info)
    """
    cmd = ['adb', '-s', SERIAL, 'exec-out', 'screencap']
    res = subprocess.run(cmd, capture_output=True)
    raw_data = res.stdout

    if len(raw_data) > 16:
        w = int.from_bytes(raw_data[0:4], 'little')
        h = int.from_bytes(raw_data[4:8], 'little')
        raw_pixels = np.frombuffer(raw_data[16:], dtype=np.uint8)
        if len(raw_pixels) == w * h * 4:
            rgba = raw_pixels.reshape((h, w, 4))
            full_bgr = rgba[:, :, [2, 1, 0]].copy()
            crop_bgr = full_bgr[CROP_Y1:CROP_Y2, CROP_X1:CROP_X2].copy()
            if save_tile_path:
                cv2.imwrite(save_tile_path, crop_bgr)
            coord_info = parse_coordinates_from_frame(full_bgr)
            return crop_bgr, coord_info

    # Fallback to PNG pipe if needed
    cmd_fallback = ['adb', '-s', SERIAL, 'exec-out', 'screencap', '-p']
    res_fallback = subprocess.run(cmd_fallback, capture_output=True)
    full_bgr = cv2.imdecode(np.frombuffer(res_fallback.stdout, np.uint8), cv2.IMREAD_COLOR)
    crop_bgr = full_bgr[CROP_Y1:CROP_Y2, CROP_X1:CROP_X2].copy()
    if save_tile_path:
        cv2.imwrite(save_tile_path, crop_bgr)
    coord_info = parse_coordinates_from_frame(full_bgr)
    return crop_bgr, coord_info

_save_thread = None

def run_adb(cmd_list):
    """Executes adb command."""
    full_cmd = ['adb', '-s', SERIAL] + cmd_list
    res = subprocess.run(full_cmd, capture_output=True, text=True)
    return res.stdout.strip()

def capture_crop_fast(save_tile_path=None):
    """
    Direct in-memory framebuffer capture via pipe.
    Decodes directly to NumPy array without saving to phone storage.
    """
    cmd = ['adb', '-s', SERIAL, 'exec-out', 'screencap']
    res = subprocess.run(cmd, capture_output=True)
    raw_data = res.stdout
    if len(raw_data) > 16:
        w = int.from_bytes(raw_data[0:4], 'little')
        h = int.from_bytes(raw_data[4:8], 'little')
        raw_pixels = np.frombuffer(raw_data[16:], dtype=np.uint8)
        if len(raw_pixels) == w * h * 4:
            rgba = raw_pixels.reshape((h, w, 4))
            crop_bgr = rgba[CROP_Y1:CROP_Y2, CROP_X1:CROP_X2, [2, 1, 0]].copy()
            if save_tile_path:
                cv2.imwrite(save_tile_path, crop_bgr)
            return crop_bgr

    # Fallback to PNG pipe
    cmd_fallback = ['adb', '-s', SERIAL, 'exec-out', 'screencap', '-p']
    res_fallback = subprocess.run(cmd_fallback, capture_output=True)
    im = cv2.imdecode(np.frombuffer(res_fallback.stdout, np.uint8), cv2.IMREAD_COLOR)
    crop_bgr = im[CROP_Y1:CROP_Y2, CROP_X1:CROP_X2].copy()
    if save_tile_path:
        cv2.imwrite(save_tile_path, crop_bgr)
    return crop_bgr

def drag_step_fast(direction='South', swipe_px=800, duration_ms=250, settle_s=0.25):
    """
    Accelerated pure-viewport drag:
    Shortened touch duration to 250ms with 0.25s settle time (~0.5s total).
    PHYSICAL TOUCH MAPPING:
    - Moving Camera South (-Y): Drag fingers UPWARDS
    - Moving Camera North (+Y): Drag fingers DOWNWARDS
    - Moving Camera West  (-X): Drag fingers RIGHTWARDS
    - Moving Camera East  (+X): Drag fingers LEFTWARDS
    """
    cx = SCREEN_CX
    cy = SCREEN_CY
    d = int(swipe_px)

    if direction == 'South':
        y_start = cy + (d // 2)
        y_end = cy - (d // 2)
        run_adb(['shell', 'input', 'swipe', str(cx), str(y_start), str(cx), str(y_end), str(duration_ms)])
    elif direction == 'North':
        y_start = cy - (d // 2)
        y_end = cy + (d // 2)
        run_adb(['shell', 'input', 'swipe', str(cx), str(y_start), str(cx), str(y_end), str(duration_ms)])
    elif direction == 'West':
        x_start = cx - (d // 2)
        x_end = cx + (d // 2)
        run_adb(['shell', 'input', 'swipe', str(x_start), str(cy), str(x_end), str(cy), str(duration_ms)])
    elif direction == 'East':
        x_start = cx + (d // 2)
        x_end = cx - (d // 2)
        run_adb(['shell', 'input', 'swipe', str(x_start), str(cy), str(x_end), str(cy), str(duration_ms)])

    time.sleep(settle_s)

def stitch_tile(canvas, crop, pos_x, pos_y):
    """Pastes cropped tile onto a canvas at exact coordinate in < 2ms."""
    th, tw = crop.shape[:2]
    ch, cw = canvas.shape[:2]

    x1 = max(0, min(cw, pos_x))
    y1 = max(0, min(ch, pos_y))
    x2 = max(0, min(cw, pos_x + tw))
    y2 = max(0, min(ch, pos_y + th))

    cx1 = x1 - pos_x
    cy1 = y1 - pos_y
    cx2 = cx1 + (x2 - x1)
    cy2 = cy1 + (y2 - y1)

    if x2 > x1 and y2 > y1:
        canvas[y1:y2, x1:x2] = crop[cy1:cy2, cx1:cx2]

def stitch_both(master_canvas, overview_canvas, crop, gx, gy):
    """
    Stitches crop onto:
    1) Master Canvas at 4.0 px/unit everywhere (28,800 x 28,800) in full un-downsampled native resolution.
    2) Overview Canvas at 1.0 px/unit (7,200 x 7,200) for real-time sea150-viewer screen fit.
    """
    # 1. Master 28,800 Canvas (4.0 px/unit)
    cx_28k = int(round(MASTER_CENTER + gx * SCALE))
    cy_28k = int(round(MASTER_CENTER - gy * SCALE))
    px_28k = cx_28k + CROP_OFFSET_X
    py_28k = cy_28k + CROP_OFFSET_Y
    stitch_tile(master_canvas, crop, px_28k, py_28k)

    # 2. Overview 7,200 Canvas (1.0 px/unit)
    ov_w = int(round(CROP_W / SCALE))   # 105 px
    ov_h = int(round(CROP_H / SCALE))   # 275 px
    crop_ov = cv2.resize(crop, (ov_w, ov_h), interpolation=cv2.INTER_AREA)

    cx_ov = int(round(OVERVIEW_CENTER + gx))
    cy_ov = int(round(OVERVIEW_CENTER - gy))
    px_ov = cx_ov + int(round(CROP_OFFSET_X / SCALE))
    py_ov = cy_ov + int(round(CROP_OFFSET_Y / SCALE))
    stitch_tile(overview_canvas, crop_ov, px_ov, py_ov)

    return (px_28k, py_28k), (px_ov, py_ov)

def async_save_canvas(overview_canvas, master_canvas=None, save_master=False):
    """Saves overview canvas asynchronously to prevent loop blocking."""
    global _save_thread
    overview_snapshot = overview_canvas.copy()
    master_snapshot = master_canvas.copy() if (master_canvas is not None and save_master) else None

    def _worker():
        cv2.imwrite(CANVAS_FILE, overview_snapshot)
        preview = cv2.resize(overview_snapshot, (1200, 1200))
        cv2.imwrite(PREVIEW_FILE, preview)
        if master_snapshot is not None:
            cv2.imwrite(MASTER_FILE, master_snapshot, [cv2.IMWRITE_JPEG_QUALITY, 85])

    if _save_thread is not None and _save_thread.is_alive():
        _save_thread.join(timeout=0.05)

    _save_thread = threading.Thread(target=_worker, daemon=True)
    _save_thread.start()

def get_or_create_canvases():
    """Loads or creates both master 28,800 canvas and 7,200 overview canvas."""
    # Overview 7,200 canvas
    if os.path.exists(CANVAS_FILE):
        overview = cv2.imread(CANVAS_FILE)
        if overview is None or overview.shape != (OVERVIEW_DIM, OVERVIEW_DIM, 3):
            overview = np.zeros((OVERVIEW_DIM, OVERVIEW_DIM, 3), dtype=np.uint8)
            overview[:] = SEA_COLOR
    else:
        overview = np.zeros((OVERVIEW_DIM, OVERVIEW_DIM, 3), dtype=np.uint8)
        overview[:] = SEA_COLOR

    # Master 28,800 canvas
    if os.path.exists(MASTER_FILE):
        master = cv2.imread(MASTER_FILE)
        if master is None or master.shape != (MASTER_DIM, MASTER_DIM, 3):
            master = np.zeros((MASTER_DIM, MASTER_DIM, 3), dtype=np.uint8)
            master[:] = SEA_COLOR
    else:
        master = np.zeros((MASTER_DIM, MASTER_DIM, 3), dtype=np.uint8)
        master[:] = SEA_COLOR

    return master, overview

def save_state(state):
    """Saves survey progress state to disk so runs can resume seamlessly."""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def load_state():
    """Loads survey progress state if exists."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Warning] Could not load state file: {e}")
    return None

def run_survey(overlap=0.01, max_cols=None, max_steps=None, reset=False):
    """
    High-Speed Survey Loop:
    - Master Canvas: 28,800 x 28,800 px (4.0 px/unit everywhere in full native resolution)
    - Overview Canvas: 7,200 x 7,200 px (1.0 px/unit for sea150-viewer default screen fit)
    - Anchors every tile directly to live (X, Y) coordinates
    - Asynchronously flushes updates to disk
    """
    # Step sizes (pixels on master canvas)
    step_y_master = int(round(CROP_H * (1.0 - overlap)))
    step_x_master = int(round(CROP_W * (1.0 - overlap)))

    full_steps_per_col = math.ceil((MASTER_DIM - CROP_H) / step_y_master) + 1
    full_cols = math.ceil((MASTER_DIM - CROP_W) / step_x_master) + 1

    total_cols = max_cols if max_cols is not None else full_cols
    steps_per_col = max_steps if max_steps is not None else full_steps_per_col
    total_screenshots = total_cols * steps_per_col

    print("=" * 70)
    print("  SEA 150 HIGH-SPEED AUTO-CROP & STITCH SURVEY ENGINE")
    print("=" * 70)
    print(f"Master Canvas:          {MASTER_DIM} x {MASTER_DIM} px (4.0 px/unit everywhere)")
    print(f"Overview Canvas:        {OVERVIEW_DIM} x {OVERVIEW_DIM} px (Default Screen Fit)")
    print(f"Clean Crop Window:      {CROP_W} x {CROP_H} px (Native Resolution)")
    print(f"Active Session:         {steps_per_col} steps/col x {total_cols} cols = {total_screenshots:,} moves")
    print("=" * 70)

    master_canvas, overview_canvas = get_or_create_canvases()

    state = None if reset else load_state()
    if state:
        curr_gx = state.get('curr_gx', 0)
        curr_gy = state.get('curr_gy', 0)
        tile_idx = state['tile_idx']
        moving_south = state['moving_south']
        start_col = state.get('col', 0)
        start_step = state.get('step', 0)
        print(f"[Resume] Resuming from saved state:")
        print(f"         Tile: #{tile_idx}, Column: {start_col + 1}, Step: {start_step + 1}")
        print(f"         Game Position: X={curr_gx}, Y={curr_gy}, Direction: {'South' if moving_south else 'North'}")
    else:
        # Initial capture at current untouched screen location
        print(f"\n[Capture] Reading live coordinates from screen without tapping...")
        init_tile_path = os.path.join(OUTPUT_DIR, f'tile_000_crop.png')
        crop_init, coord_info = capture_full_and_crop(save_tile_path=init_tile_path)

        if coord_info is not None:
            curr_gx, curr_gy, _, _ = coord_info
            print(f"[Auto-Position] Anchored at live coordinates: X={curr_gx}, Y={curr_gy}")
        else:
            curr_gx, curr_gy = 3600, 3600
            print(f"[Default Position] Starting at Top-Right corner: X={curr_gx}, Y={curr_gy}")

        tile_idx = 0
        moving_south = True
        start_col = 0
        start_step = 0

        pos_28k, pos_ov = stitch_both(master_canvas, overview_canvas, crop_init, curr_gx, curr_gy)
        print(f"  [Tile {tile_idx:03d}] Stitched at 28k {pos_28k}, Overview {pos_ov}")

        async_save_canvas(overview_canvas, master_canvas, save_master=True)
        tile_idx += 1
        save_state({
            'curr_gx': curr_gx,
            'curr_gy': curr_gy,
            'tile_idx': tile_idx,
            'moving_south': moving_south,
            'col': 0,
            'step': 0
        })

    cols_to_run = total_cols
    for col_offset in range(cols_to_run):
        col = start_col + col_offset
        col_dir = "South (Top -> Bottom)" if moving_south else "North (Bottom -> Top)"
        print(f"\n--- Column {col + 1}/{start_col + cols_to_run}: Scanning {col_dir} ---")

        first_step_idx = (start_step + 1) if (col_offset == 0 and start_step > 0) else 1
        for step in range(first_step_idx, steps_per_col):
            t_step_start = time.time()
            dir_move = 'South' if moving_south else 'North'

            # 1. Accelerated drag move (~0.5s)
            drag_step_fast(dir_move, swipe_px=800, duration_ms=250, settle_s=0.25)

            # 2. Direct capture of frame, clean crop, and live coordinate readout
            tile_path = os.path.join(OUTPUT_DIR, f'tile_{tile_idx:03d}_crop.png')
            crop, coord_info = capture_full_and_crop(save_tile_path=tile_path)

            # 3. If live coordinates are read from the persistent bar, anchor directly!
            if coord_info is not None:
                curr_gx, curr_gy, _, _ = coord_info
                coord_tag = f"Anchored X={curr_gx}, Y={curr_gy}"
            else:
                # Fallback step displacement (~29.6 map units for 800px swipe)
                delta_map_y = 29.6
                curr_gy = curr_gy - delta_map_y if moving_south else curr_gy + delta_map_y
                coord_tag = f"Calculated Y={curr_gy:.1f}"

            # 4. In-memory stitch to both 28,800 master and 7,200 overview (< 2ms)
            pos_28k, pos_ov = stitch_both(master_canvas, overview_canvas, crop, curr_gx, curr_gy)

            # 5. Non-blocking asynchronous save (saves master every 5 steps)
            save_master = (tile_idx % 5 == 0)
            async_save_canvas(overview_canvas, master_canvas, save_master=save_master)

            t_step = time.time() - t_step_start
            print(f"  [Tile {tile_idx:03d}] Placed at Overview {pos_ov} [{coord_tag}, Elapsed: {t_step:.2f}s]")

            tile_idx += 1
            save_state({
                'curr_gx': curr_gx,
                'curr_gy': curr_gy,
                'tile_idx': tile_idx,
                'moving_south': moving_south,
                'col': col,
                'step': step
            })

        start_step = 0

        if col_offset < cols_to_run - 1:
            print(f"\n  >>> Shifting West to Next Column by 400px swipe...")
            drag_step_fast('West', swipe_px=400, duration_ms=250, settle_s=0.25)

            tile_path = os.path.join(OUTPUT_DIR, f'tile_{tile_idx:03d}_crop.png')
            crop, coord_info = capture_full_and_crop(save_tile_path=tile_path)

            if coord_info is not None:
                curr_gx, curr_gy, _, _ = coord_info
                shift_tag = f"Anchored X={curr_gx}, Y={curr_gy}"
            else:
                delta_map_x = 15.0
                curr_gx = curr_gx - delta_map_x
                shift_tag = f"Calculated X={curr_gx:.1f}"

            pos_28k, pos_ov = stitch_both(master_canvas, overview_canvas, crop, curr_gx, curr_gy)
            print(f"  [Tile {tile_idx:03d}] Shift Entry Placed at Overview {pos_ov} [{shift_tag}]")

            async_save_canvas(overview_canvas, master_canvas, save_master=True)
            tile_idx += 1

            moving_south = not moving_south
            save_state({
                'curr_gx': curr_gx,
                'curr_gy': curr_gy,
                'tile_idx': tile_idx,
                'moving_south': moving_south,
                'col': col + 1,
                'step': 0
            })

    # Wait for final background save to complete
    if _save_thread is not None and _save_thread.is_alive():
        _save_thread.join()

    # Final guaranteed sync writes
    cv2.imwrite(CANVAS_FILE, overview_canvas)
    cv2.imwrite(PREVIEW_FILE, cv2.resize(overview_canvas, (1200, 1200)))
    cv2.imwrite(MASTER_FILE, master_canvas, [cv2.IMWRITE_JPEG_QUALITY, 85])

    print("\n" + "=" * 70)
    print("  SURVEY COMPLETE!")
    print(f"  Overview Canvas Saved:  {CANVAS_FILE} (7200x7200, Default Screen Fit)")
    print(f"  Master Canvas Saved:    {MASTER_FILE} (28800x28800, 4.0 px/unit everywhere)")
    print(f"  Total Tiles Stitched:   {tile_idx}")
    print("=" * 70)
    print("=" * 70)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="High-speed mathematical crop & stitch for SEA 150.")
    parser.add_argument('--cols', type=int, default=None, help='Number of columns to scan')
    parser.add_argument('--steps', type=int, default=None, help='Steps per column')
    parser.add_argument('--overlap', type=float, default=0.01, help='Overlap ratio between adjacent crops (default: 0.01 = 1 percent)')
    parser.add_argument('--reset', action='store_true', help='Reset state and canvas to start fresh from top-right')
    args = parser.parse_args()

    run_survey(overlap=args.overlap, max_cols=args.cols, max_steps=args.steps, reset=args.reset)

