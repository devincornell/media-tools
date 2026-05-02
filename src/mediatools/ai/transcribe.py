import time
import pathlib
import dataclasses
import typing


@dataclasses.dataclass
class TranscriptionSegment:
    id: int
    start: float
    end: float
    text: str
    tokens: list[str]
    compression_ratio: float
    avg_logprob: float
    no_speech_prob: float
    seek: int
    temperature: float

    @classmethod
    def from_dict(cls, data: dict) -> typing.Self:
        return cls(
            id=data['id'],
            start=data['start'],
            end=data['end'],
            text=data['text'],
            tokens=data['tokens'],
            compression_ratio=data['compression_ratio'],
            avg_logprob=data['avg_logprob'],
            no_speech_prob=data['no_speech_prob'],
            seek=data['seek'],
            temperature=data['temperature']
        )

@dataclasses.dataclass
class TranscriptionResult:
    language: str
    text: str
    segments: list[TranscriptionSegment]

    @classmethod
    def from_dict(cls, data: dict) -> typing.Self:
        return cls(
            language=data['language'],
            text=data['text'],
            segments=[TranscriptionSegment.from_dict(seg) for seg in data['segments']]
        )



def transcribe_video_openai(video_path: pathlib.Path|str) -> TranscriptionResult:
    '''Transcribe the text from a video file using OpenAI's Whisper model.'''
    try:
        import whisper
    except ImportError as e:
        # Provide a highly actionable error message
        raise ImportError(
            "The 'openai-whisper' library is missing. "
            "To enable transcription, reinstall this package with the transcribe extra: "
            "pip install 'your_awesome_package[transcribe]'"
        ) from e
    
    model = whisper.load_model("base") 
    result = model.transcribe(str(video_path))
    return TranscriptionResult.from_dict(result)

