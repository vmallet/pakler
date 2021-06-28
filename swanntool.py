import struct
import sys

# typedef struct _TblEntry {
#   char name[32];
#   char version[24];
#   unsigned int start;
#   unsigned int len;
# } TblEntry;

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
        x = cstr.rstrip(b'\0').decode('utf-8')
        # x = cstr.split('\0')[0]
        setattr(object, field, x)


class Section(object):
    def __init__(self, buf):
        fields = dict(list(zip(SECTION_FIELDS, struct.unpack(SECTION_FORMAT,buf))))
        for key in fields:
            setattr(self, key, fields[key])
        setattr(self, 'errors', [])

        fix_strings(self, SECTION_STRINGS)

        self._check_errors(buf[:-4])

    def __repr__(self):
        return 'Section name="{}" version="{}" start={:08x}  len={:08x}'.format(self.name, self.version, self.start, self.len)

    def __iter__(self):
        for key in dir(self):
            if not key.startswith('_'):
                yield key, getattr(self, key)

    def _check_errors(self, buf_crc):
        pass
        # if self.magic != UBI_EC_HDR_MAGIC:
        #     log(ec_hdr, 'Wrong MAGIC: expected %s got %s' % (UBI_EC_HDR_MAGIC, self.magic))
        #     self.errors.append('magic')

class MtdPart(object):
    def __init__(self, buf):
        fields = dict(list(zip(MTD_PART_FIELDS, struct.unpack(MTD_PART_FORMAT,buf))))
        for key in fields:
            setattr(self, key, fields[key])
        setattr(self, 'errors', [])

        fix_strings(self, MTD_PART_STRINGS)

        self._check_errors(buf[:-4])

    def __repr__(self):
        return 'Mtd_part name="{}" mtd="{}" a={:08x} start={:08x}  len={:08x}'.format(self.name, self.mtd, self.a, self.start, self.len)

    def __iter__(self):
        for key in dir(self):
            if not key.startswith('_'):
                yield key, getattr(self, key)

    def _check_errors(self, buf_crc):
        pass
        # if self.magic != UBI_EC_HDR_MAGIC:
        #     log(ec_hdr, 'Wrong MAGIC: expected %s got %s' % (UBI_EC_HDR_MAGIC, self.magic))
        #     self.errors.append('magic')


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
        setattr(self, 'errors', [])

        buf = buf[12:]
        for a in range(0, SECTION_COUNT):
            self.sections.append(Section(buf[0:SECTION_SIZE]))
            buf = buf[SECTION_SIZE:]

        for a in range(0, MTD_PART_COUNT):
            self.mtd_parts.append(MtdPart(buf[0:MTD_PART_SIZE]))
            buf = buf[MTD_PART_SIZE:]

        self._check_errors(buf[:-4])

    def __repr__(self):
        return 'Header  magic={:08x} crc32={:08x}  type={:08x}  sections=<{}>'.format(self.magic, self.crc32, self.type,
                                                                                      len(self.sections))
    def __iter__(self):
        for key in dir(self):
            if not key.startswith('_'):
                yield key, getattr(self, key)

    def _check_errors(self, buf_crc):
        pass
        # if self.magic != UBI_EC_HDR_MAGIC:
        #     log(ec_hdr, 'Wrong MAGIC: expected %s got %s' % (UBI_EC_HDR_MAGIC, self.magic))
        #     self.errors.append('magic')

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

        print("header: {}".format(header))

        header.print_debug()




def main(argv):
    filename = argv[0]

    read_header(filename)





if __name__ == "__main__":
    if len(sys.argv) != 2:
        usage(sys.argv, 1)
    main(sys.argv[1:])
