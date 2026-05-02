import mediatools





if __name__ == "__main__":
    
    tr = mediatools.ai.transcribe_video_openai('scripts/test_data/totk_compressed.mp4')

    for ts in tr.segments:
        print(f'[{ts.start:.2f} - {ts.end:.2f}] {ts.text}')


