import datetime
import shlex
import shutil
import typing as t
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import subprocess as sp

import click
from pydantic import BaseModel
from yaml import safe_load

ROOT = Path(__file__).resolve().parent.parent


class Scenario(BaseModel):
    source: Path


class Config(BaseModel):
    target_root: Path
    include: t.List[str]
    exclude: t.List[str]
    scenarios: t.Dict[str, Scenario]


def load_config() -> Config:
    with (ROOT / "etc" / "config.yml").open("r") as fh:
        data = safe_load(fh)
        return Config.model_validate(data)


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


def scan_source_dir(path: Path):
    found_extensions = defaultdict(int)
    oldest: t.Optional[datetime.datetime] = None
    newest: t.Optional[datetime.datetime] = None

    for current_path, directories, files in path.walk():
        for file_name in files:
            file = current_path / file_name
            found_extensions[file.suffix.lower().lstrip(".")] += 1
            mtime = datetime.datetime.fromtimestamp(file.lstat().st_mtime)
            if oldest is None:
                oldest = mtime
            if newest is None:
                newest = mtime

            if mtime < oldest:
                oldest = mtime
            if mtime > newest:
                newest = mtime

    return ScanResult(found_extensions=found_extensions, oldest=oldest, newest=newest)


@click.command()
@click.option("-s", "--scenario", required=True)
@click.option("-f", "--from", "from_", type=click.DateTime())
@click.option("-t", "--to", type=click.DateTime())
@click.option("-n", "--dry-run", is_flag=True, default=False)
def cmd(scenario: str, from_, to, dry_run: bool):
    config = load_config()

    try:
        scenario_data = config.scenarios[scenario]
    except KeyError:
        raise click.ClickException(
            f"Unknown scenario. Known scenarios:\n{', '.join(config.scenarios.keys())}"
        )

    target = config.target_root / scenario

    click.echo(f"scenario: {scenario}")
    click.echo(f"target: {target}")
    click.echo(f"source: {scenario_data.source}")
    click.echo("")

    scan_result = scan_source_dir(scenario_data.source)
    click.echo(scan_result)
    click.echo("")

    unexpected_formats = set(scan_result.found_extensions.keys()) - set(config.include)
    unexpected_formats -= set(config.exclude)
    if unexpected_formats:
        click.secho(
            "Found unexpected file extensions! These files will be skipped.",
            color="yellow",
        )
        click.echo(", ".join(unexpected_formats))
        click.confirm("Ok? Continue?", abort=True)

    cmd = [
        shutil.which("rclone"),
        "--log-level=DEBUG",
        "--ignore-case",
        "copy",
        # "--progress",
        # "-vvv",
    ]
    if dry_run:
        cmd.append("--dry-run")
    if from_:
        cmd += ["--max-age", from_.isoformat()]
    if to:
        cmd += ["--min-age", to.isoformat()]

    include_formats = set(config.include)

    for include_format in include_formats:
        cmd += ["--include", f"*.{include_format}"]

    cmd += [
        str(scenario_data.source),
        str(target),
    ]

    click.echo(shlex.join(cmd))
    click.echo("")
    click.confirm("Ok? Continue?", abort=True)
    sp.run(cmd)
