#!/usr/bin/env python3

import argparse
import os.path
import struct
import textwrap
import zlib

EPILOG_MARKER = "##MYEPILOG##"

CHUNK_SIZE = 128 * 1024

SWANN_MAGIC = 0x32725913

SECTION_FORMAT = "<32s24sII"
SECTION_FIELDS = ['name',  # TODO: Docs
                  'version',
                  'start',
                  'len']
SECTION_STRINGS = ['name', 'version']
SECTION_SIZE = struct.calcsize(SECTION_FORMAT)  # 64
SECTION_COUNT = 10

MTD_PART_FORMAT = "<32sI32sII"
MTD_PART_FIELDS = ['name',
                   'a',
                   'mtd',
                   'start',
                   'len']
MTD_PART_STRINGS = ['name',
                    'mtd']
MTD_PART_SIZE = struct.calcsize(MTD_PART_FORMAT)
MTD_PART_COUNT = 10

HEADER_FORMAT = "<III"
HEADER_FIELDS = ['magic',
                 'crc32',
                 'type']
HEADER_CRC_OFFSET = 4  # Offset of the CRC in the file
HEADER_HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # Size of the header's header (first 12 bytes)


def calc_header_size(section_count, mtd_part_count=None):
    if not mtd_part_count:
        mtd_part_count = section_count

    return struct.calcsize(HEADER_FORMAT) + (section_count * SECTION_SIZE) + (mtd_part_count * MTD_PART_SIZE)


def fix_strings(obj, fields):
    for field in fields:
        cstr = getattr(obj, field)
        fixed = cstr.rstrip(b'\0').decode('utf-8')
        setattr(obj, field, fixed)


def quote_string(string, min_length):
    return "{0:{1}s}".format('"{}"'.format(string), min_length)


class Section(object):
    def __init__(self, buf, num):
        self.num = num
        self.name = None
        self.version = None
        self.start = 0
        self.len = 0

        fields = dict(zip(SECTION_FIELDS, struct.unpack(SECTION_FORMAT, buf)))
        for key, val in fields.items():
            setattr(self, key, val)

        fix_strings(self, SECTION_STRINGS)

    def __repr__(self):
        return 'Section name={} version={} start={:08x}  len={:08x}  (start={:8} len={:8})'.format(
            quote_string(self.name, 16), quote_string(self.version, 16), self.start, self.len, self.start, self.len)

    def __iter__(self):
        for key in dir(self):
            if not key.startswith('_'):
                yield key, getattr(self, key)

    def serialize(self):
        return struct.pack(SECTION_FORMAT, self.name.encode(), self.version.encode(), self.start, self.len)


class MtdPart(object):
    def __init__(self, buf):
        self.name = None
        self.a = 0
        self.mtd = None
        self.start = 0
        self.len = 0

        fields = dict(zip(MTD_PART_FIELDS, struct.unpack(MTD_PART_FORMAT, buf)))
        for key, val in fields.items():
            setattr(self, key, val)

        fix_strings(self, MTD_PART_STRINGS)

    def __repr__(self):
        return 'Mtd_part name={} mtd={}  a={:08x}  start={:08x}  len={:08x}'.format(
            quote_string(self.name, 16), quote_string(self.mtd, 16), self.a, self.start, self.len)

    def __iter__(self):
        for key in dir(self):
            if not key.startswith('_'):
                yield key, getattr(self, key)

    def serialize(self):
        return struct.pack(MTD_PART_FORMAT, self.name.encode(), self.a, self.mtd.encode(), self.start, self.len)


class Header(object):
    def __init__(self, buf, section_count, mtd_part_count):
        self.magic = 0
        self.crc32 = 0
        self.type = 0
        self.sections = []
        self.mtd_parts = []

        self.size = calc_header_size(section_count, mtd_part_count)
        if len(buf) != self.size:
            raise Exception("Invalid header buffer size, expected: {}, got: {}".format(self.size, len(buf)))

        fields = dict(zip(HEADER_FIELDS, struct.unpack(HEADER_FORMAT, buf[:HEADER_HEADER_SIZE])))
        for key, val in fields.items():
            setattr(self, key, val)

        buf = buf[HEADER_HEADER_SIZE:]
        for num in range(section_count):
            self.sections.append(Section(buf[:SECTION_SIZE], num))
            buf = buf[SECTION_SIZE:]

        for num in range(mtd_part_count):
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
        if self.magic != SWANN_MAGIC:
            raise Exception("Wrong header magic: expected {:08x}, got {:08x}".format(SWANN_MAGIC, self.magic))

    def print_debug(self):
        print(self)
        for section in self.sections:
            print("    {}".format(section))
        for part in self.mtd_parts:
            print("    {}".format(part))

    def serialize(self):
        buf = struct.pack(HEADER_FORMAT, self.magic, self.crc32, self.type)
        for section in self.sections:
            buf += section.serialize()
        for mtd_part in self.mtd_parts:
            buf += mtd_part.serialize()

        if len(buf) != self.size:
            raise Exception("Serialization error: should have been {} bytes, but produced: {} bytes".format(
                self.size, len(buf)))

        return buf


def usage(argv, exitcode):
    print("usage: {} imagename".format(argv[0]))
    exit(exitcode)


def read_header(filename, section_count, mtd_part_count=None):
    if not mtd_part_count:
        mtd_part_count = section_count

    header_size = calc_header_size(section_count, mtd_part_count)

    with open(filename, "rb") as f:
        buf = f.read(header_size)
        if len(buf) != header_size:
            raise Exception("Header size error, expected: {}, got: {}".format(header_size, len(buf)))

        header = Header(buf, section_count, mtd_part_count)

    return header


def calc_crc(filename, section_count):
    header_size = calc_header_size(section_count)
    crc = 0xffffffff
    with open(filename, "rb") as f:
        f.seek(header_size)

        for chunk in iter(lambda: f.read(CHUNK_SIZE), b''):
            crc = zlib.crc32(chunk, crc)

        buf = b'\2\0\0\0'  # TODO explain...
        crc = zlib.crc32(buf, crc)

        f.seek(HEADER_HEADER_SIZE)
        buf = f.read(section_count * SECTION_SIZE)
        crc = zlib.crc32(buf, crc)

    crc = crc ^ 0xffffffff
    return crc


def check_crc(filename, section_count, mtd_part_count=None):
    header = read_header(filename, section_count, mtd_part_count)
    crc = calc_crc(filename, section_count)

    if crc != header.crc32:
        print("CRC MISMATCH, file: {}, header.crc={:08x}, got={:08x}".format(filename, header.crc32, crc))
    else:
        print("File passes CRC check: {}".format(filename))


def update_crc(filename, section_count):
    crc = calc_crc(filename, section_count)

    with open(filename, "r+b") as f:
        f.seek(HEADER_CRC_OFFSET)
        f.write(struct.pack("<I", crc))


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


def extract(filename, output_dir, include_empty, section_count, mtd_part_count=None):
    header = read_header(filename, section_count, mtd_part_count)

    if not os.path.exists(output_dir):
        os.mkdir(output_dir)

    if not os.path.exists(output_dir) or not os.path.isdir(output_dir):
        raise Exception("Invalid output directory: {}".format(output_dir))

    with open(filename, "rb") as f:
        for section in header.sections:
            out_filename = os.path.join(output_dir, make_section_filename(section))
            if section.len or include_empty:
                print("Extracting section {} ({} bytes) into {}".format(section.num, section.len, out_filename))
                extract_section(f, section, out_filename)
            else:
                print("Skipping empty section {}".format(section.num))


def replace_section(filename, section_file, section_num, output_file, section_count, mtd_part_count=None):
    header = read_header(filename, section_count, mtd_part_count)
    new_header = read_header(filename, section_count, mtd_part_count)

    if not os.path.isfile(section_file):
        raise Exception("Section file doesn't exist or is not a file: {}".format(section_file))

    section_len = os.path.getsize(section_file)

    if section_num < 0 or section_num >= section_count:
        raise Exception("Invalid section number: {} (should be between 0 and {})".format(section_num, section_count))

    print("Input            : {}".format(filename))
    print("Output           : {}".format(output_file))
    print("Replacing section: {}".format(section_num))
    print("Replacement file : {}".format(section_file))

    with open(filename, "rb") as f, open(section_file, "rb") as fsection, open(output_file, "wb") as fout:
        # Write placeholder header
        fout.write(bytearray(new_header.size))

        for section in header.sections:
            f.seek(section.start)
            new_header.sections[section.num].start = fout.tell()  # TODO: set up a check in Header.init() to validate sections[num].num==num
            if section.num == section_num:
                new_header.sections[section.num].len = section_len
                print("Replacing section {} ({} bytes)".format(section.num, section_len))
                copy(fsection, fout, section_len)
            else:
                print("Copying section {} ({} bytes)".format(section.num, section.len))
                copy(f, fout, section.len)

        print("Writing header... ({} bytes)".format(new_header.size))
        fout.seek(0)
        fout.write(new_header.serialize())

    print("Updating CRC...")
    update_crc(output_file, section_count)

    print("Replacement completed. New header: ")
    replaced_header = read_header(output_file, section_count)
    replaced_header.print_debug()


def make_epilogue_text(prog, indent, width):
    lines = [
        '{} ~/fw/CAM_FW.PAK'.format(prog),
        'List the content of CAM_FW.PAK with the default number of sections (10)',
        '',
        '{} ~/fw/CAM_FW.PAK -c 9'.format(prog),
        'List the content of CAM_FW.PAK knowing it has 9 sections',
        '',
        '{} ~/fw/CAM_FW.PAK -e -c 9 -d /tmp/extracted/'.format(prog),
        'Extract all sections of CAM_FW.PAK into /tmp/extracted, knowing it has 9 sections',
        '',
        '{} ~/fw/CAM_FW.PAK -r -c 9 -n 4 -f ~/fw/new_fs.cramfs -o ~/fw/CAM_FW_PATCHED.PAK'.format(prog),
        'From firwmware file ~/fw/CAM_FW.PAK, replace the 4th section with new file ~/fw/new_fs.cramfs, writing'
        ' the output into ~/fw/CAM_FW_PATCHED.PAK, knowing the firmware has 9 sections'
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
        description='swanntool (by Vincent Mallet 2021) - manipulate Swann / Reolink / Novatek PAK firmware files',
        formatter_class=EpilogizerHelpFormatter,
        epilog=EPILOG_MARKER)

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
    parser.add_argument('-c', '--section-count', dest='section_count', type=int, default=SECTION_COUNT,
                        help='Number of sections in source PAK file (default {})'.format(SECTION_COUNT))
    parser.add_argument('--empty', dest='include_empty', action='store_true',
                        help='Include empty sections when extracting')
    parser.add_argument('filename', nargs=1, help='Name of PAK firmware file')

    args = parser.parse_args()

    # Set default action as "list"
    if not (args.list or args.replace or args.extract):
        args.list = True

    return args


def main():
    args = parse_args()
    filename = args.filename[0]

    if args.list:
        header = read_header(filename, args.section_count)
        header.print_debug()
        check_crc(filename, args.section_count)

    elif args.extract:
        output_dir = args.output_dir or make_output_dir_name(filename)
        print("output: {}".format(output_dir))
        extract(filename, output_dir, args.include_empty, args.section_count)

    elif args.replace:
        if not args.section_file or not args.section_num:
            raise Exception("replace error: need both section binary file and section number to do a replacement;"
                            " see help")
        output_file = args.output_pak or make_output_file_name(filename)
        replace_section(filename, args.section_file, args.section_num, output_file, args.section_count)


if __name__ == "__main__":
    main()
