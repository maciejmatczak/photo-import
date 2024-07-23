import sys
from pathlib import Path

if __name__ in {"__main__", "__mp_main__"}:
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    print(Path(__file__).resolve().parent.parent)
    from photo_import.cmd import main

    main()
