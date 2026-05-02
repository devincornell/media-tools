import dataclasses
import typing
import zipfile
import tempfile
import requests
from pathlib import Path

import dataclasses
import typing
import zipfile
import tempfile
import requests
from pathlib import Path

@dataclasses.dataclass(frozen=True)
class RemoteZipDownloader:
    url: str
    #zip_filename: str
    path: Path
    _temp_dir: tempfile.TemporaryDirectory

    @classmethod
    def from_url(cls, url: str) -> typing.Self:
        ''''''
        tmp_zip_filename: str = "archive.zip"

        # 1. Setup encapsulated infrastructure
        td = tempfile.TemporaryDirectory()
        temp_path = Path(td.name)
        zip_path = temp_path / tmp_zip_filename

        # 2. Download directly to memory and write to disk
        response = requests.get(url)
        zip_path.write_bytes(response.content)

        # 3. Extract the archive
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(temp_path)
            
        # 4. Delete the raw zip file now that extraction is complete
        zip_path.unlink()

        # 5. Instantiation
        return cls(
            url=url,
            #zip_filename=tmp_zip_filename,
            path=temp_path,
            _temp_dir=td
        )

    def cleanup(self) -> None:
        """Manually clean up the temp directory when done."""
        self._temp_dir.cleanup()