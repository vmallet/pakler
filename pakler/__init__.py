# SPDX-FileCopyrightText: 2021 Vincent Mallet <vmallet@gmail.com>
# SPDX-License-Identifier: MIT

"""Simple tool to manipulate PAK firmware files (list, extract, replace) for Swann and Reolink devices. See -h."""

import io
import struct
import zlib
from pathlib import Path
from typing import Optional
from zipfile import ZipExtFile

try:
    from ._version import __version__
except ModuleNotFoundError:
    __version__ = 'dev-local'

CHUNK_SIZE = 128 * 1024

PAK_MAGIC = 0x32725913
PAK_MAGIC_BYTES = PAK_MAGIC.to_bytes(4, "little")

SECTION_FORMAT = "<32s24sII"
SECTION_FORMAT_64 = "<32s24sQQ"
SECTION_FIELDS = ['name',  # TODO: Docs
                  'version',
                  'start',
                  'len']
SECTION_STRINGS = ['name', 'version']
SECTION_SIZE = struct.calcsize(SECTION_FORMAT)  # 64
SECTION_SIZE_64 = struct.calcsize(SECTION_FORMAT_64)  # 72

MTD_PART_FORMAT = "<32sI32sII"
MTD_PART_FIELDS = ['name',
                   'a',
                   'mtd',
                   'start',
                   'len']
MTD_PART_STRINGS = ['name',
                    'mtd']
MTD_PART_SIZE = struct.calcsize(MTD_PART_FORMAT)  # 76

HEADER_FORMAT = "<III"
HEADER_FORMAT_64 = "<QQQ"
HEADER_FIELDS = ['magic',
                 'crc32',
                 'type']
HEADER_CRC_OFFSET = 4  # Offset of the CRC in the file
HEADER_CRC_OFFSET_64 = 8
HEADER_HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # Size of the header's header (first 12 bytes)
HEADER_HEADER_SIZE_64 = struct.calcsize(HEADER_FORMAT_64)  # First 24 bytes


def calc_header_size(section_count, mtd_part_count=None, is64=False):
    """Return the calculated size of the header given a number of sections (and optionally of mtd_parts)."""
    if not mtd_part_count:
        mtd_part_count = section_count

    if is64:
        return HEADER_HEADER_SIZE_64 + (section_count * SECTION_SIZE_64) + (mtd_part_count * MTD_PART_SIZE)
    return HEADER_HEADER_SIZE + (section_count * SECTION_SIZE) + (mtd_part_count * MTD_PART_SIZE)


def decode_strings(obj, fields):
    """Decode (utf-8) 0-padded binary strings in the obj's fields to normal strings."""
    for field in fields:
        cstr = getattr(obj, field)
        fixed = cstr.rstrip(b'\0').decode('utf-8')
        setattr(obj, field, fixed)


def quote_string(string):
    """Return the string surrounded with double-quotes."""
    return f'"{string}"'


class Section:
    """A header's 'section'."""

    def __init__(self, buf, num, is64=False):
        self.num = num
        self.name = None
        self.version = None
        self.start = 0
        self.len = 0
        self.section_format = SECTION_FORMAT_64 if is64 else SECTION_FORMAT

        fields = zip(SECTION_FIELDS, struct.unpack(self.section_format, buf))
        for key, val in fields:
            setattr(self, key, val)

        decode_strings(self, SECTION_STRINGS)

    def __repr__(self):
        return f"{self.__class__.__qualname__}({self.name!r})"

    def __iter__(self):
        for key in dir(self):
            if not key.startswith('_'):
                yield key, getattr(self, key)

    def __bytes__(self):
        return struct.pack(self.section_format, self.name.encode(), self.version.encode(), self.start, self.len)

    def debug_str(self):
        return 'Section {:2} name={:16} version={:16} start=0x{:08x}  len=0x{:08x}  (start={:8} len={:8})'.format(
            self.num, quote_string(self.name), quote_string(self.version), self.start, self.len, self.start, self.len)


class MtdPart:
    """A header's 'Mtd_Part'."""

    def __init__(self, buf):
        self.name = None
        self.a = 0
        self.mtd = None
        self.start = 0
        self.len = 0

        fields = zip(MTD_PART_FIELDS, struct.unpack(MTD_PART_FORMAT, buf))
        for key, val in fields:
            setattr(self, key, val)

        decode_strings(self, MTD_PART_STRINGS)

    def __repr__(self):
        return f"{self.__class__.__qualname__}({self.name!r})"

    def __iter__(self):
        for key in dir(self):
            if not key.startswith('_'):
                yield key, getattr(self, key)

    def __bytes__(self):
        return struct.pack(MTD_PART_FORMAT, self.name.encode(), self.a, self.mtd.encode(), self.start, self.len)

    def debug_str(self):
        return 'Mtd_part name={:16} mtd={:16}  a=0x{:08x}  start=0x{:08x}  len=0x{:08x}'.format(
            quote_string(self.name), quote_string(self.mtd), self.a, self.start, self.len)


class Header:
    """PAK file header."""

    def __init__(self, buf, section_count, mtd_part_count, is64=False):
        self.magic = 0
        self.crc32 = 0
        self.type = 0
        self.sections = []
        self.mtd_parts = []
        self.is64 = is64
        if is64:
            self.header_format = HEADER_FORMAT_64
            self.header_header_size = HEADER_HEADER_SIZE_64
            self.section_size = SECTION_SIZE_64
        else:
            self.header_format = HEADER_FORMAT
            self.header_header_size = HEADER_HEADER_SIZE
            self.section_size = SECTION_SIZE

        self.size = calc_header_size(section_count, mtd_part_count, is64)
        if len(buf) != self.size:
            raise Exception(f"Invalid header buffer size, expected: {self.size}, got: {len(buf)}")

        fields = zip(HEADER_FIELDS, struct.unpack(self.header_format, buf[:self.header_header_size]))
        for key, val in fields:
            setattr(self, key, val)

        buf = buf[self.header_header_size:]
        for num in range(section_count):
            self.sections.append(Section(buf[:self.section_size], num, is64))
            buf = buf[self.section_size:]

        for _ in range(mtd_part_count):
            self.mtd_parts.append(MtdPart(buf[:MTD_PART_SIZE]))
            buf = buf[MTD_PART_SIZE:]

        self._check_errors(buf[:-4])

    def __repr__(self):
        return '{}(magic=0x{:08x}, crc32=0x{:08x}, type=0x{:08x})'.format(
            self.__class__.__qualname__, self.magic, self.crc32, self.type, len(self.sections), len(self.mtd_parts))

    def __iter__(self):
        for key in dir(self):
            if not key.startswith('_'):
                yield key, getattr(self, key)

    def __bytes__(self):
        buf = struct.pack(self.header_format, self.magic, self.crc32, self.type)
        for section in self.sections:
            buf += bytes(section)
        for mtd_part in self.mtd_parts:
            buf += bytes(mtd_part)

        if len(buf) != self.size:
            raise Exception(f"Serialization error: should have been {self.size} bytes, but produced: {len(buf)} bytes")

        return buf

    def _check_errors(self, buf_crc):
        if self.magic != PAK_MAGIC:
            raise Exception(f"Wrong header magic: expected 0x{PAK_MAGIC:08x}, got 0x{self.magic:08x}")

    def debug_str(self):
        return 'Header  magic=0x{:08x}  crc32=0x{:08x}  type=0x{:08x}  sections=<{}>  mtd_parts=<{}>'.format(
            self.magic, self.crc32, self.type, len(self.sections), len(self.mtd_parts))

    def print_debug(self):
        print(self.debug_str())
        for section in self.sections:
            print(f"    {section.debug_str()}")
        for part in self.mtd_parts:
            print(f"    {part.debug_str()}")


class PAK:

    def __init__(self, fd, header: Header, closefd=True) -> None:
        self._fd = fd
        self._header = header
        self._closefd = closefd

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
        return self._header.crc32

    @property
    def type(self):
        return self._header.type

    @property
    def header(self):
        return self._header

    @property
    def sections(self):
        return self._header.sections

    @property
    def partitions(self):
        return self._header.mtd_parts

    @property
    def is64(self):
        return self._header.is64

    def close(self):
        self._fd.close()

    def calc_crc(self):
        """Calculate the PAK file's CRC (which should match the header's CRC)."""
        crc = 0xffffffff
        self._fd.seek(self.header.size)

        for chunk in iter(lambda: self._fd.read(CHUNK_SIZE), b''):
            crc = zlib.crc32(chunk, crc)

        buf = b'\2\0\0\0'  # TODO explain...
        crc = zlib.crc32(buf, crc)

        self._fd.seek(self.header.header_header_size)
        buf = self._fd.read(len(self.sections) * self.header.section_size)
        crc = zlib.crc32(buf, crc)

        crc = crc ^ 0xffffffff
        return crc

    def extract_section(self, section: Section):
        self._fd.seek(section.start)
        return self._fd.read(section.len)

    def save_section(self, section: Section, out_filename):
        self._fd.seek(section.start)
        with open(out_filename, "wb") as fout:
            copy(self._fd, fout, section.len)

    def extract(self, output_dir: Path, include_empty=False, quiet=True):
        """Extract all sections from the PAK file into individual files."""
        if not output_dir.exists():
            output_dir.mkdir()

        if not output_dir.exists() or not output_dir.is_dir():
            raise Exception(f"Invalid output directory: {output_dir}")

        for section in self.sections:
            out_filename = output_dir / make_section_filename(section)
            if section.len or include_empty:
                _print(f"Extracting section {section.num} ({section.len} bytes) into {out_filename}", quiet=quiet)
                self.save_section(section, out_filename)
            else:
                _print(f"Skipping empty section {section.num}", quiet=quiet)

    @staticmethod
    def is_64bit(fd):
        """Determine the firmware's target bitness.

        Firmwares for 64-bit devices have 8 bytes long header fields
        instead of 4, with zero padding. That means the three "extra"
        groups of bytes are all zeroes. For 32-bit devices, the first
        group corresponds to the CRC and the second is a part of the
        first section's name, therefore they can never be all zeroes.
        """
        fmt = "<IIIIII"
        struct_size = struct.calcsize(fmt)
        _, group1, _, group2, _, group3 = struct.unpack(fmt, fd.read(struct_size))
        return sum((group1, group2, group3)) == 0

    @staticmethod
    def get_section_count(fd, is64) -> Optional[int]:
        """
        Attempt to guess the number of sections for the given PAK firmware file.

        :return: Guessed number of sections, or None if it couldn't be guessed
        """
        offset = HEADER_HEADER_SIZE_64 if is64 else HEADER_HEADER_SIZE
        section_size = SECTION_SIZE_64 if is64 else SECTION_SIZE
        fd.seek(offset, 1)
        first_section = Section(fd.read(section_size), 0, is64)
        first_section_name = first_section.name.encode("utf-8")
        for count in range(30):
            data = fd.read(section_size)
            if data.startswith(first_section_name):
                return count + 1
        return None

    @staticmethod
    def read_header(fd, section_count, is64):
        """Read and parse the header of a PAK firmware file.

        :param fd: file object representing the PAK firmware file
        :param section_count: number of sections present in the header
        :param is64: bitness of the PAK firmware
        :return: the parsed Header object
        """
        header_size = calc_header_size(section_count, section_count, is64)
        buf = fd.read(header_size)
        if len(buf) != header_size:
            raise Exception(f"Header size error, expected: {header_size}, got: {len(buf)}")
        return Header(buf, section_count, section_count, is64)

    @classmethod
    def from_fd(cls, fd, offset=0, closefd=True):
        fd.seek(offset)
        is64 = cls.is_64bit(fd)
        fd.seek(offset)
        section_count = cls.get_section_count(fd, is64)
        fd.seek(offset)
        header = cls.read_header(fd, section_count, is64)
        return cls(fd, header, closefd)

    @classmethod
    def from_bytes(cls, bytes_, offset=0):
        return cls.from_fd(io.BytesIO(bytes_), offset)

    @classmethod
    def from_file(cls, path, offset=0):
        return cls.from_fd(open(path, "rb"), offset)


def read_header(filename, section_count=None, mtd_part_count=None, is64=None):
    """Read and parse the header of a PAK firmware file.

    :param filename: name of the PAK firmware file
    :param section_count: number of sections present in the header
    :param mtd_part_count: optional number of mtd_parts, defaults to section_count
    :param is64: bitness of the PAK firmware
    :return: the parsed Header object
    """
    with PAK.from_file(filename) as pak:
        return pak.header


def calc_crc(filename, section_count=None, is64=None):
    """Calculate the PAK file's CRC (which should match the header's CRC)."""
    with PAK.from_file(filename) as pak:
        return pak.calc_crc()


def check_crc(filename, section_count=None, mtd_part_count=None, is64=None):
    """Check the PAK file's crc matches the crc in its header."""
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


def update_crc(filename, section_count=None, is64=None):
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


def make_section_filename(section):
    # TODO: should sanitize section name before turning it into a filename
    if section.name:
        return f"{section.num:02}_{section.name}.bin"
    return f"{section.num:02}.bin"


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


def extract_section(f, section, out_filename):
    f.seek(section.start)
    with open(out_filename, "wb") as fout:
        copy(f, fout, section.len)


def extract(filename, output_dir: Path, include_empty=False, section_count=None, mtd_part_count=None):
    """Extract all sections from the given PAK file into individual files."""
    if not output_dir.exists():
        output_dir.mkdir()

    if not output_dir.exists() or not output_dir.is_dir():
        raise Exception(f"Invalid output directory: {output_dir}")

    with PAK.from_file(filename) as pak:
        for section in pak.sections:
            out_filename = output_dir / make_section_filename(section)
            if section.len or include_empty:
                print(f"Extracting section {section.num} ({section.len} bytes) into {out_filename}")
                pak.save_section(section, out_filename)
            else:
                print(f"Skipping empty section {section.num}")


def replace_section(filename, section_file: Path, section_num, output_file: Path, section_count=None, mtd_part_count=None):
    """Copy the given PAK file into new output_file, replacing the specified section.

    :param filename: name of the input PAK firmware file
    :param section_file: name of the file containing the section to be swapped-in
    :param section_num: number of the section to be replaced
    :param output_file: name of the output file which will contained the modified PAK file
    :param section_count: number of sections in the input PAK file
    :param mtd_part_count:  optional number of mtd_parts in the input PAK file
    """
    with PAK.from_file(filename) as pak:
        new_header = pak.header
        section_count = len(pak.sections)

    if not section_file.is_file():
        raise Exception(f"Section file doesn't exist or is not a file: {section_file}")

    section_len = section_file.stat().st_size

    if section_num < 0 or section_num >= section_count:
        raise Exception(f"Invalid section number: {section_num} (should be between 0 and {section_count})")

    print(f"Input            : {filename}")
    print(f"Output           : {output_file}")
    print(f"Replacing section: {section_num}")
    print(f"Replacement file : {section_file}")

    with PAK.from_file(filename) as pak, open(section_file, "rb") as fsection, open(output_file, "wb") as fout:
        # Write placeholder header
        fout.write(bytearray(new_header.size))

        for section in pak.sections:
            pak._fd.seek(section.start)
            new_header.sections[section.num].start = fout.tell()  # TODO: set up a check in Header.init() to validate sections[num].num==num
            if section.num == section_num:
                new_header.sections[section.num].len = section_len
                print(f"Replacing section {section.num} ({section.len} bytes) with {section_len} bytes")
                copy(fsection, fout, section_len)
            else:
                print(f"Copying section {section.num} ({section.len} bytes)")
                copy(pak._fd, fout, section.len)

        print(f"Writing header... ({new_header.size} bytes)")
        fout.seek(0)
        fout.write(bytes(new_header))

    print("Updating CRC...")
    update_crc(output_file)

    print("Replacement completed. New header: ")
    with PAK.from_file(output_file) as pak:
        pak.header.print_debug()


def guess_section_count(filename, is64=None) -> Optional[int]:
    """
    Attempt to guess the number of sections for the given PAK firmware file.

    :return: Guessed number of sections, or None if it couldn't be guessed
    """
    if is64 is None:
        is64 = is_64bit(filename)
    with open(filename, "rb") as f:
        return PAK.get_section_count(f, is64)


def is_64bit(filename):
    with open(filename, "rb") as f:
        return PAK.is_64bit(f)


def _print(*args, **kwargs):
    if not kwargs.pop("quiet", False):
        print(*args, **kwargs)


def _is_pak(file):
    return file.read(4) == PAK_MAGIC_BYTES


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
