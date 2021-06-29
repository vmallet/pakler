import argparse
import struct
import sys
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
HEADER_SIZE = struct.calcsize(HEADER_FORMAT) + (SECTION_COUNT * SECTION_SIZE) + (MTD_PART_COUNT * MTD_PART_SIZE)


def fix_strings(object, fields):
    for field in fields:
        cstr = getattr(object, field)
        fixed = cstr.rstrip(b'\0').decode('utf-8')
        setattr(object, field, fixed)


def quote_string(string, min_length):
    return "{0:{1}s}".format('"{}"'.format(string), min_length)


class Section(object):
    def __init__(self, buf):
        fields = dict(list(zip(SECTION_FIELDS, struct.unpack(SECTION_FORMAT,buf))))
        for key in fields:
            setattr(self, key, fields[key])

        fix_strings(self, SECTION_STRINGS)

    def __repr__(self):
        return 'Section name={} version={} start={:08x}  len={:08x}'.format(quote_string(self.name, 16), quote_string(self.version, 16), self.start, self.len)

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

    def __init__(self, buf):
        fields = dict(list(zip(HEADER_FIELDS, struct.unpack(HEADER_FORMAT,buf[0:12]))))
        for key in fields:
            setattr(self, key, fields[key])

        buf = buf[12:]
        for a in range(0, SECTION_COUNT):
            self.sections.append(Section(buf[0:SECTION_SIZE]))
            buf = buf[SECTION_SIZE:]

        for a in range(0, MTD_PART_COUNT):
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


def read_header(filename):
    with open(filename, "rb") as f:
        buf = f.read(HEADER_SIZE)
        if len(buf) != HEADER_SIZE:
            raise Exception("size error")

        header = Header(buf)

    return header


def calc_crc(filename):
    crc = 0xffffffff
    with open(filename, "rb") as f:
        f.seek(HEADER_SIZE)

        for chunk in iter(lambda: f.read(CHUNK_SIZE), b''):
            crc = zlib.crc32(chunk, crc)

        buf = b'\2\0\0\0' # TODO explain...
        crc = zlib.crc32(buf, crc)

        f.seek(12)
        buf = f.read(SECTION_COUNT * SECTION_SIZE)
        crc = zlib.crc32(buf, crc)

    crc = crc ^ 0xffffffff
    return crc


def check_crc(filename):
    header = read_header(filename)
    crc = calc_crc(filename)

    if crc != header.crc32:
        print("CRC MISMATCH, file: {}, header.crc={:08x}, got={:08x}".format(filename, header.crc32, crc))
    else:
        print("File passes CRC check: {}".format(filename))


def parse_args():
    parser = argparse.ArgumentParser(description='swanntool (by Vincent Mallet 2021)')

    pgroup = parser.add_mutually_exclusive_group()
    pgroup.add_argument('-l', '--list', dest='list', action='store_true',
                        help='List contents of PAK firmware file (default)')
    pgroup.add_argument('-r', '--replace', dest='replace', action='store_true',
                        help='Replace a section into a new PAK file')
    parser.add_argument('-o', '--output', dest='output_pak', help='Name of the output PAK file')
    parser.add_argument('-c', '--section-count', dest='section_count', type=int, default=SECTION_COUNT,
                        help='Number of sections in source PAK file (default {})'.format(SECTION_COUNT))
    parser.add_argument('filename', nargs=2, help='Name of PAK firmware file')

    args = parser.parse_args()
    print("args: {}".format(args))

    # Set default action as "list"
    if not (args.list or args.replace):
        args.list = True

    return args


def main():
    args = parse_args()
    filename = args.filename[0]

    if args.list:
        header = read_header(filename)
        header.print_debug()
        check_crc(filename)
    elif args.replace:
        pass


if __name__ == "__main__":
    main()
