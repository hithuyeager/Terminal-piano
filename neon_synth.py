
"""
NEON SYNTH
A tiny terminal music machine built with Textual + pygame.

Install:
    pip install textual pygame

Run:
    python neon_synth.py

Keys:
    Q W E R T Y U I  -> notes
    A S D F G H J K  -> lower octave
    1-8               -> drum sounds
    SPACE             -> play/stop sequencer
    [ / ]             -> BPM
    C                 -> clear pattern
    Q                 -> quit
"""

import math
import random
import threading
import time
from array import array
from dataclasses import dataclass

import pygame
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.timer import Timer
from textual.widgets import Footer, Header, Static


SAMPLE_RATE = 44100

# Frequencies for a small playable keyboard.
NOTES = {
    "q": 261.63, "w": 293.66, "e": 329.63, "r": 349.23,
    "t": 392.00, "y": 440.00, "u": 493.88, "i": 523.25,
    "a": 130.81, "s": 146.83, "d": 164.81, "f": 174.61,
    "g": 196.00, "h": 220.00, "j": 246.94, "k": 261.63,
}

NOTE_LABELS = {
    "q": "C4", "w": "D4", "e": "E4", "r": "F4",
    "t": "G4", "y": "A4", "u": "B4", "i": "C5",
    "a": "C3", "s": "D3", "d": "E3", "f": "F3",
    "g": "G3", "h": "A3", "j": "B3", "k": "C4",
}


@dataclass
class Pad:
    key: str
    label: str
    active: bool = False


def make_tone(freq: float, duration=0.24, volume=0.34):
    """Generate a warm sine + harmonic tone in memory."""
    count = int(SAMPLE_RATE * duration)
    frames = array("h")

    for n in range(count):
        t = n / SAMPLE_RATE

        # Attack / release envelope.
        attack = min(1.0, t / 0.012)
        release = min(1.0, max(0.0, (duration - t) / 0.055))
        envelope = attack * release

        # Fundamental + subtle harmonics.
        sample = (
            math.sin(2 * math.pi * freq * t)
            + 0.22 * math.sin(2 * math.pi * freq * 2 * t)
            + 0.08 * math.sin(2 * math.pi * freq * 3 * t)
        )

        frames.append(int(32767 * volume * envelope * sample / 1.30))

    return pygame.mixer.Sound(buffer=frames.tobytes())


def make_kick():
    duration = 0.18
    count = int(SAMPLE_RATE * duration)
    frames = array("h")

    for n in range(count):
        t = n / SAMPLE_RATE
        freq = 130 * math.exp(-18 * t) + 42
        envelope = math.exp(-22 * t)
        value = math.sin(2 * math.pi * freq * t) * envelope
        frames.append(int(32767 * 0.55 * value))

    return pygame.mixer.Sound(buffer=frames.tobytes())


def make_hat():
    duration = 0.055
    count = int(SAMPLE_RATE * duration)
    frames = array("h")

    for n in range(count):
        t = n / SAMPLE_RATE
        envelope = math.exp(-75 * t)
        noise = random.uniform(-1, 1)
        frames.append(int(32767 * 0.20 * noise * envelope))

    return pygame.mixer.Sound(buffer=frames.tobytes())


class SynthAudio:
    def __init__(self):
        pygame.mixer.pre_init(SAMPLE_RATE, -16, 1, 256)
        pygame.init()
        pygame.mixer.init()

        self.notes = {key: make_tone(freq) for key, freq in NOTES.items()}
        self.kick = make_kick()
        self.hat = make_hat()

        self.lock = threading.Lock()
        self.last_note = "-"

    def play_note(self, key: str):
        sound = self.notes.get(key)
        if sound:
            sound.play()
            with self.lock:
                self.last_note = NOTE_LABELS[key]

    def play_kick(self):
        self.kick.play()

    def play_hat(self):
        self.hat.play()

    def close(self):
        pygame.mixer.quit()
        pygame.quit()


class NeonSynth(App):
    TITLE = "NEON SYNTH // TERMINAL MUSIC MACHINE"
    SUB_TITLE = "play the keyboard • build a loop • make noise"

    CSS = """
    Screen {
        background: #050711;
        color: #d7e7ff;
    }

    Header {
        background: #080d1d;
        color: #66e3ff;
        text-style: bold;
    }

    Footer {
        background: #080d1d;
        color: #91a4c7;
    }

    #main {
        height: 1fr;
        padding: 1 2;
    }

    #hero {
        height: 5;
        border: round #315cff;
        background: #081026;
        padding: 1 2;
    }

    #hero_title {
        color: #a78bfa;
        text-style: bold;
    }

    #visualizer {
        height: 8;
        border: round #0ea5e9;
        background: #03050c;
        color: #43e7ff;
        padding: 1 2;
    }

    #middle {
        height: 15;
    }

    .panel {
        border: round #243b70;
        background: #070b17;
        padding: 1;
        margin: 1 1 0 0;
    }

    #keyboard {
        width: 2fr;
    }

    #sequencer {
        width: 1fr;
        margin-right: 0;
    }

    #pads {
        height: 8;
        padding: 1;
    }

    .pad {
        width: 1fr;
        height: 3;
        margin: 0 1 1 0;
        border: round #334155;
        content-align: center middle;
        background: #0b1224;
    }

    .pad_active {
        border: round #67e8f9;
        color: #67e8f9;
        background: #112744;
        text-style: bold;
    }

    #status {
        height: 5;
        border: round #19315a;
        background: #060b16;
        padding: 1 2;
        color: #8da6cf;
    }

    .accent {
        color: #67e8f9;
    }

    .pink {
        color: #e879f9;
    }
    """

    bpm = reactive(124)
    running = reactive(False)
    current_step = reactive(0)
    last_key = reactive("-")

    def __init__(self):
        super().__init__()
        self.audio = None
        self.pad_widgets = {}
        self.sequence = [False] * 16
        self.timer: Timer | None = None
        self.visual_tick = 0

    def compose(self) -> ComposeResult:
        yield Header()

        with Vertical(id="main"):
            with Vertical(id="hero"):
                yield Static("✦  N E O N   S Y N T H", id="hero_title")
                yield Static(
                    "A tiny instrument hiding inside your terminal. "
                    "Press the keys. Build the loop. Break the silence."
                )
                yield Static("BPM 124   •   KEY C MAJOR   •   AUDIO ONLINE", id="hero_meta")

            yield Static("", id="visualizer")

            with Horizontal(id="middle"):
                with Vertical(classes="panel", id="keyboard"):
                    yield Static("[ KEYBOARD ]   Q W E R T Y U I   /   A S D F G H J K")
                    with Horizontal(id="pads"):
                        for key in "qwertyui":
                            yield Static(
                                f" {key.upper()}  {NOTE_LABELS[key]} ",
                                classes="pad",
                                id=f"pad-{key}",
                            )

                with Vertical(classes="panel", id="sequencer"):
                    yield Static("[ 16-STEP SEQUENCER ]")
                    yield Static("", id="seq_view")
                    yield Static(
                        "[SPACE] play/stop   [1-8] drums   [[ / ]] BPM   [C] clear"
                    )

            yield Static("", id="status")

        yield Footer()

    def on_mount(self):
        try:
            self.audio = SynthAudio()
        except Exception as exc:
            self.audio = None
            self.query_one("#status", Static).update(
                f"Audio initialization failed: {exc}\n"
                "The visual synthesizer still works. Install pygame and check your system audio."
            )

        self.set_interval(0.05, self.refresh_visualizer)
        self.set_interval(0.10, self.refresh_ui)

    def on_unmount(self):
        if self.audio:
            self.audio.close()

    def refresh_ui(self):
        self.query_one("#seq_view", Static).update(self.render_sequence())
        self.query_one("#status", Static).update(self.render_status())

    def refresh_visualizer(self):
        self.visual_tick += 1

        bars = []
        for i in range(42):
            wave = (
                math.sin(self.visual_tick * 0.16 + i * 0.47) * 0.35
                + math.sin(self.visual_tick * 0.071 + i * 0.19) * 0.25
                + random.uniform(-0.12, 0.12)
            )
            height = max(1, int((wave + 0.7) * 3.0))
            bars.append("▁▂▃▄▅▆▇"[min(6, height)])

        self.query_one("#visualizer", Static).update(
            " ".join(bars)
            + "\n\n"
            + "  LIVE SPECTRUM   "
            + ("● PLAYING" if self.running else "○ READY")
            + f"       BPM {self.bpm}       NOTE {self.last_key}"
        )

    def render_sequence(self):
        result = []
        for i, enabled in enumerate(self.sequence):
            if i == self.current_step and self.running:
                result.append("▶" if enabled else "▷")
            else:
                result.append("●" if enabled else "·")

        return (
            " ".join(result[:8])
            + "\n"
            + " ".join(result[8:])
            + "\n\n"
            + "tap a step with [1-8] to add percussion"
        )

    def render_status(self):
        audio = "ONLINE" if self.audio else "OFFLINE"
        return (
            f" AUDIO  {audio}     "
            f" LAST NOTE  {self.last_key:<3}     "
            f" TEMPO  {self.bpm} BPM     "
            f" SEQUENCER  {'RUNNING' if self.running else 'STOPPED'}"
        )

    def on_key(self, event):
        key = event.key.lower()

        if key in NOTES:
            self.last_key = NOTE_LABELS[key]
            if self.audio:
                self.audio.play_note(key)

            widget = self.pad_widgets.get(key) or self.query_one(
                f"#pad-{key}", Static
            )
            self.pad_widgets[key] = widget
            widget.add_class("pad_active")
            self.set_timer(0.13, lambda w=widget: w.remove_class("pad_active"))
            return

        if key == "space":
            self.running = not self.running
            if self.running:
                self.current_step = 0
                self.timer = self.set_interval(60 / self.bpm / 4, self.advance_step)
            elif self.timer:
                self.timer.pause()
            return

        if key == "[":
            self.bpm = max(60, self.bpm - 4)
            if self.running:
                self.restart_clock()
            return

        if key == "]":
            self.bpm = min(220, self.bpm + 4)
            if self.running:
                self.restart_clock()
            return

        if key in "12345678":
            step = int(key) - 1
            self.sequence[step] = not self.sequence[step]
            return

        if key == "c":
            self.sequence = [False] * 16
            self.current_step = 0
            return

    def restart_clock(self):
        if self.timer:
            self.timer.stop()
        self.timer = self.set_interval(60 / self.bpm / 4, self.advance_step)

    def advance_step(self):
        if not self.running:
            return

        self.current_step = (self.current_step + 1) % 16

        # Simple drum pattern.
        if self.current_step % 4 == 0 and self.audio:
            self.audio.play_kick()

        if self.current_step % 2 == 0 and self.audio:
            self.audio.play_hat()

        # Play enabled notes as a little C-major sequence.
        if self.sequence[self.current_step] and self.audio:
            melody = ["q", "e", "t", "u", "i", "t", "e", "q"]
            self.audio.play_note(melody[self.current_step % len(melody)])


if __name__ == "__main__":
    NeonSynth().run()
