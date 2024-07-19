import datetime
import shlex
import shutil
import subprocess as sp
import sys
import typing as t
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import click
from pydantic import BaseModel, ValidationError, field_validator
from rich import print
from rich.pretty import pprint
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
    oldest: datetime.datetime
    newest: datetime.datetime

    def __str__(self) -> str:
        msg = "Found extensions:\n"
        for ext, count in self.found_extensions.items():
            msg += f"  {ext}: {count}\n"
        msg += f"oldest: {self.oldest.isoformat()}\n"
        msg += f"newest: {self.newest.isoformat()}"

        return msg


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


@dataclass
class App:
    app_config: AppConfig
    user_config: UserConfig


@click.group(invoke_without_command=True)
@click.pass_context
def cmd(ctx):
    print("[blue]Setting up")
    print("")
    app_dir = Path(click.get_app_dir(APP_NAME))
    app_dir.mkdir(exist_ok=True)

    app_config_path = app_dir / "config.yml"

    if not app_config_path.exists():
        print(f"[red]{app_config_path} doesn't exist!")
        sys.exit(1)

    try:
        app_config = load_config(app_config_path, AppConfig)
    except ValidationError as exception:
        print(str(exception))
        sys.exit(1)

    pprint(app_config.model_dump(mode="json"), expand_all=True)

    try:
        user_config = load_config(app_config.user_config, UserConfig)
    except ValidationError as exception:
        print(f"[red]Invalid user config: {app_config.user_config}")
        print(str(exception))
        sys.exit(1)

    pprint(user_config.model_dump(mode="json"), expand_all=True)

    ctx.obj = App(user_config=user_config, app_config=app_config)
    if ctx.invoked_subcommand is not None:
        print("")


@cmd.command(name="import")
@click.option("-s", "--scenario", required=False)
@click.option("-f", "--from", "from_", type=click.DateTime())
@click.option("-t", "--to", type=click.DateTime())
@click.option("-n", "--dry-run", is_flag=True, default=False)
@click.argument("scenario")
@click.pass_obj
def import_(
    app: App,
    scenario: str,
    from_: datetime.datetime,
    to: datetime.datetime,
    dry_run: bool,
):
    print("[blue]Reading data")
    print("")

    try:
        scenario_data = app.user_config.scenarios[scenario]
    except KeyError:
        print(
            f"[red]Unknown scenario. Known scenarios:\n{', '.join(app.user_config.scenarios.keys())}"
        )
        sys.exit(1)

    target = app.user_config.target_root / scenario

    print(f"scenario: [magenta]{scenario}")
    print(f"source: [magenta]{scenario_data.source}")
    print(f"target: [magenta]{target}")
    print("")

    scan_result = scan_source_dir(scenario_data.source, from_, to)

    print("Found extensions:")
    for ext, count in scan_result.found_extensions.items():
        print(f"  {ext}: [magenta]{count}")
    print(f"oldest: [magenta]{scan_result.oldest.isoformat(sep=' ')}")
    print(f"newest: [magenta]{scan_result.newest.isoformat(sep=' ')}")

    print("")

    unexpected_formats = set(scan_result.found_extensions.keys()) - set(
        app.user_config.include
    )

    unexpected_formats -= set(app.user_config.exclude)
    if unexpected_formats:
        print("[yellow]Found unexpected file extensions! These files will be skipped.")
        print(unexpected_formats)

    click.confirm("Ok? Continue?", abort=True)

    print("")
    print("[blue]Importing data")
    print("")

    cmd = [
        shutil.which("rclone"),
        "--ignore-case",
        "copy",
        "-vv",
    ]
    if dry_run:
        cmd.append("--dry-run")
    if from_:
        cmd += ["--max-age", from_.isoformat()]
    if to:
        cmd += ["--min-age", to.isoformat()]

    include_formats = set(app.user_config.include)

    for include_format in include_formats:
        cmd += ["--include", f"*.{include_format}"]

    cmd += [
        str(scenario_data.source),
        str(target),
    ]
    print("Command:")
    print(" ", shlex.join(cmd))
    print("")

    click.confirm("Ok? Continue?", abort=True)

    sp.run(cmd)
