####################### Probe Errors #######################
class ProbeError(Exception):
    pass

class MultipleStreamsError(ProbeError):
    pass

class NoVideoStreamError(ProbeError):
    pass

class NoAudioStreamError(ProbeError):
    pass

class NoDurationError(ProbeError):
    pass

class NoResolutionError(ProbeError):
    pass