"""
lyra_voice_assistant.py — Intelligent Voice Assistant for Phone Control & Q&A.

Combines:
  1. Voice Input (Microphone SpeechRecognition with Text Input Fallback)
  2. Voice Output (Text-To-Speech via pyttsx3 / SAPI5)
  3. Phone Automation Engine (LYRA Agent Perception-Action Loop + ADB Control)
  4. Knowledge Q&A Engine (xAI Grok API Integration)
"""

import sys
import os
import time
import subprocess
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import speech & assistant dependencies
import pyttsx3
import speech_recognition as sr

from lyra.agent.router import classify_intent, resolve_task_from_input
from lyra.agent.agent_loop import AgentLoop
from lyra.agent.tasks import list_tasks
from lyra.assistant.grok_client import grok
from lyra.assistant.responder import Responder


class VoiceEngine:
    """Handles Text-To-Speech voice output."""

    def __init__(self):
        try:
            self.tts_engine = pyttsx3.init()
            self.tts_engine.setProperty('rate', 170)    # Natural speech speed
            self.tts_engine.setProperty('volume', 1.0)  # Max volume
            # Try to select female voice if available
            voices = self.tts_engine.getProperty('voices')
            for v in voices:
                if "female" in v.name.lower() or "zira" in v.name.lower():
                    self.tts_engine.setProperty('voice', v.id)
                    break
            self.use_pyttsx3 = True
        except Exception:
            self.use_pyttsx3 = False

    def speak(self, text: str):
        """Speaks the text out loud through speakers and prints to console."""
        print(f"\n  LYRA (Voice): \"{text}\"")

        if self.use_pyttsx3:
            try:
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
                return
            except Exception:
                pass

        # Fallback to PowerShell Speech Synthesizer
        try:
            clean_text = text.replace("'", "").replace('"', "")
            ps_cmd = f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{clean_text}')"
            subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True)
        except Exception:
            pass


class VoiceListener:
    """Handles Microphone Speech-To-Text input."""

    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300
        self.recognizer.pause_threshold = 0.8

    def listen(self, timeout: float = 5.0) -> Optional[str]:
        """Listens for voice input from the default microphone."""
        try:
            with sr.Microphone() as source:
                print("\n  [VOICE] Listening... Speak into your microphone now.")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=10.0)

            print("  [VOICE] Processing speech...")
            text = self.recognizer.recognize_google(audio)
            print(f"  [YOU SAID]: \"{text}\"")
            return text
        except sr.WaitTimeoutError:
            print("  [VOICE] Silence detected (timed out).")
            return None
        except sr.UnknownValueError:
            print("  [VOICE] Could not understand audio.")
            return None
        except Exception as e:
            print(f"  [VOICE] Microphone error: {e}")
            return None


class LyraVoiceAssistant:
    """
    Main Voice Assistant Application.
    Integrates Speech Input/Output, Phone Action Automation, and Grok Q&A.
    """

    def __init__(self):
        self.voice = VoiceEngine()
        self.listener = VoiceListener()
        self.agent = AgentLoop()
        self.responder = Responder()

    def run(self):
        self._print_welcome_banner()
        self.voice.speak("Hello! I am LYRA, your AI phone assistant. How can I help you today?")

        while True:
            print("\n" + "-" * 55)
            print("  Press ENTER to speak into Mic, type your command, or 'q' to exit")
            choice = input("  Command [Mic / Text]: ").strip()

            if choice.lower() in ("q", "quit", "exit"):
                self.voice.speak("Goodbye! Have a great day.")
                break

            user_text = ""
            if choice == "":
                # Listen from mic
                user_text = self.listener.listen(timeout=6.0)
                if not user_text:
                    self.voice.speak("I didn't hear anything. You can also type your command below.")
                    continue
            else:
                user_text = choice

            self._process_command(user_text)

    def _process_command(self, user_text: str):
        text_lower = user_text.lower().strip()

        # Handle special utility commands
        if text_lower in ("tasks", "list tasks", "what can you do"):
            tasks_list = ", ".join([t.replace("_", " ") for t in list_tasks()])
            msg = f"I can execute phone actions like: {tasks_list}."
            self.voice.speak(msg)
            return

        if text_lower in ("status", "check phone", "what is on screen"):
            try:
                self.voice.speak("Checking phone screen...")
                perception = self.agent.coordinator.perceive()
                state = perception.get("screen_state", "UNKNOWN")
                dets = len(perception.get("detections", []))
                msg = f"Your phone is currently on the {state.replace('_', ' ')} with {dets} UI elements detected."
                self.voice.speak(msg)
            except Exception as e:
                self.voice.speak(f"Could not read phone screen. Error: {e}")
            return

        # Classify intent (ACTION vs QUESTION)
        intent_type, matched = classify_intent(user_text)

        if intent_type == "ACTION":
            try:
                task_name = resolve_task_from_input(user_text)
                clean_name = task_name.replace("_", " ")
                self.voice.speak(f"Starting action: {clean_name} on your phone.")

                # Execute phone action task
                result = self.agent.run_task(task_name)

                if result.get("success", False):
                    self.voice.speak(f"Successfully completed {clean_name}.")
                else:
                    self.voice.speak(f"Action {clean_name} encountered an issue. Check the logs.")

            except ValueError:
                self.voice.speak(f"I recognized that as a phone action, but I don't have a task matching '{user_text}'. Try asking to open instagram or camera.")
            except Exception as e:
                self.voice.speak(f"Action failed. Error: {e}")

        elif intent_type == "QUESTION":
            self.voice.speak("Let me look that up for you.")

            # Route to Grok API
            if grok.enabled:
                answer = grok.ask(user_text)
                self.voice.speak(answer)
            else:
                answer = (
                    f"I processed your question: '{user_text}'. "
                    "To get AI answers, set your GROK_API_KEY in the .env file."
                )
                self.voice.speak(answer)

    def _print_welcome_banner(self):
        print()
        print("  =======================================================")
        print("   LYRA VOICE ASSISTANT — Intelligent Phone & AI Engine")
        print("  =======================================================")
        print("   * Voice Input & Speech Output (TTS)")
        print("   * Phone Action Automation (ADB + Vision Model)")
        print("   * General Knowledge Q&A (xAI Grok API Integration)")
        print("  =======================================================")
        print()


if __name__ == "__main__":
    assistant = LyraVoiceAssistant()
    assistant.run()
