/**
 * app.js — Humanized Dynamic Frontend for LYRA Voice Assistant Web UI.
 * Features 60 FPS screen mirror, Web Speech API, Direct Interactive Touch Tap, 
 * Visual Personality Studio (AURA, WAVE, RADIAL, GRID, BAR), Color Hue Customizer, and Theme Switching.
 */

// Theme Toggle State Management
function toggleTheme() {
  const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
  const newTheme = currentTheme === "dark" ? "light" : "dark";

  document.documentElement.setAttribute("data-theme", newTheme);
  localStorage.setItem("lyra-theme", newTheme);

  updateThemeUI(newTheme);
}

function updateThemeUI(theme) {
  const themeIcon = document.getElementById("themeIcon");
  const themeLabel = document.getElementById("themeLabel");

  if (theme === "light") {
    if (themeIcon) themeIcon.innerText = "☀️";
    if (themeLabel) themeLabel.innerText = "Light Mode";
  } else {
    if (themeIcon) themeIcon.innerText = "🌙";
    if (themeLabel) themeLabel.innerText = "Dark Mode";
  }
}

// Initialize saved theme
const savedTheme = localStorage.getItem("lyra-theme") || "dark";
document.documentElement.setAttribute("data-theme", savedTheme);

// DOM Elements
const micBtn = document.getElementById("micBtn");
const micWrapper = document.getElementById("micWrapper");
const voiceStatusText = document.getElementById("voiceStatusText");
const chatLog = document.getElementById("chatLog");
const chatInput = document.getElementById("chatInput");
const phoneScreenImg = document.getElementById("phoneScreenImg");
const phoneScreenWrapper = document.getElementById("phoneScreenWrapper");
const touchRippleContainer = document.getElementById("touchRippleContainer");
const bboxCanvas = document.getElementById("bboxCanvas");
const screenStateBadge = document.getElementById("screenStateBadge");
const refreshScreenBtn = document.getElementById("refreshScreenBtn");
const aiAvatarCanvas = document.getElementById("aiAvatarCanvas");
const activeStyleBadge = document.getElementById("activeStyleBadge");
const colorHueSlider = document.getElementById("colorHueSlider");
const hueColorPreview = document.getElementById("hueColorPreview");

// Contexts
const ctx = bboxCanvas ? bboxCanvas.getContext("2d") : null;
const avatarCtx = aiAvatarCanvas ? aiAvatarCanvas.getContext("2d") : null;

// Global State
let cachedDetections = [];
let aiState = "LISTENING"; // LISTENING, SPEAKING, THINKING, CONNECTING
let visualizerStyle = "AURA"; // AURA, WAVE, RADIAL, GRID, BAR
let colorHue = 180; // 0 to 360
let avatarAngle = 0;

// Web Speech Recognition Initialization
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let isListening = false;

if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = 'en-US';

  recognition.onstart = () => {
    isListening = true;
    setAgentState("LISTENING");
    if (micWrapper) micWrapper.classList.add("listening");
    if (voiceStatusText) voiceStatusText.innerText = "Listening... Speak into your microphone";
  };

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    if (voiceStatusText) voiceStatusText.innerText = `Recognized: "${transcript}"`;
    addChatBubble("user", transcript);
    processCommand(transcript);
  };

  recognition.onerror = (event) => {
    isListening = false;
    setAgentState("LISTENING");
    if (micWrapper) micWrapper.classList.remove("listening");
    if (voiceStatusText) voiceStatusText.innerText = "Listening error. Try clicking the mic again.";
  };

  recognition.onend = () => {
    isListening = false;
    if (micWrapper) micWrapper.classList.remove("listening");
  };
}

// Microphone Button Click Handler
if (micBtn) {
  micBtn.addEventListener("click", () => {
    if (!recognition) {
      alert("Speech recognition is not supported in this browser. Please type your message.");
      return;
    }
    if (isListening) {
      recognition.stop();
    } else {
      recognition.start();
    }
  });
}

// Visual Personality Studio Handlers
function setAgentState(state) {
  aiState = state;
  const pills = ["PillListening", "PillSpeaking", "PillThinking", "PillConnecting"];
  pills.forEach(p => {
    const el = document.getElementById("pill" + state.charAt(0) + state.slice(1).toLowerCase());
    const allEl = document.querySelectorAll(".state-pill");
    allEl.forEach(btn => btn.classList.remove("active"));
    if (el) el.classList.add("active");
  });
}

function setVisualizerStyle(style) {
  visualizerStyle = style;
  if (activeStyleBadge) activeStyleBadge.innerText = style;

  const styles = ["Aura", "Wave", "Radial", "Grid", "Bar"];
  styles.forEach(s => {
    const el = document.getElementById("style" + s);
    if (el) el.classList.remove("active");
  });

  const activeEl = document.getElementById("style" + style.charAt(0) + style.slice(1).toLowerCase());
  if (activeEl) activeEl.classList.add("active");
}

function updateVisualizerParams() {
  if (colorHueSlider) {
    colorHue = parseInt(colorHueSlider.value);
    if (hueColorPreview) {
      hueColorPreview.style.background = `hsl(${colorHue}, 100%, 50%)`;
    }
    const orbGlow = document.getElementById("aiOrbGlow");
    if (orbGlow) {
      orbGlow.style.background = `radial-gradient(circle, hsl(${colorHue}, 100%, 50%) 0%, hsl(${(colorHue + 60) % 360}, 100%, 50%) 60%, transparent 70%)`;
    }
  }
}

// Text Form Submit Handler
function handleFormSubmit(event) {
  event.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;

  chatInput.value = "";
  addChatBubble("user", text);
  processCommand(text);
}

// Suggestion Chip Handler
function sendSuggestion(text) {
  addChatBubble("user", text);
  processCommand(text);
}

// Speak text response via browser TTS
function speakResponse(text) {
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    
    utterance.onstart = () => { setAgentState("SPEAKING"); };
    utterance.onend = () => { setAgentState("LISTENING"); };
    utterance.onerror = () => { setAgentState("LISTENING"); };

    window.speechSynthesis.speak(utterance);
  }
}

// Append Chat Bubble
function addChatBubble(sender, message) {
  removeTypingIndicator();

  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${sender}`;
  bubble.innerText = message;
  chatLog.appendChild(bubble);
  chatLog.scrollTop = chatLog.scrollHeight;
}

// Typing Indicator
function showTypingIndicator() {
  removeTypingIndicator();

  const bubble = document.createElement("div");
  bubble.className = "chat-bubble assistant typing-bubble";
  bubble.id = "typingIndicator";
  bubble.innerHTML = `
    <div class="typing-dot"></div>
    <div class="typing-dot"></div>
    <div class="typing-dot"></div>
  `;
  chatLog.appendChild(bubble);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function removeTypingIndicator() {
  const el = document.getElementById("typingIndicator");
  if (el) el.remove();
}

// Process Command via Backend API
async function processCommand(text) {
  setAgentState("THINKING");
  if (voiceStatusText) voiceStatusText.innerText = `LYRA is thinking...`;
  showTypingIndicator();

  try {
    const response = await fetch("/api/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: text }),
    });

    if (!response.ok) {
      throw new Error(`Backend returned HTTP ${response.status}`);
    }
    const data = await response.json();
    if (!data || typeof data.response !== "string") {
      throw new Error("Backend returned an invalid response");
    }

    addChatBubble("assistant", data.response);
    speakResponse(data.response);
    if (voiceStatusText) voiceStatusText.innerText = "Ready";

    updatePerception();

  } catch (error) {
    console.error("Error processing command:", error);
    const errText = "Could not connect to LYRA backend server.";
    addChatBubble("assistant", errText);
    speakResponse(errText);
    if (voiceStatusText) voiceStatusText.innerText = "Server connection error";
    setAgentState("LISTENING");
  }
}

// Execute Quick Action Button
function executeQuickAction(actionName) {
  const cleanName = actionName.replace("_", " ");
  addChatBubble("user", `Execute ${cleanName}`);
  processCommand(actionName);
}

async function launchScrcpyMirror() {
  try {
    const res = await fetch("/api/launch_scrcpy");
    const data = await res.json();
    if (data.status === "success") {
      addChatBubble("assistant", "Launched hardware zero-lag scrcpy screen mirror (60 FPS, Direct3D11)!");
    }
  } catch (e) {
    console.error("Scrcpy launch error:", e);
  }
}

// Interactive Direct Phone Screen Touch Tapping
async function handlePhoneScreenClick(event) {
  const rect = phoneScreenImg.getBoundingClientRect();
  const clickX = event.clientX - rect.left;
  const clickY = event.clientY - rect.top;

  const phoneWidth = Number(phoneScreenWrapper.dataset.phoneWidth) || 720;
  const phoneHeight = Number(phoneScreenWrapper.dataset.phoneHeight) || 1600;

  const targetX = Math.round((clickX / rect.width) * phoneWidth);
  const targetY = Math.round((clickY / rect.height) * phoneHeight);

  spawnTouchRipple(clickX, clickY);

  try {
    const response = await fetch("/api/tap", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ x: targetX, y: targetY }),
    });
    if (!response.ok) throw new Error(`Tap failed with HTTP ${response.status}`);

    setTimeout(updatePerception, 300);
  } catch (err) {
    console.error("Failed to tap screen:", err);
  }
}

function spawnTouchRipple(x, y) {
  if (!touchRippleContainer) return;
  const ripple = document.createElement("div");
  ripple.className = "touch-ripple";
  ripple.style.left = `${x}px`;
  ripple.style.top = `${y}px`;
  touchRippleContainer.appendChild(ripple);
  setTimeout(() => ripple.remove(), 600);
}

// Refresh stream connection
function refreshVideoStream() {
  phoneScreenImg.src = "/stream.mjpg?t=" + Date.now();
  updatePerception();
}

// Asynchronous Background Model Perception
async function updatePerception() {
  try {
    const res = await fetch("/api/perceive");
    const data = await res.json();

    if (data.screen_state) {
      screenStateBadge.innerText = `SCREEN STATE: ${data.screen_state} (${(data.screen_confidence * 100).toFixed(0)}%)`;
    }

    cachedDetections = data.detections || [];
    drawBoundingBoxes(cachedDetections);

  } catch (err) {
    console.error("Perception update failed:", err);
  }
}

async function updateDeviceInfo() {
  try {
    const res = await fetch("/api/device");
    const data = await res.json();
    if (!res.ok || !data.connected) throw new Error(data.error || "Phone unavailable");
    phoneScreenWrapper.dataset.phoneWidth = data.width;
    phoneScreenWrapper.dataset.phoneHeight = data.height;
    const status = document.getElementById("deviceStatusText");
    if (status) status.innerText = `Android phone connected (${data.width}x${data.height})`;
    drawBoundingBoxes(cachedDetections);
  } catch (err) {
    const status = document.getElementById("deviceStatusText");
    if (status) status.innerText = "Phone disconnected";
    console.error("Device info update failed:", err);
  }
}

// Draw Bounding Boxes on Overlay Canvas
function drawBoundingBoxes(detections) {
  if (!bboxCanvas || !ctx || !phoneScreenImg) return;
  bboxCanvas.width = phoneScreenImg.clientWidth;
  bboxCanvas.height = phoneScreenImg.clientHeight;

  ctx.clearRect(0, 0, bboxCanvas.width, bboxCanvas.height);

  if (!detections || detections.length === 0) return;

  const colors = [`hsl(${colorHue}, 100%, 50%)`, `hsl(${(colorHue + 60) % 360}, 100%, 50%)`, "#f43f5e", "#10b981", "#f59e0b"];

  const phoneWidth = Number(phoneScreenWrapper?.dataset.phoneWidth) || 720;
  const phoneHeight = Number(phoneScreenWrapper?.dataset.phoneHeight) || 1600;
  const scaleX = bboxCanvas.width / phoneWidth;
  const scaleY = bboxCanvas.height / phoneHeight;

  detections.forEach((det, idx) => {
    const [xmin, ymin, xmax, ymax] = det.bbox_original;

    const x = xmin * scaleX;
    const y = ymin * scaleY;
    const w = (xmax - xmin) * scaleX;
    const h = (ymax - ymin) * scaleY;

    const color = colors[idx % colors.length];

    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.strokeRect(x, y, w, h);

    ctx.fillStyle = color;
    const labelText = `${det.label} ${(det.confidence * 100).toFixed(0)}%`;
    ctx.font = "bold 12px Plus Jakarta Sans, sans-serif";
    const textWidth = ctx.measureText(labelText).width;

    ctx.fillRect(x, Math.max(0, y - 22), textWidth + 10, 22);

    ctx.fillStyle = "#ffffff";
    ctx.fillText(labelText, x + 5, Math.max(14, y - 6));
  });
}

// Animated Visual Personality Engine (5 Shaders: AURA, WAVE, RADIAL, GRID, BAR)
function renderVisualizer() {
  if (!avatarCtx) return;
  const w = aiAvatarCanvas.width;
  const h = aiAvatarCanvas.height;
  const cx = w / 2;
  const cy = h / 2;

  avatarCtx.clearRect(0, 0, w, h);
  avatarAngle += (aiState === "THINKING" ? 0.08 : 0.03);

  const mainColor = `hsl(${colorHue}, 100%, 60%)`;
  const subColor = `hsl(${(colorHue + 60) % 360}, 100%, 55%)`;

  if (visualizerStyle === "AURA") {
    // 💫 AURA: Undulating morphing liquid energy ring
    avatarCtx.save();
    avatarCtx.translate(cx, cy);
    avatarCtx.rotate(avatarAngle * 0.5);

    const points = 60;
    const baseRadius = 55;
    avatarCtx.beginPath();
    for (let i = 0; i <= points; i++) {
      const theta = (i / points) * Math.PI * 2;
      const waveVal = Math.sin(theta * 4 + avatarAngle * 3) * (aiState === "SPEAKING" ? 12 : 6);
      const r = baseRadius + waveVal;
      const x = Math.cos(theta) * r;
      const y = Math.sin(theta) * r;
      if (i === 0) avatarCtx.moveTo(x, y);
      else avatarCtx.lineTo(x, y);
    }
    avatarCtx.closePath();

    avatarCtx.strokeStyle = mainColor;
    avatarCtx.lineWidth = 6;
    avatarCtx.shadowColor = mainColor;
    avatarCtx.shadowBlur = 18;
    avatarCtx.stroke();

    avatarCtx.strokeStyle = subColor;
    avatarCtx.lineWidth = 3;
    avatarCtx.shadowBlur = 10;
    avatarCtx.stroke();

    avatarCtx.restore();

  } else if (visualizerStyle === "WAVE") {
    // 〰️ WAVE: Oscillating soundwave harmonics
    avatarCtx.lineWidth = 3;
    const waves = 4;
    for (let wIdx = 0; wIdx < waves; wIdx++) {
      avatarCtx.beginPath();
      avatarCtx.strokeStyle = wIdx % 2 === 0 ? mainColor : subColor;
      avatarCtx.shadowColor = avatarCtx.strokeStyle;
      avatarCtx.shadowBlur = 12;

      for (let x = 20; x < w - 20; x += 4) {
        const y = cy + Math.sin(x * 0.05 + avatarAngle * 4 + wIdx) * (15 + wIdx * 4) * (aiState === "SPEAKING" ? 1.5 : 0.8);
        if (x === 20) avatarCtx.moveTo(x, y);
        else avatarCtx.lineTo(x, y);
      }
      avatarCtx.stroke();
    }

  } else if (visualizerStyle === "RADIAL") {
    // ❇️ RADIAL: Radiating audio spectrum pins
    const pins = 24;
    const innerR = 40;
    for (let i = 0; i < pins; i++) {
      const theta = (i / pins) * Math.PI * 2 + avatarAngle * 0.5;
      const pinLen = 15 + Math.abs(Math.sin(avatarAngle * 4 + i)) * (aiState === "SPEAKING" ? 30 : 15);
      
      const x1 = cx + Math.cos(theta) * innerR;
      const y1 = cy + Math.sin(theta) * innerR;
      const x2 = cx + Math.cos(theta) * (innerR + pinLen);
      const y2 = cy + Math.sin(theta) * (innerR + pinLen);

      avatarCtx.strokeStyle = (i % 2 === 0) ? mainColor : subColor;
      avatarCtx.lineWidth = 4;
      avatarCtx.lineCap = "round";
      avatarCtx.shadowColor = avatarCtx.strokeStyle;
      avatarCtx.shadowBlur = 10;

      avatarCtx.beginPath();
      avatarCtx.moveTo(x1, y1);
      avatarCtx.lineTo(x2, y2);
      avatarCtx.stroke();
    }

  } else if (visualizerStyle === "GRID") {
    // ⣿ GRID: Matrix pulsating dot grid
    const cols = 5;
    const rows = 5;
    const spacing = 22;
    const startX = cx - (cols - 1) * spacing / 2;
    const startY = cy - (rows - 1) * spacing / 2;

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const dotX = startX + c * spacing;
        const dotY = startY + r * spacing;
        const pulse = Math.abs(Math.sin(avatarAngle * 3 + r + c)) * 8 + 4;

        avatarCtx.fillStyle = (r + c) % 2 === 0 ? mainColor : subColor;
        avatarCtx.shadowColor = avatarCtx.fillStyle;
        avatarCtx.shadowBlur = 12;

        avatarCtx.beginPath();
        avatarCtx.arc(dotX, dotY, pulse, 0, Math.PI * 2);
        avatarCtx.fill();
      }
    }

  } else if (visualizerStyle === "BAR") {
    // 📊 BAR: Vertical equalizer spectrum bars
    const bars = 9;
    const barW = 10;
    const gap = 8;
    const startX = cx - (bars * (barW + gap)) / 2;

    for (let i = 0; i < bars; i++) {
      const hVal = 12 + Math.abs(Math.sin(avatarAngle * 5 + i * 0.8)) * (aiState === "SPEAKING" ? 60 : 25);
      const bx = startX + i * (barW + gap);
      const by = cy - hVal / 2;

      avatarCtx.fillStyle = i % 2 === 0 ? mainColor : subColor;
      avatarCtx.shadowColor = avatarCtx.fillStyle;
      avatarCtx.shadowBlur = 10;

      avatarCtx.beginPath();
      avatarCtx.roundRect(bx, by, barW, hVal, 5);
      avatarCtx.fill();
    }
  }
}

// 60 FPS Master Render Loop
function renderLoop() {
  drawBoundingBoxes(cachedDetections);
  renderVisualizer();
  requestAnimationFrame(renderLoop);
}

// Event Listeners
if (refreshScreenBtn) {
  refreshScreenBtn.addEventListener("click", () => {
    refreshVideoStream();
  });
}

// Initial Setup & Timers
window.addEventListener("DOMContentLoaded", () => {
  updateThemeUI(savedTheme);
  updateVisualizerParams();
  updateDeviceInfo();
  updatePerception();
  setInterval(updatePerception, 2500);
  requestAnimationFrame(renderLoop);
});
