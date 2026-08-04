# Maya Playblast Tools

English | [中文](README_CN.md)

Maya animation playblast tool  
High-quality video output with H.264 / H.265 / AV1 encoders, quality presets, resolution control, and scene audio mixing.

Supported versions: Maya 2022 / 2023 / 2024

## Installation

### Drag-and-drop install (recommended)

1. Open Maya (2022 / 2023 / 2024)
2. Drag the `install.py` file from the project into the Maya viewport
3. Wait for the automatic installation to finish (internet connection required on first use to download FFmpeg)
4. The button appears next to the time slider immediately — no Maya restart needed

### Manual setup (optional)

If drag-and-drop does not work, add the `modules` directory to Maya's `MAYA_MODULE_PATH` environment variable, then restart Maya.

## Usage

### Basic controls

| Action | Function |
|---|---|
| Left-click the button | Save dialog opens, exports video with current settings |
| Right-click the button | Opens the output options menu |

### Output options (right-click menu)

| Option | Description |
|---|---|
| Auto Play | Play the video automatically after export |
| Sound | Mix in the audio loaded on the time slider (warns and exports silent video if no audio) |
| Container | Container format: MP4 / MKV / MOV |
| Video Codec | Video codec: H.264 / H.265 / AV1 (filtered by container) |
| Frame Format | Intermediate frame format: JPEG / PNG |
| Resolution | Resolution: presets / view size / render settings |
| Quality | Quality level: High / Medium / Low |
| Scale | Render scale: 25% / 50% / 75% / 100% |
| Preset | Preset profiles: apply, save, delete (current options are remembered) |

### Notes

- Temporary frame sequences are cleaned up automatically after export
- The save location is remembered and used as the default directory next time
- Audio comes from the audio loaded on the Maya time slider (Time Slider > Sound menu)
- The right-click menu stays open while adjusting multiple options; it closes only when clicking outside or choosing Playblast
