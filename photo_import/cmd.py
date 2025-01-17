import datetime
import shlex
import shutil
import subprocess as sp
import sys
import typing as t
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from time import sleep

import click
import psutil
import questionary
from psutil._common import bytes2human
from pydantic import BaseModel, ValidationError, field_validator
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.pretty import pprint
from yaml import safe_load

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "mm-photo-import"


console = Console()


class Scenario(BaseModel):
    folder: str
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


def write_and_rotate(path: Path, line, max_lines=10):
    try:
        raw = path.read_text().splitlines()
    except FileNotFoundError:
        raw = list()

    content = deque(raw, max_lines)
    content.append(line)
    path.write_text("\n".join(content))


def spinner(msg=""):
    with console.status(msg):
        sleep(1)


@dataclass
class App:
    app_dir: Path
    import_sessions_dir: Path
    app_config: AppConfig
    app_config_path: Path
    user_config: UserConfig
    user_config_path: Path


@click.group(invoke_without_command=True)
@click.pass_context
def cmd(ctx):
    print(Panel("[bold blue]Setting up"))
    print("")

    app_dir = Path(click.get_app_dir(APP_NAME))
    app_dir.mkdir(exist_ok=True)
    import_sessions_dir = app_dir / "import-sessions"
    import_sessions_dir.mkdir(exist_ok=True)

    print(f"[magenta]App directory[/]: {app_dir}")

    app_config_path = app_dir / "config.yml"

    print(f"[magenta]App config path[/]: {app_config_path}")

    spinner("reading app config...")

    if not app_config_path.exists():
        print("[red]App config doesn't exist!")
        sys.exit(1)

    try:
        app_config = load_config(app_config_path, AppConfig)
    except ValidationError as exception:
        print(str(exception))
        sys.exit(1)

    print("")
    print("[magenta]App config:")
    pprint(app_config.model_dump(mode="json"), expand_all=True)

    spinner("reading user config...")

    try:
        user_config = load_config(app_config.user_config, UserConfig)
    except ValidationError as exception:
        print(f"[red]Invalid user config: {app_config.user_config}")
        print(str(exception))
        sys.exit(1)

    print("")
    print(f"[magenta]User config[/]: {app_config_path}")
    pprint(user_config.model_dump(mode="json"), expand_all=True)

    ctx.obj = App(
        app_dir=app_dir,
        import_sessions_dir=import_sessions_dir,
        user_config=user_config,
        user_config_path=app_config.user_config,
        app_config=app_config,
        app_config_path=app_config_path,
    )

    if ctx.invoked_subcommand is not None:
        spinner("preparing...")
        print("")


@cmd.command(name="import")
@click.option("-f", "--from", "from_", type=click.DateTime())
@click.option("-t", "--to", type=click.DateTime())
@click.option("-n", "--dry-run", is_flag=True, default=False)
@click.argument("scenario")
@click.pass_obj
def import_(
    app: App,
    scenario: str,
    from_: datetime.datetime | None,
    to: datetime.datetime | None,
    dry_run: bool,
):
    print(Panel("[blue]Reading data"))
    print("")

    try:
        scenario_data = app.user_config.scenarios[scenario]
    except KeyError:
        print(
            f"[red]Unknown scenario. Known scenarios:\n{', '.join(app.user_config.scenarios.keys())}"
        )
        sys.exit(1)

    target = app.user_config.target_root / scenario_data.folder

    options = {}
    for partition in psutil.disk_partitions():
        usage = psutil.disk_usage(partition.mountpoint)
        partition_str = f"{partition.device}: {bytes2human(usage.used)} / {bytes2human(usage.total)}"
        options[partition_str] = partition.mountpoint

    choice = questionary.select(
        "Which storage device to import photos from?", choices=options
    ).ask()
    if choice is None:
        raise click.Abort

    history_file = app.import_sessions_dir / scenario
    try:
        history = history_file.read_text().splitlines()
    except FileNotFoundError:
        history = list()

    print("")
    print("[magenta]History:")
    for e in history:
        print(f" - {e}")
    print("")

    spinner("calculating...")

    scenario_source = Path(options[choice]) / scenario_data.source

    if not scenario_source.exists():
        print(f"[red]Scenario import path doesn't exist: {scenario_source}")
        print(f"Review your config: [green]{app.user_config_path}")
        sys.exit(1)

    print(f"[magenta]scenario[/]: {scenario}")
    print(f"[magenta]source[/]: {scenario_source}")
    print(f"[magenta]target[/]: {target}")

    spinner("scanning dir...")
    scan_result = scan_source_dir(scenario_source, from_, to)

    print("")
    print("Found files:")
    for ext, count in scan_result.found_extensions.items():
        print(f"  [magenta]{ext}[/]: {count}")
    o = scan_result.oldest.isoformat(sep=" ") if scan_result.oldest else "?"
    n = scan_result.newest.isoformat(sep=" ") if scan_result.newest else "?"
    print(f"[magenta]oldest[/]: {o}")
    print(f"[magenta]newest[/]: {n}")

    print("")

    # we expect the extensions we want to initially include, but scan dir might find more
    unexpected_extensions = set(scan_result.found_extensions.keys()) - set(
        app.user_config.include
    )

    # in case of often cases, user can silence the warnings for certain extensions
    unexpected_extensions -= set(app.user_config.exclude)

    if unexpected_extensions:
        print("[yellow]Found unexpected file extensions! These files will be skipped.")
        print(unexpected_extensions)

    click.confirm("Ok? Continue?", abort=True)

    print("")
    print(Panel("[blue]Importing data"))
    print("")

    cmd = [
        shutil.which("rclone"),
        "--ignore-case",
        "copy",
        "-v",
    ]
    if dry_run:
        cmd.append("--dry-run")
    if from_:
        cmd += ["--max-age", from_.isoformat()]
    if to:
        cmd += ["--min-age", to.isoformat()]

    include_extensions = set(app.user_config.include)

    for include_extension in include_extensions:
        cmd += ["--include", f"*.{include_extension}"]

    cmd += [
        str(scenario_source),
        str(target),
    ]

    spinner("rendering command...")

    print("Command:")
    print(" ", shlex.join(cmd))
    print("")

    click.confirm("Ok? Continue?", abort=True)
    print("")

    history_record = []
    if from_:
        history_record.append(f"from: {from_} (user)")
    else:
        history_record.append(f"from: {scan_result.oldest} (auto)")

    if to:
        history_record.append(f"to: {to} (user)")
    else:
        history_record.append(f"to: {scan_result.newest} (auto)")

    write_and_rotate(history_file, ";  ".join(history_record))

    sp.run(cmd)
