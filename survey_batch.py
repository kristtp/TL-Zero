
import subprocess
import time
import os
import sys

SERIAL = '10.0.5.212:42331'

def run_adb(cmd):
    full_cmd = f'adb -s {SERIAL} {cmd}'
    res = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    return res.stdout.strip()

def jump_to(x, y):
    # Tap coordinate bar to open dialog
    run_adb('shell input tap 440 120')
    time.sleep(0.4)
    # Tap X box
    run_adb('shell input tap 380 215')
    time.sleep(0.3)
    # Clear and enter X
    for _ in range(8):
        run_adb('shell input keyevent 67')
    run_adb(f'shell input text {x}')
    time.sleep(0.3)
    # Tap Y box
    run_adb('shell input tap 560 215')
    time.sleep(0.3)
    # Clear and enter Y
    for _ in range(8):
        run_adb('shell input keyevent 67')
    run_adb(f'shell input text {y}')
    time.sleep(0.3)
    # Tap Go
    run_adb('shell input tap 730 215')
    time.sleep(1.8)

def capture(local_path):
    remote = '/sdcard/survey_tmp.png'
    run_adb(f'shell screencap -p {remote}')
    run_adb(f'pull {remote} {local_path}')
    run_adb(f'shell rm {remote}')

os.makedirs('analysis-assets/survey-run', exist_ok=True)

targets = [
    ('Goddess_201003_NE', 2150, 2150),
    ('Goddess_201002_E', 2600, 800),
    ('Goddess_201001_SE', 2500, -900),
    ('Goddess_211003_SE_Far', 2150, -2150),
    ('Goddess_211002_S', 800, -2600)
]

for idx, (label, tx, ty) in enumerate(targets, 1):
    print(f'[{idx}/5] Jumping to {label} at X:{tx} Y:{ty}...')
    jump_to(tx, ty)
    out_file = f'analysis-assets/survey-run/{idx:02d}_{label}_{tx}_{ty}.png'
    capture(out_file)
    print(f'  Captured {out_file}')

print('Batch 1 complete!')
