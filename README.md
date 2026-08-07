# LYRA Agent

AI phone-control assistant built from scratch.

Takes user commands → routes questions to Grok API, routes phone-actions through:
**screenshot → custom vision model → coordinate extraction → ADB tap/swipe → verification → text response**

## Project Status

See [checklist.md](checklist.md) for the current task status.

## Setup

1. Install Python dependencies: `pip install -r requirements.txt`
2. Install ADB Platform Tools and add to PATH
3. Connect Android phone with USB Debugging enabled
4. Copy `.env.example` to `.env` and add your Grok API key

## Architecture

- **lyra/model/** — Custom CNN (LyraNet) trained from scratch for UI element detection and screen-state classification
- **lyra/data/** — Dataset pipeline (PyTorch Dataset, preprocessing, augmentation)
- **lyra/training/** — Training loop, evaluation, visualization
- **lyra/inference/** — Run trained model on live screenshots
- **lyra/phone/** — ADB controller, screenshot capture, accessibility
- **lyra/agent/** — Command router, primitives, task definitions, agent loop
- **lyra/assistant/** — Grok API client, text response generation
