import pathlib
import subprocess
import typing
from pathlib import Path
import dataclasses



@dataclasses.dataclass(repr=False)
class CommandExecutionResult:
    '''A class to represent the result of an FFMPEG command.
    Description: this is a container for both the subprocess.CompletedProcess and 
    the FFMPEG command that was run to generate it. You can access the command's
    output (stderrr), return code, etc. via this class.
    '''
    command: list[str]
    result: subprocess.CompletedProcess
    timeout: float|None 
    cwd: str|Path|None
    env: dict[str, str]|None

    
    @property
    def output(self) -> str:
        '''Return progress and diagnostic output of the FFMPEG command (note: ffmpeg sends it to stdout).'''
        return self.result.stderr.strip()

    @property
    def stderr(self) -> str:
        '''Return progress and diagnostic output of the FFMPEG command (ffmpeg sends it to stdout).'''
        return self.result.stderr.strip()

    @property
    def stdout(self) -> str:
        '''Return stdout of the FFMPEG command. This is unliklely to be useful.'''
        return self.result.stdout.strip()

    @property
    def output_files(self) -> list[Path]:
        '''Return the output file paths of the FFMPEG command.'''
        return [Path(output.path) for output in self.command.outputs]
    
    @property
    def output_file(self) -> Path:
        '''Return the first output file path of the FFMPEG command (for backward compatibility).'''
        if self.command.outputs:
            return Path(self.command.outputs[0].path)
        raise ValueError("No output files specified in command.")

    @property
    def returncode(self) -> int:
        '''Return the return code of the FFMPEG command.'''
        return self.result.returncode
    
    def __str__(self) -> str:
        '''Return a string representation of the FFMPEGResult.'''
        return f"{self.__class__.__name__}(command={self.command.get_command()}, returncode={self.returncode}, output_length={len(self.result.stderr)})"



def execute_subprocess(
    cmd: list[str], 
    timeout: float|None = None, 
    cwd: str|Path|None = None, 
    env: dict[str, str]|None = None
) -> CommandExecutionResult:
    '''Run a subprocess with the given command and parameters.'''
    try:
        # Execute the command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
            check=True,
            #stdin=subprocess.DEVNULL, # not sure if I should hard-code this, but here we are.
        )
        
    except subprocess.CalledProcessError as e:
        error_msg = f"FFMPEG command failed: {' '.join(cmd)}"
        raise CommandExecutionError.from_stdout_stderr(
            stdout=e.stdout,
            stderr=e.stderr,
            msg=f'{error_msg} - {e.stderr.strip() if e.stderr else "<no stderr output>"}'
        ) from e
        
    except subprocess.TimeoutExpired as e:
        raise CommandTimeoutError(f"FFMPEG command timed out after {timeout} seconds: {' '.join(cmd)}")
        
    except FileNotFoundError as e:
        raise CommandMissingFromPathError("FFMPEG not found in PATH. Please ensure FFMPEG is installed and available.")

    return CommandExecutionResult(
        command=cmd, 
        result=result,
        timeout=timeout,
        cwd=cwd,
        env=env,
    )


class CommandExecutionError(Exception):
    stdout: str
    stderr: str

    @classmethod
    def from_stderr(cls, stderr: str | bytes, msg: str|None=None) -> typing.Self:
        '''Create a FFMPEGError from stderr string.'''
        return cls.from_stdout_stderr(stdout=None, stderr=stderr, msg=msg)
    
    @classmethod
    def from_stdout(cls, stderr: str | bytes, msg: str|None=None) -> typing.Self:
        '''Create a FFMPEGError from stdout and stderr strings.'''
        return cls.from_stdout_stderr(stdout=None, stderr=stderr, msg=msg)
        
    @classmethod
    def from_stdout_stderr(cls, stdout:str|bytes|None=None, stderr:str|bytes|None=None, msg:str|None=None) -> typing.Self:
        '''Create a FFMPEGError from stdout and stderr strings.'''
        o = cls(msg)
        o.stdout = stdout.decode() if isinstance(stdout, bytes) else stdout
        o.stderr = stderr.decode() if isinstance(stderr, bytes) else stderr
        return o
    
    def clean_stdout(self) -> str:
        '''Clean the stdout string by removing newlines and extra spaces.'''
        if self.stdout is None:
            return ''
        return clean_stdout(self.stdout)
    
    def clean_stderr(self) -> str:
        '''Clean the stderr string by removing newlines and extra spaces.'''
        if self.stderr is None:
            return ''
        return clean_stdout(self.stderr)

def clean_stdout(stdout: str) -> str:
    return ' '.join(stdout.split('\n')).strip()

class CommandTimeoutError(CommandExecutionError):
    pass

class CommandMissingFromPathError(CommandExecutionError):
    pass