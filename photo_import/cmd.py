import datetime
import random
import shutil
import subprocess as sp
import sys
import typing as t
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, field_validator
from PySide6 import QtCore, QtGui, QtWidgets
from yaml import safe_load

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "mm-photo-import"


class Scenario(BaseModel):
    source: Path


class UserConfig(BaseModel):
    target_root: Path
    include: t.List[str]
    exclude: t.List[str]
    scenarios: t.Dict[str, Scenario]


class AppConfig(BaseModel):
    user_config: Path

    @field_validator("user_config")
    @classmethod
    def path_must_exist(cls, v: Path) -> Path:
        if not v.exists():
            raise ValueError("path must exist")
        return v


T = t.TypeVar("T", bound=BaseModel)


def load_config(path: Path, config_class: t.Type[T]) -> T:
    with path.open("r") as fh:
        data = safe_load(fh)
        return config_class.model_validate(data)


@dataclass
class ScanResult:
    found_extensions: t.Dict[str, int]
    oldest: datetime.datetime | None
    newest: datetime.datetime | None


def scan_source_dir(path: Path, from_: datetime.datetime, to: datetime.datetime):
    found_extensions = defaultdict(int)
    oldest: t.Optional[datetime.datetime] = None
    newest: t.Optional[datetime.datetime] = None

    cmd = [
        shutil.which("rclone"),
        "--ignore-case",
        "--files-only",
        "--recursive",
    ]

    if from_:
        cmd += ["--max-age", from_.isoformat()]
    if to:
        cmd += ["--min-age", to.isoformat()]

    cmd += [
        "--format",
        "tp",
        "lsf",
        str(path),
    ]

    proc = sp.run(cmd, text=True, capture_output=True)
    for line in proc.stdout.splitlines():
        timestamp_str, file_path_str = line.split(";")
        file_path = Path(file_path_str)
        found_extensions[file_path.suffix.lower().lstrip(".")] += 1
        mtime = datetime.datetime.fromisoformat(timestamp_str)

        if oldest is None:
            oldest = mtime
        if newest is None:
            newest = mtime

        if mtime < oldest:
            oldest = mtime
        if mtime > newest:
            newest = mtime

    return ScanResult(found_extensions=found_extensions, oldest=oldest, newest=newest)


class AlertDialog(QtWidgets.QMessageBox):
    def __init__(self, message, details, window_size=None, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Alert")
        self.setText(message)
        self.setDetailedText(details)
        self.setStandardButtons(QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
        self.setIcon(QtWidgets.QMessageBox.Warning)

        if window_size:
            self.setGeometry(window_size)


class App(QtWidgets.QApplication):
    def __init__(self, argv: list[str]) -> None:
        self.setOrganizationName("MMco")
        self.setApplicationName("Photo Import")

        QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)

        super().__init__(argv)

    # @QtCore.Slot(str, str)
    # def alert(self, message, details):
    #     AlertDialog(message=message, details=details).show()

    user_config: UserConfig
    user_config_path: Path


class Settings(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        settings = QtCore.QSettings()

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        form = QtWidgets.QWidget()
        form_layout = QtWidgets.QFormLayout(form)

        self.user_config = QtWidgets.QLineEdit(
            settings.value("user_config_path", defaultValue="?", type=str)
        )
        form_layout.addRow("User config", self.user_config)

        layout.addWidget(form)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )

        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def accept(self):
        settings = QtCore.QSettings()
        settings.setValue("user_config_path", self.user_config)
        super().accept()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.hello = ["Hallo Welt", "Hei maailma", "Hola Mundo", "Привет мир"]

        self.button = QtWidgets.QPushButton("Click me!")
        self.text = QtWidgets.QLabel("Hello World", alignment=QtCore.Qt.AlignCenter)

        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        layout = QtWidgets.QVBoxLayout(central_widget)
        layout.addWidget(self.text)
        layout.addWidget(self.button)

        self.button.clicked.connect(self.magic)

        toolbar = QtWidgets.QToolBar("Main toolbar")
        self.addToolBar(toolbar)

        open_settings_action = QtGui.QAction("Settings", self)
        open_settings_action.triggered.connect(self.open_settings)
        toolbar.addAction(open_settings_action)

    @QtCore.Slot()
    def magic(self):
        self.text.setText(random.choice(self.hello))

    def open_settings(self, s):
        dialog = Settings(self)
        print(dialog.exec())


def run():
    app = App(sys.argv)

    widget = MainWindow()
    widget.resize(800, 600)
    widget.show()

    sys.exit(app.exec())


# @click.command(invoke_without_command=True)
# @click.pass_context
# def cmd(ctx):
# print("[blue]Setting up")
# print("")

# app_dir = Path(click.get_app_dir(APP_NAME))
# app_dir.mkdir(exist_ok=True)

# app_config_path = app_dir / "config.yml"

# if not app_config_path.exists():
#     print(f"[red]{app_config_path} doesn't exist!")
#     sys.exit(1)

# try:
#     app_config = load_config(app_config_path, AppConfig)
# except ValidationError as exception:
#     print(str(exception))
#     sys.exit(1)

# pprint(app_config.model_dump(mode="json"), expand_all=True)

# try:
#     user_config = load_config(app_config.user_config, UserConfig)
# except ValidationError as exception:
#     print(f"[red]Invalid user config: {app_config.user_config}")
#     print(str(exception))
#     sys.exit(1)

# pprint(user_config.model_dump(mode="json"), expand_all=True)

# ctx.obj = App(
#     user_config=user_config,
#     user_config_path=app_config.user_config,
#     app_config=app_config,
#     app_config_path=app_config_path,
# )

# if ctx.invoked_subcommand is not None:
#     print("")


# @cmd.command(name="import")
# @click.option("-s", "--scenario", required=False)
# @click.option("-f", "--from", "from_", type=click.DateTime())
# @click.option("-t", "--to", type=click.DateTime())
# @click.option("-n", "--dry-run", is_flag=True, default=False)
# @click.argument("scenario")
# @click.pass_obj
# def import_(
#     app: App,
#     scenario: str,
#     from_: datetime.datetime,
#     to: datetime.datetime,
#     dry_run: bool,
# ):
#     print("[blue]Reading data")
#     print("")

#     try:
#         scenario_data = app.user_config.scenarios[scenario]
#     except KeyError:
#         print(
#             f"[red]Unknown scenario. Known scenarios:\n{', '.join(app.user_config.scenarios.keys())}"
#         )
#         sys.exit(1)

#     target = app.user_config.target_root / scenario

#     options = {}
#     for partition in psutil.disk_partitions():
#         usage = psutil.disk_usage(partition.mountpoint)
#         partition_str = f"{partition.device}: {bytes2human(usage.used)} / {bytes2human(usage.total)}"
#         options[partition_str] = partition.mountpoint

#     choice = questionary.select(
#         "Which storage device to import photos from?", choices=options
#     ).ask()

#     scenario_source = Path(options[choice]) / scenario_data.source

#     if not scenario_source.exists():
#         print(f"[red]Scenario import path doesn't exist: {scenario_source}")
#         print(f"Review your config: [green]{app.user_config_path}")
#         sys.exit(1)

#     print("")
#     print(f"scenario: [magenta]{scenario}")
#     print(f"source: [magenta]{scenario_source}")
#     print(f"target: [magenta]{target}")
#     print("")

#     print("Scanning dir...\n")
#     scan_result = scan_source_dir(scenario_source, from_, to)

#     print("Found extensions:")
#     for ext, count in scan_result.found_extensions.items():
#         print(f"  {ext}: [magenta]{count}")
#     o = scan_result.oldest.isoformat(sep=" ") if scan_result.oldest else "?"
#     n = scan_result.newest.isoformat(sep=" ") if scan_result.newest else "?"
#     print(f"oldest: [magenta]{o}")
#     print(f"newest: [magenta]{n}")

#     print("")

#     unexpected_formats = set(scan_result.found_extensions.keys()) - set(
#         app.user_config.include
#     )

#     unexpected_formats -= set(app.user_config.exclude)
#     if unexpected_formats:
#         print("[yellow]Found unexpected file extensions! These files will be skipped.")
#         print(unexpected_formats)

#     click.confirm("Ok? Continue?", abort=True)

#     print("")
#     print("[blue]Importing data")
#     print("")

#     cmd = [
#         shutil.which("rclone"),
#         "--ignore-case",
#         "copy",
#         "-vv",
#     ]
#     if dry_run:
#         cmd.append("--dry-run")
#     if from_:
#         cmd += ["--max-age", from_.isoformat()]
#     if to:
#         cmd += ["--min-age", to.isoformat()]

#     include_formats = set(app.user_config.include)

#     for include_format in include_formats:
#         cmd += ["--include", f"*.{include_format}"]

#     cmd += [
#         str(scenario_source),
#         str(target),
#     ]
#     print("Command:")
#     print(" ", shlex.join(cmd))
#     print("")

#     click.confirm("Ok? Continue?", abort=True)

#     sp.run(cmd)
#     click.confirm("Ok? Continue?", abort=True)

#     sp.run(cmd)
#     sp.run(cmd)
#     sp.run(cmd)
#     sp.run(cmd)
