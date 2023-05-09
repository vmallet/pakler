#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2021 Vincent Mallet <vmallet@gmail.com>
# SPDX-License-Identifier: MIT

"""Simple tool to manipulate PAK firmware files (list, extract, replace) for Swann and Reolink devices. See -h."""

import argparse
import io
import os.path
import struct
import textwrap
import zlib
from typing import Optional

try:
    from ._version import __version__
except ModuleNotFoundError:
    __version__ = 'dev-local'

EPILOG_MARKER = "##MYEPILOG##"

CHUNK_SIZE = 128 * 1024

PAK_MAGIC = 0x32725913

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
MTD_PART_COUNT = 10

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
    return '"{}"'.format(string)


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
        return 'Section {:2} name={:16} version={:16} start={:08x}  len={:08x}  (start={:8} len={:8})'.format(
            self.num, quote_string(self.name), quote_string(self.version), self.start, self.len, self.start, self.len)

    def __iter__(self):
        for key in dir(self):
            if not key.startswith('_'):
                yield key, getattr(self, key)

    def serialize(self):
        return struct.pack(self.section_format, self.name.encode(), self.version.encode(), self.start, self.len)


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
        return 'Mtd_part name={:16} mtd={:16}  a={:08x}  start={:08x}  len={:08x}'.format(
            quote_string(self.name), quote_string(self.mtd), self.a, self.start, self.len)

    def __iter__(self):
        for key in dir(self):
            if not key.startswith('_'):
                yield key, getattr(self, key)

    def serialize(self):
        return struct.pack(MTD_PART_FORMAT, self.name.encode(), self.a, self.mtd.encode(), self.start, self.len)


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
            raise Exception("Invalid header buffer size, expected: {}, got: {}".format(self.size, len(buf)))

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
        return 'Header  magic={:08x}  crc32={:08x}  type={:08x}  sections=<{}>  mtd_parts=<{}>'.format(
            self.magic, self.crc32, self.type, len(self.sections), len(self.mtd_parts))

    def __iter__(self):
        for key in dir(self):
            if not key.startswith('_'):
                yield key, getattr(self, key)

    def _check_errors(self, buf_crc):
        if self.magic != PAK_MAGIC:
            raise Exception("Wrong header magic: expected {:08x}, got {:08x}".format(PAK_MAGIC, self.magic))

    def print_debug(self):
        print(self)
        for section in self.sections:
            print("    {}".format(section))
        for part in self.mtd_parts:
            print("    {}".format(part))

    def serialize(self):
        buf = struct.pack(self.header_format, self.magic, self.crc32, self.type)
        for section in self.sections:
            buf += section.serialize()
        for mtd_part in self.mtd_parts:
            buf += mtd_part.serialize()

        if len(buf) != self.size:
            raise Exception("Serialization error: should have been {} bytes, but produced: {} bytes".format(
                self.size, len(buf)))

        return buf


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

    def extract(self, output_dir, include_empty=False, quiet=True):
        """Extract all sections from the PAK file into individual files."""
        if not os.path.exists(output_dir):
            os.mkdir(output_dir)

        if not os.path.exists(output_dir) or not os.path.isdir(output_dir):
            raise Exception("Invalid output directory: {}".format(output_dir))

        for section in self.sections:
            out_filename = os.path.join(output_dir, make_section_filename(section))
            if section.len or include_empty:
                _print("Extracting section {} ({} bytes) into {}".format(section.num, section.len, out_filename), quiet=quiet)
                self.save_section(section, out_filename)
            else:
                _print("Skipping empty section {}".format(section.num), quiet=quiet)

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
            raise Exception("Header size error, expected: {}, got: {}".format(header_size, len(buf)))
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
    with PAK.from_file(filename) as pak:
        header = pak.header
        crc = pak.calc_crc()

    if crc != header.crc32:
        print("CRC MISMATCH, file: {}, header.crc={:08x}, got={:08x}".format(filename, header.crc32, crc))
        return False

    print("File passes CRC check: {}".format(filename))
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
        return "{:02}_{}.bin".format(section.num, section.name)
    return "{:02}.bin".format(section.num)


def find_new_name(base):
    name = base
    suffix = 0
    while os.path.exists(name):
        suffix += 1
        if suffix == 1000:
            raise Exception("Could not find a non-existing file/directory for base: {}".format(base))
        name = "{}.{:03}".format(base, suffix)

    return name


def make_output_file_name(filename):
    base = filename + ".replaced"
    return find_new_name(base)


def make_output_dir_name(filename):
    base = filename + ".extracted"
    return find_new_name(base)


def copy(fin, fout, length):
    chunk_size = CHUNK_SIZE
    while length > 0:
        if length < chunk_size:
            chunk_size = length
        chunk = fin.read(chunk_size)
        if not chunk:
            raise Exception("Read error with chunk_size={} length={}".format(chunk_size, length))
        fout.write(chunk)
        length -= chunk_size


def extract_section(f, section, out_filename):
    f.seek(section.start)
    with open(out_filename, "wb") as fout:
        copy(f, fout, section.len)


def extract(filename, output_dir, include_empty=False, section_count=None, mtd_part_count=None):
    """Extract all sections from the given PAK file into individual files."""
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)

    if not os.path.exists(output_dir) or not os.path.isdir(output_dir):
        raise Exception("Invalid output directory: {}".format(output_dir))

    with PAK.from_file(filename) as pak:
        for section in pak.sections:
            out_filename = os.path.join(output_dir, make_section_filename(section))
            if section.len or include_empty:
                print("Extracting section {} ({} bytes) into {}".format(section.num, section.len, out_filename))
                pak.save_section(section, out_filename)
            else:
                print("Skipping empty section {}".format(section.num))


def replace_section(filename, section_file, section_num, output_file, section_count=None, mtd_part_count=None):
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

    if not os.path.isfile(section_file):
        raise Exception("Section file doesn't exist or is not a file: {}".format(section_file))

    section_len = os.path.getsize(section_file)

    if section_num < 0 or section_num >= section_count:
        raise Exception("Invalid section number: {} (should be between 0 and {})".format(section_num, section_count))

    print("Input            : {}".format(filename))
    print("Output           : {}".format(output_file))
    print("Replacing section: {}".format(section_num))
    print("Replacement file : {}".format(section_file))

    with PAK.from_file(filename) as pak, open(section_file, "rb") as fsection, open(output_file, "wb") as fout:
        # Write placeholder header
        fout.write(bytearray(new_header.size))

        for section in pak.sections:
            pak._fd.seek(section.start)
            new_header.sections[section.num].start = fout.tell()  # TODO: set up a check in Header.init() to validate sections[num].num==num
            if section.num == section_num:
                new_header.sections[section.num].len = section_len
                print("Replacing section {} ({} bytes) with {} bytes".format(section.num, section.len, section_len))
                copy(fsection, fout, section_len)
            else:
                print("Copying section {} ({} bytes)".format(section.num, section.len))
                copy(pak._fd, fout, section.len)

        print("Writing header... ({} bytes)".format(new_header.size))
        fout.seek(0)
        fout.write(new_header.serialize())

    print("Updating CRC...")
    update_crc(output_file)

    print("Replacement completed. New header: ")
    with PAK.from_file(output_file) as pak:
        pak.header.print_debug()


def make_epilogue_text(prog, indent, width):
    lines = [
        '{} ~/fw/CAM_FW.pak'.format(prog),
        'List the content of CAM_FW.pak, auto-detecting the number of sections',
        '',
        '{} ~/fw/CAM_FW.pak -e -d /tmp/extracted/'.format(prog),
        'Extract all sections of CAM_FW.pak into /tmp/extracted',
        '',
        '{} ~/fw/CAM_FW.pak -r -n 4 -f ~/fw/new_fs.cramfs -o ~/fw/CAM_FW_PATCHED.pak'.format(prog),
        'From firmware file ~/fw/CAM_FW.pak, replace the 4th section with new file ~/fw/new_fs.cramfs, writing'
        ' the output to ~/fw/CAM_FW_PATCHED.pak'
    ]

    wrapper = textwrap.TextWrapper(width, initial_indent=indent, subsequent_indent=indent)

    return "\n".join(["examples:"] + [wrapper.fill(line) for line in lines])


class EpilogizerHelpFormatter(argparse.HelpFormatter):
    """
    Help message formatter which injects a pre-formatted epilog text if the text to be formatted is the EPILOG_MARKER.
    """

    def __init__(self, prog, indent_increment=2, max_help_position=24, width=None) -> None:
        super().__init__(prog, indent_increment, max_help_position, width)
        self._my_prog = prog
        self._my_indent = ' ' * indent_increment

    def _fill_text(self, text, width, indent):
        if text == EPILOG_MARKER:
            return make_epilogue_text(self._my_prog, self._my_indent, width)
        return super()._fill_text(text, width, indent)


def parse_args():
    parser = argparse.ArgumentParser(
        description='%(prog)s {} (by Vincent Mallet 2021) - manipulate Swann / Reolink PAK firmware files'.format(
            __version__),
        formatter_class=EpilogizerHelpFormatter,
        epilog=EPILOG_MARKER)

    parser.add_argument('-v', '--version', action='version', version="%(prog)s {}".format(__version__))

    pgroup = parser.add_mutually_exclusive_group()
    pgroup.add_argument('-l', '--list', dest='list', action='store_true',
                        help='List contents of PAK firmware file (default)')
    pgroup.add_argument('-r', '--replace', dest='replace', action='store_true',
                        help='Replace a section into a new PAK file')
    pgroup.add_argument('-e', '--extract', dest='extract', action='store_true',
                        help='Extract sections to a directory')
    parser.add_argument('-f', '--section-file', dest='section_file', help='Input binary file for section replacement')
    parser.add_argument('-n', '--section-num', dest='section_num', type=int, help='Section number of replaced section')
    parser.add_argument('-o', '--output', dest='output_pak', help='Name of output PAK file when replacing a section')
    parser.add_argument('-d', '--output-dir', dest='output_dir',
                        help='Name of output directory when extracting sections')
    parser.add_argument('--empty', dest='include_empty', action='store_true',
                        help='Include empty sections when extracting')
    parser.add_argument('filename', nargs=1, help='Name of PAK firmware file')

    args = parser.parse_args()

    # Set default action as "list"
    if not (args.list or args.replace or args.extract):
        args.list = True

    return args


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


def main():
    args = parse_args()
    filename = args.filename[0]

    if args.list:
        with PAK.from_file(filename) as pak:
            pak.header.print_debug()
            check_crc(filename)

    elif args.extract:
        output_dir = args.output_dir or make_output_dir_name(filename)
        print("output: {}".format(output_dir))
        with PAK.from_file(filename) as pak:
            pak.extract(output_dir, args.include_empty, quiet=False)

    elif args.replace:
        if not args.section_file or not args.section_num:
            raise Exception("replace error: need both section binary file and section number to do a replacement;"
                            " see help")
        output_file = args.output_pak or make_output_file_name(filename)
        replace_section(filename, args.section_file, args.section_num, output_file)


if __name__ == "__main__":
    main()
