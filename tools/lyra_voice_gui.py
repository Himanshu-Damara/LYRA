"""
lyra_voice_gui.py — Modern Desktop GUI for LYRA Voice Assistant.

Features:
  - Interactive Voice Button (Mic Listening)
  - Text Input Field & History Log
  - Spoken Text-To-Speech (TTS) Voice Responses
  - Phone Action Task Triggering (Instagram, Camera, Photos, Likes, Home)
  - xAI Grok API Integration for Question Answering
"""

import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.lyra_voice_assistant import LyraVoiceAssistant


class LyraVoiceGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("LYRA — AI Phone & Voice Assistant")
        self.root.geometry("680 x 620")
        self.root.configure(bg="#1E1E2E")

        self.assistant = LyraVoiceAssistant()

        # Custom Styling
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TFrame", background="#1E1E2E")
        self.style.configure("TLabel", background="#1E1E2E", foreground="#D9E0EE", font=("Segoe UI", 10))
        self.style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"), foreground="#CBA6F7")
        self.style.configure("Status.TLabel", font=("Segoe UI", 10, "italic"), foreground="#89B4FA")

        self._build_ui()

        # Initial greeting in background thread
        threading.Thread(target=self.speak_and_log, args=("Hello! I am LYRA, your AI phone assistant. Tap the microphone or type below.",), daemon=True).start()

    def _build_ui(self):
        # Header Banner
        header_frame = ttk.Frame(self.root, padding=15)
        header_frame.pack(fill="x")

        title_lbl = ttk.Label(header_frame, text="🎙️ LYRA Voice Assistant", style="Header.TLabel")
        title_lbl.pack(anchor="w")

        sub_lbl = ttk.Label(header_frame, text="Autonomous Phone Actions & Grok AI Q&A Engine")
        sub_lbl.pack(anchor="w", pady=(2, 0))

        # Output Log Window
        log_frame = ttk.Frame(self.root, padding=(15, 0, 15, 10))
        log_frame.pack(fill="both", expand=True)

        self.log_area = scrolledtext.ScrolledText(
            log_frame,
            bg="#181825",
            fg="#CDD6F4",
            insertbackground="#CDD6F4",
            font=("Consolas", 10),
            wrap="word",
            relief="flat",
            bd=5
        )
        self.log_area.pack(fill="both", expand=True)

        # Status Line
        self.status_lbl = ttk.Label(self.root, text="Status: Ready", style="Status.TLabel", padding=(15, 5))
        self.status_lbl.pack(anchor="w")

        # Controls Frame (Mic Button & Input)
        control_frame = ttk.Frame(self.root, padding=15)
        control_frame.pack(fill="x")

        # Big Mic Button
        self.mic_btn = tk.Button(
            control_frame,
            text="🎙️ LISTEN (MIC)",
            bg="#89B4FA",
            fg="#11111B",
            font=("Segoe UI", 11, "bold"),
            activebackground="#B4BEFE",
            relief="flat",
            padx=15,
            pady=8,
            command=self.start_mic_listening
        )
        self.mic_btn.pack(side="left", padx=(0, 10))

        # Text Input Entry
        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(
            control_frame,
            textvariable=self.entry_var,
            bg="#313244",
            fg="#CDD6F4",
            insertbackground="#CDD6F4",
            font=("Segoe UI", 11),
            relief="flat",
            bd=5
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entry.bind("<Return>", lambda event: self.send_text_command())

        # Send Button
        send_btn = tk.Button(
            control_frame,
            text="SEND",
            bg="#A6E3A1",
            fg="#11111B",
            font=("Segoe UI", 10, "bold"),
            activebackground="#94E2D5",
            relief="flat",
            padx=15,
            pady=8,
            command=self.send_text_command
        )
        send_btn.pack(side="right")

    def append_log(self, sender: str, message: str):
        self.log_area.configure(state="normal")
        self.log_area.insert("end", f"[{sender}]: ", "sender")
        self.log_area.insert("end", f"{message}\n\n")
        self.log_area.see("end")
        self.log_area.configure(state="disabled")

    def speak_and_log(self, text: str):
        self.append_log("LYRA", text)
        self.assistant.voice.speak(text)

    def set_status(self, text: str):
        self.status_lbl.config(text=f"Status: {text}")

    def send_text_command(self):
        cmd = self.entry_var.get().strip()
        if not cmd:
            return
        self.entry_var.set("")
        self.append_log("YOU", cmd)

        threading.Thread(target=self._process_in_background, args=(cmd,), daemon=True).start()

    def start_mic_listening(self):
        self.mic_btn.config(state="disabled", bg="#F38BA8", text="🎙️ LISTENING...")
        self.set_status("Listening to microphone...")

        def _listen_worker():
            user_text = self.assistant.listener.listen(timeout=6.0)
            self.root.after(0, lambda: self.mic_btn.config(state="normal", bg="#89B4FA", text="🎙️ LISTEN (MIC)"))
            if user_text:
                self.append_log("YOU (Voice)", user_text)
                self._process_in_background(user_text)
            else:
                self.set_status("Ready")
                self.speak_and_log("I didn't hear anything. Try tapping the microphone again.")

        threading.Thread(target=_listen_worker, daemon=True).start()

    def _process_in_background(self, text: str):
        self.set_status(f"Processing '{text}'...")
        self.assistant._process_command(text)
        self.set_status("Ready")


def main():
    root = tk.Tk()
    app = LyraVoiceGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
