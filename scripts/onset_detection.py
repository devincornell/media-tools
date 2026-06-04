import librosa
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

# --- Usage ---
# Ensure you have librosa installed: pip install librosa
audio_file = "scripts/sorry.mp3" 
tempo, beats, onsets = analyze_track_for_video(audio_file)

print(f"\nEstimated Tempo: {tempo[0]:.2f} BPM")
print(f"Total steady beats found: {len(beats)}")
print(f"First 5 steady beats (seconds): {beats[:5]}")

print(f"\nTotal sudden onsets found: {len(onsets)}")
print(f"First 5 sudden onsets (seconds): {onsets[:5]}")