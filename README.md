# TL-Zero: SEA 150 Atlas & Tactical Mapping

Interactive map and tactical survey engine for Tavern & Legend SEA 150.

## Live Viewer
Visit the live interactive map:
**[SEA 150 Atlas](https://kristtp.github.io/TL-Zero/)**

## Features
- **1,647 Decoded Gathering Resource Nodes**: Extracted directly from APK client geometry (`GatheringCircleConfig`).
- **17 Goddess & Wonder Landmarks**: Exact static site coordinates with region boundaries.
- **Dynamic Live Turtle Trap Overlay**: Real-time garrison positioning and tracking.
- **Interactive Layers & Controls**:
  - Distance calculator to nearest Goddesses and resource fields.
  - Coordinate search and inspector.
  - Seamless toggle between Synthetic Vector Map and Live Stitched Satellite Map.
  - Real-time targeting crosshair with live X, Y coordinate tracking.
- **Autonomous Survey Engine (`auto_stitch_survey.py`)**:
  - Automated mathematical boustrophedon camera sweeping via ADB.
  - Clean ocean window cropping ($420 \times 1100$ px).
  - Live coordinate auto-detection directly from the screen with GPU-accelerated EasyOCR.
  - 4.0 px/unit master canvas rendering with real-time browser preview updates.
