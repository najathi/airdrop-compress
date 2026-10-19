"""The interface every processor implements - built-in converters and plugins alike.

A processor receives a Job (one incoming file plus a private scratch folder) and
writes its results into that scratch folder. The engine then gives the results
unique names and moves them into the output folder, so a processor can never
overwrite another file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..settings import Settings


@dataclass
class Job:
    src: Path                 # the received file (read only - never modify it)
    workdir: Path             # scratch folder for results
    settings: Settings


@dataclass
class Output:
    path: Path                # file inside Job.workdir
    suffix: str               # final name = <stem><suffix>, e.g. ".webp", "-800w.webp"
    label: str = ""           # short description for the activity list ("AVIF", "800w")


@dataclass
class Result:
    outputs: list[Output] = field(default_factory=list)
    note: str = ""            # extra detail for the activity list ("Auto picked AVIF")


class SkipFile(Exception):
    """Not an error - the file was deliberately not converted (reason in the message)."""


class Processor(Protocol):
    id: str
    name: str
    kind: str                 # "image" | "document" | "plugin"

    def handles(self, path: Path, settings: Settings) -> bool: ...

    def process(self, job: Job) -> Result: ...
