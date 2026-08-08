# LYRA Agent

An AI-powered phone-control assistant that combines a custom UI perception model with an agentic action execution framework.

Takes user commands → routes questions to LLMs (such as Grok), and resolves screen actions through:
**Live Screenshot → Custom Perception CNN (LyraNet) → Bounding Box/Coordinate Extraction → ADB Gestures → Verification & Text Response**

---

## 🌟 Key Features

- **Hybrid Brain & Body**: Uses custom vision models for UI element perception combined with a rich agentic tool-use environment.
- **Custom UI Vision Model (LyraNet)**: A CNN trained from scratch to detect UI interactive elements (buttons, inputs) and classify screen states.
- **Agent Action Loop**: Continuous perception-action cycle with verification steps to ensure actions achieve the user's target state.
- **Interactive Web & Dashboard**: Clean web frontend interface to view device status, run CLI commands, and view models.
- **Voice Assistant Integrated**: Support for voice command triggers and audio responses.

---

## 📂 Project Structure

* **[lyra/](file:///c:/Users/HP/Downloads/LYRA%20agent/LYRA%20agent/lyra)** — Core neural network and phone-control agent:
  * **[lyra/model/](file:///c:/Users/HP/Downloads/LYRA%20agent/LYRA%20agent/lyra/model)** — Custom CNN (LyraNet) trained from scratch for UI element detection and screen classification.
  * **[lyra/data/](file:///c:/Users/HP/Downloads/LYRA%20agent/LYRA%20agent/lyra/data)** — Dataset pipeline, custom PyTorch loaders, and image augmentations.
  * **[lyra/training/](file:///c:/Users/HP/Downloads/LYRA%20agent/LYRA%20agent/lyra/training)** — Trainer loops, evaluator hooks, and prediction visualizers.
  * **[lyra/inference/](file:///c:/Users/HP/Downloads/LYRA%20agent/LYRA%20agent/lyra/inference)** — Runs real-time CNN perception on live screenshots.
  * **[lyra/phone/](file:///c:/Users/HP/Downloads/LYRA%20agent/LYRA%20agent/lyra/phone)** — Low-level ADB controllers, screen captures, and accessibility dump parsers.
  * **[lyra/agent/](file:///c:/Users/HP/Downloads/LYRA%20agent/LYRA%20agent/lyra/agent)** — Planning loops, command router, verification checks, and primitives.
  * **[lyra/assistant/](file:///c:/Users/HP/Downloads/LYRA%20agent/LYRA%20agent/lyra/assistant)** — Grok/LLM api adapters for text responses.
* **[android-agent/](file:///c:/Users/HP/Downloads/LYRA%20agent/LYRA%20agent/android-agent)** — The underlying full-featured device-control framework, dashboard server, and companion app.
* **[tools/](file:///c:/Users/HP/Downloads/LYRA%20agent/LYRA%20agent/tools)** — Diagnostic scripts, voice GUI, evaluation tools, and local web servers.
* **[web/](file:///c:/Users/HP/Downloads/LYRA%20agent/LYRA%20agent/web)** — Simple web UI interface to control the agent.

---

## 🚀 Getting Started

### Prerequisites
1. **Python 3.10+** installed.
2. **Android SDK Platform Tools (ADB)** installed and added to your system's `PATH`.
3. An Android phone connected with **USB Debugging enabled** (run `adb devices` to verify connection).

### Installation
1. Install core dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. *(Optional)* For voice assistant features:
   ```bash
   pip install -r requirements-voice.txt
   ```
3. Set up environment file:
   * Copy `.env.example` to `.env`.
   * Open `.env` and fill in your API keys (e.g., `GROK_API_KEY`).

### Run the Agent
To start the CLI interface:
```bash
python tools/lyra_cli.py
```
To run the local web server:
```bash
python tools/web_server.py
```
And view the interface at `http://localhost:5000` (or the configured port).

---

## 📋 Status & Progress

Please refer to **[checklist.md](file:///c:/Users/HP/Downloads/LYRA%20agent/LYRA%20agent/checklist.md)** for a detailed list of tasks, features completed, and what is coming next!
