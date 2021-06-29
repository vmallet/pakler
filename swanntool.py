import argparse
import os.path
import struct
import zlib

CHUNK_SIZE = 128 * 1024

SWANN_MAGIC = 0x32725913

SECTION_FORMAT = "<32s24sII"
SECTION_FIELDS = ['name', #TODO: Docs
                  'version',
                  'start',
                  'len']
SECTION_STRINGS = ['name', 'version']
SECTION_SIZE = struct.calcsize(SECTION_FORMAT) # 64
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


def calc_header_size(section_count, mtd_part_count = None):
    if not mtd_part_count:
        mtd_part_count = section_count

    return struct.calcsize(HEADER_FORMAT) + (section_count * SECTION_SIZE) + (mtd_part_count * MTD_PART_SIZE)


def fix_strings(object, fields):
    for field in fields:
        cstr = getattr(object, field)
        fixed = cstr.rstrip(b'\0').decode('utf-8')
        setattr(object, field, fixed)


def quote_string(string, min_length):
    return "{0:{1}s}".format('"{}"'.format(string), min_length)


class Section(object):
    def __init__(self, buf, num):
        self.num = num
        fields = dict(list(zip(SECTION_FIELDS, struct.unpack(SECTION_FORMAT,buf))))
        for key in fields:
            setattr(self, key, fields[key])

        fix_strings(self, SECTION_STRINGS)

    def __repr__(self):
        return 'Section name={} version={} start={:08x}  len={:08x}  (start={:8} len={:8})'.format(
            quote_string(self.name, 16), quote_string(self.version, 16), self.start, self.len, self.start, self.len)

    def __iter__(self):
        for key in dir(self):
            if not key.startswith('_'):
                yield key, getattr(self, key)


class MtdPart(object):
    def __init__(self, buf):
        fields = dict(list(zip(MTD_PART_FIELDS, struct.unpack(MTD_PART_FORMAT,buf))))
        for key in fields:
            setattr(self, key, fields[key])

        fix_strings(self, MTD_PART_STRINGS)

    def __repr__(self):
        return 'Mtd_part name={} mtd={}  a={:08x}  start={:08x}  len={:08x}'.format(
            quote_string(self.name, 16), quote_string(self.mtd, 16), self.a, self.start, self.len)

    def __iter__(self):
        for key in dir(self):
            if not key.startswith('_'):
                yield key, getattr(self, key)


class Header(object):
    magic = 0
    crc32 = 0
    type = 0
    sections = []
    mtd_parts = []

    def __init__(self, buf, section_count, mtd_part_count):
        fields = dict(list(zip(HEADER_FIELDS, struct.unpack(HEADER_FORMAT, buf[0:12]))))
        for key in fields:
            setattr(self, key, fields[key])

        buf = buf[12:]
        for num in range(0, section_count):
            self.sections.append(Section(buf[0:SECTION_SIZE], num))
            buf = buf[SECTION_SIZE:]

        for num in range(0, mtd_part_count):
            self.mtd_parts.append(MtdPart(buf[0:MTD_PART_SIZE]))
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


def usage(argv, exitcode):
    print("usage: {} imagename".format(argv[0]))
    exit(exitcode)


def read_header(filename, section_count, mtd_part_count = None):
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

        buf = b'\2\0\0\0' # TODO explain...
        crc = zlib.crc32(buf, crc)

        f.seek(12)
        buf = f.read(section_count * SECTION_SIZE)
        crc = zlib.crc32(buf, crc)

    crc = crc ^ 0xffffffff
    return crc


def check_crc(filename, section_count, mtd_part_count = None):
    header = read_header(filename, section_count, mtd_part_count)
    crc = calc_crc(filename, section_count)

    if crc != header.crc32:
        print("CRC MISMATCH, file: {}, header.crc={:08x}, got={:08x}".format(filename, header.crc32, crc))
    else:
        print("File passes CRC check: {}".format(filename))


def make_section_filename(section):
    #TODO: should sanitize section name before turning it into a filename
    if section.name:
        return "{:02}_{}.bin".format(section.num, section.name)
    return "{:02}.bin".format(section.num)


def make_output_dir_name(filename):
    base = filename + ".extracted"
    dirname = base
    suffix = 0
    while os.path.exists(dirname):
        suffix += 1
        if suffix == 1000:
            raise Exception("Could not find a non-existing directory for base: {}".format(base))
        dirname = "{}.{:03}".format(base, suffix)

    return dirname


def copy(fin, fout, len):
    chunk_size = CHUNK_SIZE
    while len > 0:
        if len < chunk_size:
            chunk_size = len
        chunk = fin.read(chunk_size)
        if not chunk:
            raise Exception("Read error with chunk_size={} len={}".format(chunk_size, len))
        fout.write(chunk)
        len -= chunk_size


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


def parse_args():
    parser = argparse.ArgumentParser(description='swanntool (by Vincent Mallet 2021)')

    pgroup = parser.add_mutually_exclusive_group()
    pgroup.add_argument('-l', '--list', dest='list', action='store_true',
                        help='List contents of PAK firmware file (default)')
    pgroup.add_argument('-r', '--replace', dest='replace', action='store_true',
                        help='Replace a section into a new PAK file')
    pgroup.add_argument('-e', '--extract', dest='extract', action='store_true',
                        help='Extract sections to a directory')
    parser.add_argument('-o', '--output', dest='output_pak', help='Name of the output PAK file')
    parser.add_argument('-d', '--output-dir', dest='output_dir',
                        help='Name of output directory when extracting sections')
    parser.add_argument('-c', '--section-count', dest='section_count', type=int, default=SECTION_COUNT,
                        help='Number of sections in source PAK file (default {})'.format(SECTION_COUNT))
    parser.add_argument('--empty', dest='include_empty', action='store_true',
                        help='Include empty sections when extracting')
    parser.add_argument('filename', nargs=1, help='Name of PAK firmware file')

    args = parser.parse_args()
    print("args: {}".format(args))

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
        pass


if __name__ == "__main__":
    main()
