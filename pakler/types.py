import argparse
import array
import io
import mmap
from os import PathLike
from pathlib import Path
from typing import BinaryIO, Union

# io.BufferedIOBase is for ZipExtFile
IOBytes = Union[BinaryIO, io.BufferedIOBase]

StrOrBytesPath = Union[str, bytes, "PathLike[str]", "PathLike[bytes]"]
FileDescriptorOrPath = Union[int, StrOrBytesPath]

ReadOnlyBuffer = bytes
WriteableBuffer = Union[bytearray, memoryview, array.array, mmap.mmap]
ReadableBuffer = Union[ReadOnlyBuffer, WriteableBuffer]

Unused = object


class MainArgs(argparse.Namespace):
    list: bool
    replace: bool
    extract: bool
    section_file: Path
    section_num: int
    output_pak: Path
    output_dir: Path
    include_empty: bool
    filename: Path
