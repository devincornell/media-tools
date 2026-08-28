import argparse

import librosa
import librosa.display
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MultipleLocator
import numpy as np


def analyze_track_for_video(audio_path):
    print(f"Loading audio: {audio_path}...")
    # Load the audio file (sr=None preserves the original sample rate)
    y, sr = librosa.load(audio_path, sr=None)
    
    print("Detecting steady beats...")
    # Get the tempo and the frame indices of the beats
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    
    print("Detecting sudden onsets (drum hits/drops)...")
    # Get the frame indices of loud musical events
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, backtrack=True)
    
    # Convert those frame indices into exact time stamps (in seconds)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)
    
    return tempo, beat_times, onset_times


def plot_detection(audio_path, tempo, beat_times, onset_times, output_path, show=False):
    """Plot the audio features and detector decisions on a shared timeline."""
    y, sr = librosa.load(audio_path, sr=None)
    onset_strength = librosa.onset.onset_strength(y=y, sr=sr)
    onset_strength_times = librosa.frames_to_time(
        np.arange(len(onset_strength)), sr=sr
    )
    spectrogram = librosa.amplitude_to_db(
        np.abs(librosa.stft(y)), ref=np.max
    )

    figure, axes = plt.subplots(
        3, 1, figsize=(100, 14), sharex=True,
        gridspec_kw={"height_ratios": (2, 1, 3)},
    )
    librosa.display.waveshow(y, sr=sr, ax=axes[0], color="black", alpha=0.7)
    axes[0].set_ylabel("Amplitude")
    axes[0].set_title(f"{audio_path} | Estimated tempo: {float(np.asarray(tempo).flat[0]):.1f} BPM")

    axes[1].plot(onset_strength_times, onset_strength, color="darkorange")
    axes[1].fill_between(onset_strength_times, onset_strength, color="orange", alpha=0.2)
    axes[1].set_ylabel("Onset\nstrength")

    librosa.display.specshow(
        spectrogram, sr=sr, x_axis="time", y_axis="log", ax=axes[2], cmap="magma"
    )
    axes[2].set_ylabel("Frequency")
    axes[2].set_xlabel("Time (seconds)")
    axes[2].xaxis.set_major_locator(MultipleLocator(10))
    axes[2].xaxis.set_minor_locator(MultipleLocator(5))
    axes[2].xaxis.set_major_formatter(
        FuncFormatter(lambda seconds, _: f"{int(seconds // 60)}:{int(seconds % 60):02d}")
    )
    axes[2].tick_params(axis="x", which="minor", length=3, color="gray")

    for beat_time in beat_times:
        for axis in axes:
            axis.axvline(beat_time, color="deepskyblue", alpha=0.3, linewidth=0.7)

    for onset_time in onset_times:
        for axis in axes[:2]:
            axis.axvline(onset_time, color="orangered", alpha=0.55, linewidth=0.8)

    axes[0].plot([], [], color="deepskyblue", label="Beat")
    axes[0].plot([], [], color="orangered", label="Detected onset")
    axes[0].legend(loc="upper right")
    figure.tight_layout()
    figure.savefig(output_path, dpi=200)
    print(f"Saved visualization: {output_path}")
    if show:
        plt.show()
    plt.close(figure)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Detect and visualize beats and onsets.")
    parser.add_argument("audio_file", nargs="?", default="scripts/sorry.mp3")
    parser.add_argument(
        "-o", "--output", default="scripts/sorry_detection.png",
        help="PNG path for the visualization",
    )
    parser.add_argument(
        "--show", action="store_true",
        help="Also open an interactive window when a display is available",
    )
    args = parser.parse_args()

    audio_file = args.audio_file
    tempo, beats, onsets = analyze_track_for_video(audio_file)
    plot_detection(audio_file, tempo, beats, onsets, args.output, show=args.show)

    print(f"\nEstimated Tempo: {float(np.asarray(tempo).flat[0]):.2f} BPM")
    print(f"Total steady beats found: {len(beats)}")
    print(f"First 5 steady beats (seconds): {beats[:5]}")

    print(f"\nTotal sudden onsets found: {len(onsets)}")
    print(f"First 5 sudden onsets (seconds): {onsets[:5]}")