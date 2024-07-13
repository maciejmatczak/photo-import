from pathlib import Path
import sys


if __name__ == "__main__":
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    print(Path(__file__).resolve().parent.parent)
    from photo_import.cmd import cmd

    cmd()
