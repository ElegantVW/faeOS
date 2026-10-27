import numpy as np
from scipy.io.wavfile import write
import math

# GBA-style 8-note chiptune melody
sample_rate = 44100
duration = 5
notes = [
    (440, 0.5),   # A4
    (659, 0.5),   # E5
    (698, 0.5),   # F5
    (784, 0.5),   # G5
    (880, 0.5),   # A5
    (659, 0.5),   # E5
    (698, 0.5),   # F5
    (784, 0.5)    # G5
]

samples = []
for freq, dur in notes:
    t = np.linspace(0, dur, int(sample_rate * dur), False)
    samples.append((np.sin(2 * np.pi * freq * t)).astype(np.float32))

samples = np.concatenate(samples)

# Add reverb, square wave, and percussion
reverb = np.zeros_like(samples)
reverb[1000:] = samples[:-1000]
samples = samples + reverb * 0.3

square_wave = np.sin(2 * np.pi * 220 * np.linspace(0, duration, int(sample_rate * duration)))
samples = samples + square_wave * 0.5

percussion = np.zeros(int(sample_rate * 4))
percussion[::int(sample_rate/4)] = 0.5  # 4th note beat
samples = samples + percussion * 0.3

write("/home/evenweaker/faeOS/audio/sealed_leaf.wav", sample_rate, samples)