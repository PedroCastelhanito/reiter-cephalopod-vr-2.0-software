import os,sys
from pathlib import Path
_dlls=[os.add_dll_directory(str(p)) for p in (Path(sys.base_prefix),Path(sys.base_prefix)/"DLLs",Path(sys.base_prefix)/"Library/bin") if p.is_dir()]
import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
