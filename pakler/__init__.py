# SPDX-FileCopyrightText: 2021 Vincent Mallet <vmallet@gmail.com>
# SPDX-License-Identifier: MIT

"""Simple tool to manipulate PAK firmware files (list, extract, replace) for Swann and Reolink devices. See -h."""

import io
import struct
import zlib
from ctypes import sizeof
from enum import Enum, auto
from pathlib import Path
from zipfile import ZipExtFile

from pakler.structure import (
    quote_string,
    PAK32Header,
    PAK32Section,
    PAK64Header,
    PAK64Section,
    PAKPartition,
    PAKSHeader,
    PAKSSection
)

try:
    from ._version import __version__
except ModuleNotFoundError:
    __version__ = 'dev-local'

CHUNK_SIZE = 128 * 1024

PAK_MAGIC = 0x32725913
PAK_MAGIC_BYTES = PAK_MAGIC.to_bytes(4, "little")
PAK_MAGIC2 = 0x32725923
PAK_MAGIC2_BYTES = PAK_MAGIC2.to_bytes(4, "little")
PAKS_MAGIC = 0x50414B53
PAKS_MAGIC_BYTES = PAKS_MAGIC.to_bytes(4, "little")

PAK_MAGICS_BYTES = (PAK_MAGIC_BYTES, PAK_MAGIC2_BYTES, PAKS_MAGIC_BYTES)

HEADER_CRC_OFFSET = 4  # Offset of the CRC in the file
HEADER_CRC_OFFSET_64 = 8

PAKS_CRC_OFFSET = 0x04  # File CRC, covers everything from PAKS_CRC_START to the end of the file
PAKS_CRC_START = 0x08  # First byte covered by the file CRC (file_size field), i.e. right after the file CRC
PAKS_BOARD_CRC_OFFSET = 0x18  # Board CRC, covers everything from PAKS_BOARD_CRC_START to the end of the board
PAKS_BOARD_CRC_START = 0x1c  # First byte covered by the board CRC (hwver field), i.e. right after the board CRC


def paks_crc(data, crc=0):
    """CRC used by PAKS files: standard CRC-32 table, but without initial and final XOR (bc_gen_crc)."""
    return zlib.crc32(data, crc ^ 0xffffffff) ^ 0xffffffff


class PAKType(Enum):
    PAK32 = auto()
    PAK64 = auto()
    PAKS = auto()


class PAK:

    def __init__(self, fd, offset=0, closefd=True) -> None:
        self._fd = fd
        self._offset = offset
        self._closefd = closefd
        self._sections = []
        self._partitions = []
        self._pak_type = self._get_pak_type()
        self._header = self._read_header()
        self._read_file()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self._closefd:
            self.close()

    @property
    def magic(self):
        return self._header.magic

    @property
    def crc(self):
        return getattr(self._header, "crc32", 0)

    @property
    def type(self):
        return getattr(self._header, "type", 0)

    @property
    def header(self):
        return self._header

    @property
    def sections(self):
        return self._sections

    @property
    def partitions(self):
        return self._partitions

    @property
    def is64(self):
        return self._pak_type == PAKType.PAK64

    @property
    def pak_type(self):
        return self._pak_type

    def close(self):
        self._fd.close()
        self._fd = None

    def calc_crc(self):
        """Calculate the PAK file's CRC (which should match the header's CRC)."""
        if self._pak_type == PAKType.PAKS:
            return self._calc_paks_crc(PAKS_CRC_START)
        crc = 0xffffffff
        self._fd.seek(self._offset + self._sections[0].start)

        for chunk in iter(lambda: self._fd.read(CHUNK_SIZE), b''):
            crc = zlib.crc32(chunk, crc)

        buf = b'\2\0\0\0'  # TODO explain...
        crc = zlib.crc32(buf, crc)

        self._fd.seek(self._offset + sizeof(self._header))
        buf = self._fd.read(len(self.sections) * sizeof(self._sections[0]))
        crc = zlib.crc32(buf, crc)

        crc = crc ^ 0xffffffff
        return crc

    def calc_board_crc(self):
        """Calculate the CRC of the PAKS board (which should match the header's board CRC)."""
        return self._calc_paks_crc(PAKS_BOARD_CRC_START)

    def calc_section_crc(self, section):
        """Calculate the CRC of a PAKS section's data (which should match the section's checksum)."""
        crc = 0
        self._fd.seek(self._offset + section.start)
        remaining = section.len
        while remaining > 0:
            chunk = self._fd.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                raise Exception(f"Unexpected end of file in section {section.name}")
            crc = paks_crc(chunk, crc)
            remaining -= len(chunk)
        return crc

    def _calc_paks_crc(self, start):
        crc = 0
        self._fd.seek(self._offset + start)
        for chunk in iter(lambda: self._fd.read(CHUNK_SIZE), b''):
            crc = paks_crc(chunk, crc)
        return crc

    def extract_section(self, section):
        self._fd.seek(self._offset + section.start)
        return self._fd.read(section.len)

    def save_section(self, section, out_filename):
        self._fd.seek(self._offset + section.start)
        with open(out_filename, "wb") as fout:
            copy(self._fd, fout, section.len)

    def extract(self, output_dir: Path, include_empty=False, quiet=True):
        """Extract all sections from the PAK file into individual files."""
        if not output_dir.exists():
            output_dir.mkdir()

        if not output_dir.exists() or not output_dir.is_dir():
            raise Exception(f"Invalid output directory: {output_dir}")

        for num, section in enumerate(self.sections):
            out_filename = output_dir / make_section_filename(section, num)
            if section.len or include_empty:
                _print(f"Extracting section {num} ({section.len} bytes) into {out_filename}", quiet=quiet)
                self.save_section(section, out_filename)
            else:
                _print(f"Skipping empty section {num}", quiet=quiet)

    def debug_str(self):
        if self._pak_type == PAKType.PAKS:
            h = self._header
            return ('Header  magic=0x{:08x}  crc32=0x{:08x}  file_size=0x{:08x}  boards={}  board={}  fwver={}'
                    '  board_crc32=0x{:08x}  data_size=0x{:08x}  sections=<{}>').format(
                h.magic, h.crc32, h.file_size, h.nb_boards, quote_string(h.hwver), quote_string(h.fwver),
                h.board_crc32, h.data_size, len(self.sections))
        return 'Header  magic=0x{:08x}  crc32=0x{:08x}  type=0x{:08x}  sections=<{}>  mtd_parts=<{}>'.format(
            self.magic, self.crc, self.type, len(self.sections), len(self.partitions))

    def print_debug(self):
        print(self.debug_str())
        for num, section in enumerate(self.sections):
            print(f"    {section.debug_str(num)}")
        for part in self.partitions:
            print(f"    {part.debug_str()}")

    def _read_file(self):
        self._fd.seek(self._offset + sizeof(self._header))
        if self._pak_type == PAKType.PAKS:
            if self._header.ext_len:
                raise Exception(f"Unsupported PAKS file: ext_len={self._header.ext_len}")
            self._fd.seek(self._header.board_ext_len, 1)
            for _ in range(self._header.nb_sections):
                section = PAKSSection.from_fd(self._fd)
                section._start = self._fd.tell() + section.ext_len - self._offset
                self._sections.append(section)
                self._fd.seek(section.ext_len + section.len, 1)
        else:
            cls = PAK64Section if self.is64 else PAK32Section
            while True:
                section = cls.from_fd(self._fd)
                if self._sections and section.name == self._sections[0].name:
                    # We have reached (and read a part of) the first partition.
                    self._fd.seek(-sizeof(cls), 1)
                    break
                self._sections.append(section)
            for _ in range(len(self._sections)):
                self._partitions.append(PAKPartition.from_fd(self._fd))

    def _is_64bit(self):
        """Determine the firmware's target bitness.

        Firmwares for 64-bit devices have 8 bytes long header fields
        instead of 4, with zero padding. That means the three "extra"
        groups of bytes are all zeroes. For 32-bit devices, the first
        group corresponds to the CRC and the second is a part of the
        first section's name, therefore they can never be all zeroes.
        """
        fmt = "<IIIIII"
        struct_size = struct.calcsize(fmt)
        self._fd.seek(self._offset)
        _, group1, _, group2, _, group3 = struct.unpack(fmt, self._fd.read(struct_size))
        return sum((group1, group2, group3)) == 0

    def _get_pak_type(self):
        self._fd.seek(self._offset)
        magic = self._fd.read(4)
        if not is_pak_file(magic):
            raise Exception("Not a PAK file")
        if magic == PAKS_MAGIC_BYTES:
            return PAKType.PAKS
        return PAKType.PAK64 if self._is_64bit() else PAKType.PAK32

    def _read_header(self):
        """Read and parse the header of a PAK firmware file.

        :return: the parsed Header object
        """
        self._fd.seek(self._offset)
        if self._pak_type == PAKType.PAKS:
            return PAKSHeader.from_fd(self._fd)
        cls = PAK64Header if self.is64 else PAK32Header
        return cls.from_fd(self._fd)

    @classmethod
    def from_fd(cls, fd, offset=0, closefd=True):
        return cls(fd, offset, closefd)

    @classmethod
    def from_bytes(cls, bytes_, offset=0):
        return cls.from_fd(io.BytesIO(bytes_), offset)

    @classmethod
    def from_file(cls, path, offset=0):
        return cls.from_fd(open(path, "rb"), offset)


def check_paks_crc(pak, filename):
    """Check the file, board and section CRCs of a PAKS file."""
    ok = True
    for section in pak.sections:
        crc = pak.calc_section_crc(section)
        if crc != section.checksum:
            print(f"CRC MISMATCH, section: {section.name}, section.crc=0x{section.checksum:08x}, got=0x{crc:08x}")
            ok = False
    for name, expected, crc in (("board", pak.header.board_crc32, pak.calc_board_crc()),
                                ("file", pak.header.crc32, pak.calc_crc())):
        if crc != expected:
            print(f"CRC MISMATCH, {name}: {filename}, header.crc=0x{expected:08x}, got=0x{crc:08x}")
            ok = False
    if ok:
        print(f"File passes CRC check: {filename}")
    return ok


def check_crc(filename):
    """Check the PAK file's crc matches the crc in its header."""
    if isinstance(filename, ZipExtFile):
        with PAK.from_fd(filename) as pak:
            if pak.pak_type == PAKType.PAKS:
                return check_paks_crc(pak, filename.name)
        filename.seek(0)
    else:
        with PAK.from_file(filename) as pak:
            if pak.pak_type == PAKType.PAKS:
                return check_paks_crc(pak, filename)

    if isinstance(filename, ZipExtFile):
        with PAK.from_fd(filename) as pak:
            header = pak.header
            crc = pak.calc_crc()
        filename = filename.name
    else:
        with PAK.from_file(filename) as pak:
            header = pak.header
            crc = pak.calc_crc()

    if crc != header.crc32:
        print(f"CRC MISMATCH, file: {filename}, header.crc=0x{header.crc32:08x}, got=0x{crc:08x}")
        return False

    print(f"File passes CRC check: {filename}")
    return True


def update_crc(filename):
    """Recompute the PAK file's crc and store it in its header.

    Note: the PAK file is modified by this operation.
    """
    with PAK.from_file(filename) as pak:
        crc = pak.calc_crc()
        offset = HEADER_CRC_OFFSET_64 if pak.is64 else HEADER_CRC_OFFSET
        fmt = "<Q" if pak.is64 else "<I"

    with open(filename, "r+b") as f:
        f.seek(offset)
        f.write(struct.pack(fmt, crc))


def make_section_filename(section, num):
    # TODO: should sanitize section name before turning it into a filename
    if section.name:
        return f"{num:02}_{section.name}.bin"
    return f"{num:02}.bin"


def copy(fin, fout, length):
    chunk_size = CHUNK_SIZE
    while length > 0:
        if length < chunk_size:
            chunk_size = length
        chunk = fin.read(chunk_size)
        if not chunk:
            raise Exception(f"Read error with chunk_size={chunk_size} length={length}")
        fout.write(chunk)
        length -= chunk_size


def update_paks_crc(filename):
    """Recompute the board and file CRCs of a PAKS file and store them in its header.
    Section CRCs are not touched.
    """
    with PAK.from_file(filename) as pak:
        if pak.header.nb_boards != 1:
            raise Exception(f"Unsupported PAKS file containing multiple boards: {pak.header.nb_boards} boards")
        board_crc = pak.calc_board_crc()
    with open(filename, "r+b") as f:
        f.seek(PAKS_BOARD_CRC_OFFSET)
        f.write(struct.pack("<I", board_crc))
    # The file CRC covers the board CRC, so it has to be computed afterwards.
    with PAK.from_file(filename) as pak:
        crc = pak.calc_crc()
    with open(filename, "r+b") as f:
        f.seek(PAKS_CRC_OFFSET)
        f.write(struct.pack("<I", crc))


def replace_paks_section(filename, section_file: Path, section_num, output_file: Path, section_version=None,
                         fw_version=None):
    """Copy the given PAKS file into new output_file, replacing the specified section and updating all CRCs.

    :param section_version: new version string of the section. The device skips sections whose name and
        version match what is already installed, so a modified section needs a new version to be flashed.
    :param fw_version: new firmware version string of the board. The device refuses the whole update if it
        matches the currently installed firmware version.
    """
    with PAK.from_file(filename) as pak:
        if pak.header.nb_boards != 1:
            raise Exception(f"Unsupported PAKS file containing multiple boards: {pak.header.nb_boards} boards")
        if section_num < 0 or section_num >= len(pak.sections):
            raise Exception(f"Invalid section number: {section_num} (should be between 0 and {len(pak.sections) - 1})")
        replaced = pak.sections[section_num]
        section_len = section_file.stat().st_size
        if replaced.partition_size and section_len > replaced.partition_size:
            raise Exception(f"Section file too big: {section_len} bytes > partition size {replaced.partition_size}")
        if section_version is not None and len(section_version.encode()) >= PAKSSection._version.size:
            raise Exception(f"Section version too long: {section_version!r}")
        if fw_version is not None and len(fw_version.encode()) >= PAKSHeader._fwver.size:
            raise Exception(f"Firmware version too long: {fw_version!r}")

        print(f"Input            : {filename}")
        print(f"Output           : {output_file}")
        print(f"Replacing section: {section_num} ({replaced.name})")
        print(f"Replacement file : {section_file}")

        with open(section_file, "rb") as fsection, open(output_file, "wb") as fout:
            header = pak.header
            fout.write(bytes(header))
            pak._fd.seek(pak._offset + sizeof(header))
            copy(pak._fd, fout, header.board_ext_len)
            for num, section in enumerate(pak.sections):
                pak._fd.seek(pak._offset + section.start - section.ext_len)
                section_pos = fout.tell()
                fout.write(bytes(section))
                copy(pak._fd, fout, section.ext_len)
                if num == section_num:
                    print(f"Replacing section {num} ({section.len} bytes) with {section_len} bytes")
                    crc = 0
                    for chunk in iter(lambda: fsection.read(CHUNK_SIZE), b''):
                        crc = paks_crc(chunk, crc)
                        fout.write(chunk)
                    section._len = section_len
                    section._checksum = crc
                    if section_version is not None:
                        section._version = section_version.encode()
                    end = fout.tell()
                    fout.seek(section_pos)
                    fout.write(bytes(section))
                    fout.seek(end)
                else:
                    copy(pak._fd, fout, section.len)
            header._file_size = fout.tell()
            header._data_size = fout.tell() - sizeof(header)
            if fw_version is not None:
                header._fwver = fw_version.encode()
            fout.seek(0)
            fout.write(bytes(header))

    print("Updating CRC...")
    update_paks_crc(output_file)

    print("Replacement completed. New header: ")
    with PAK.from_file(output_file) as pak:
        pak.print_debug()


def replace_section(filename, section_file: Path, section_num, output_file: Path, section_version=None,
                    fw_version=None):
    """Copy the given PAK file into new output_file, replacing the specified section.

    :param filename: name of the input PAK firmware file
    :param section_file: name of the file containing the section to be swapped-in
    :param section_num: number of the section to be replaced
    :param output_file: name of the output file which will contained the modified PAK file
    :param section_version: new version string of the section (PAKS only)
    :param fw_version: new firmware version string of the board (PAKS only)
    """
    if not section_file.is_file():
        raise Exception(f"Section file doesn't exist or is not a file: {section_file}")

    with PAK.from_file(filename) as pak:
        pak_type = pak.pak_type
        section_count = len(pak.sections)
    if pak_type == PAKType.PAKS:
        return replace_paks_section(filename, section_file, section_num, output_file, section_version, fw_version)
    if section_version is not None or fw_version is not None:
        raise Exception("Setting the section or firmware version is only supported for PAKS files")

    section_len = section_file.stat().st_size

    if section_num < 0 or section_num >= section_count:
        raise Exception(f"Invalid section number: {section_num} (should be between 0 and {section_count})")

    print(f"Input            : {filename}")
    print(f"Output           : {output_file}")
    print(f"Replacing section: {section_num}")
    print(f"Replacement file : {section_file}")

    with PAK.from_file(filename) as pak, open(section_file, "rb") as fsection, open(output_file, "wb") as fout:
        metadata_size = sizeof(pak.header) + section_count * (sizeof(pak.sections[0]) + sizeof(pak.partitions[0]))
        # Write placeholder header
        fout.write(bytearray(metadata_size))

        for num, section in enumerate(pak.sections):
            pak._fd.seek(section.start)
            section._start = fout.tell()
            if num == section_num:
                print(f"Replacing section {num} ({section.len} bytes) with {section_len} bytes")
                copy(fsection, fout, section_len)
                section._len = section_len
            else:
                print(f"Copying section {num} ({section.len} bytes)")
                copy(pak._fd, fout, section.len)

        print(f"Writing header... ({metadata_size} bytes)")
        fout.seek(0)
        fout.write(bytes(pak.header))
        for section in pak.sections:
            fout.write(bytes(section))
        for partition in pak.partitions:
            fout.write(bytes(partition))

    print("Updating CRC...")
    update_crc(output_file)

    print("Replacement completed. New header: ")
    with PAK.from_file(output_file) as pak:
        pak.print_debug()


def _print(*args, **kwargs):
    if not kwargs.pop("quiet", False):
        print(*args, **kwargs)


def _is_pak(file):
    return file.read(4) in PAK_MAGICS_BYTES


def is_pak_file(fileorbytes):
    """See if a file is a PAK file by checking the magic number.

    The argument may be a bytes object, a file or file-like object.
    """
    if isinstance(fileorbytes, (bytes, bytearray)):
        return _is_pak(io.BytesIO(fileorbytes[:4]))
    try:
        if hasattr(fileorbytes, "read"):
            return _is_pak(fileorbytes)
        else:
            with open(fileorbytes, "rb") as f:
                return _is_pak(f)
    except OSError:
        return False
