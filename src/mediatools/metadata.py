
import json
import typing
from pathlib import Path

class Metadata(dict[str, typing.Any]):
    
    @classmethod
    def from_json_file(cls, path: Path) -> typing.Self:
        with Path(path).open('r') as f:
            return cls(json.load(f))


