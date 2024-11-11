import typing


####################### Probe Errors #######################
class ProbeError(Exception):
    pass

class MultipleStreamsError(ProbeError):
    pass

class NoVideoStreamError(ProbeError):
    pass

class NoAudioStreamError(ProbeError):
    pass

####################### FFMPEG Errors #######################

class FFMPEGCommandError(Exception):
    stderr: str

    @classmethod
    def from_stderr(cls, stderr: str | bytes, msg: str) -> typing.Self:
        o = cls(msg)
        try:
            o.stderr = stderr.decode()
        except AttributeError as e:
            o.stderr = stderr
        return o

#class ProblemCompressingVideo(FFMPEGCommandError):
#    pass

#class ProblemMakingThumb(FFMPEGCommandError):
#    pass

#class ProblemSplicingVideo(FFMPEGCommandError):
#    pass

#class ProblemCroppingVideo(FFMPEGCommandError):
#    pass
