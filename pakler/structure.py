from ctypes import LittleEndianStructure, c_char, c_uint32, c_uint64, sizeof


class _Base(LittleEndianStructure):

    def __iter__(self):
        # This allows calling dict() on instances of this class.
        classes = []
        for cls in self.__class__.__mro__:
            classes.append(cls)
            if cls == _Base:
                break
        seen = set()
        for cls in reversed(classes):
            try:
                cls_fields = cls._fields_
            except AttributeError:
                continue
            for field in cls_fields:
                if field not in seen:
                    seen.add(field)
                    name = field[0]
                    prop = name.lstrip('_')
                    try:
                        attr = getattr(self, prop)
                    except AttributeError:
                        attr = getattr(self, name)
                    else:
                        name = prop
                    yield name, dict(attr) if isinstance(attr, _Base) else attr

    @classmethod
    def from_fd(cls, fd):
        return cls.from_buffer_copy(fd.read(sizeof(cls)))


class _PAKHeader(_Base):

    @property
    def magic(self):
        return self._magic

    @property
    def crc32(self):
        return self._crc32

    @property
    def type(self):
        return self._type


class PAK32Header(_PAKHeader):
    _fields_ = [
        ("_magic", c_uint32),
        ("_crc32", c_uint32),
        ("_type", c_uint32),
    ]


class PAK64Header(_PAKHeader):
    _fields_ = [
        ("_magic", c_uint64),
        ("_crc32", c_uint64),
        ("_type", c_uint64),
    ]


class _PAKSection(_Base):
    _fields_ = [
        ("_name", c_char * 32),
        ("_version", c_char * 24),
    ]

    @property
    def name(self):
        return self._name.decode()

    @property
    def version(self):
        return self._version.decode()

    @property
    def start(self):
        return self._start

    @property
    def len(self):
        return self._len

    def __repr__(self):
        return f"{self.__class__.__qualname__}({self.name!r})"

    def debug_str(self, num):
        return 'Section {:2} name={:16} version={:16} start=0x{:08x}  len=0x{:08x}  (start={:8} len={:8})'.format(
            num, quote_string(self.name), quote_string(self.version), self.start, self.len, self.start, self.len)


class PAK32Section(_PAKSection):
    _fields_ = [
        ("_start", c_uint32),
        ("_len", c_uint32),
    ]


class PAK64Section(_PAKSection):
    _fields_ = [
        ("_start", c_uint64),
        ("_len", c_uint64),
    ]


class PAKPartition(_Base):
    _fields_ = [
        ("_name", c_char * 32),
        ("_a", c_uint32),
        ("_mtd", c_char * 32),
        ("_start", c_uint32),
        ("_len", c_uint32),
    ]

    @property
    def name(self):
        return self._name.decode()

    @property
    def a(self):
        return self._a

    @property
    def mtd(self):
        return self._mtd.decode()

    @property
    def start(self):
        return self._start

    @property
    def len(self):
        return self._len

    def __repr__(self):
        return f"{self.__class__.__qualname__}({self.name!r})"

    def debug_str(self):
        return 'Mtd_part name={:16} mtd={:16}  a=0x{:08x}  start=0x{:08x}  len=0x{:08x}'.format(
            quote_string(self.name), quote_string(self.mtd), self.a, self.start, self.len)


class PAKSHeader(_Base):
    _fields_ = [
        # File header
        ("_magic", c_uint32),  # "SKAP" (also accepted: "LOER")
        ("_crc32", c_uint32),  # paks_crc() of everything from offset 8 up to the end of the file
        ("_file_size", c_uint32), # total length of the paks file
        ("_nb_boards", c_uint32), # number of following board headers (paks files can include multiple hardware versions with their own sections)
        ("_ext_len", c_uint32),  # extra bytes skipped between file header and first board header
        # Board header
        ("_board_magic", c_uint32),  # "DIDB"
        ("_board_crc32", c_uint32),  # paks_crc() from _hwver up to the end of the board's data
        ("_hwver", c_char * 32),  # hardware version, e.g. "IPC_560SD88MPW"; matched against the device's board type
        ("_fwver", c_char * 32),  # upgrade is refused if equal to the currently installed version specified in [app]/version.json
        ("_data_size", c_uint32),  # size of everything following the board header (image headers + data)
        ("_nb_sections", c_uint32), # number of following sections for this board
        ("_board_ext_len", c_uint32),  # extra bytes skipped between board header and first image header
    ]

    @property
    def magic(self):
        return self._magic

    @property
    def crc32(self):
        return self._crc32

    @property
    def nb_boards(self):
        return self._nb_boards

    @property
    def ext_len(self):
        return self._ext_len

    @property
    def board_magic(self):
        return self._board_magic

    @property
    def board_crc32(self):
        return self._board_crc32

    @property
    def board_ext_len(self):
        return self._board_ext_len

    @property
    def file_size(self):
        return self._file_size

    @property
    def hwver(self):
        return self._hwver.decode()

    @property
    def fwver(self):
        return self._fwver.decode()

    @property
    def data_size(self):
        return self._data_size

    @property
    def nb_sections(self):
        return self._nb_sections


class PAKSSection(_Base):
    """Image header (0x58 bytes), followed by _ext_len extra bytes and then _len bytes of image data."""
    _fields_ = [
        ("_magic", c_uint32),  # "SGMI"
        ("_checksum", c_uint32),  # paks_crc() of the image data only (excluding header and extra bytes)
        ("_name", c_char * 32),  # partition name
        ("_version", c_char * 32),  # image is skipped if the device already has this name with this version
        ("_len", c_uint32), # total length of the image itself
        ("_flash_offset", c_uint32),  # absolute flash address the image is written to (0xffffffff: not flashed)
        ("_partition_size", c_uint32), # size of the flash partition on the device
        ("_ext_len", c_uint32), # extra bytes skipped between image header and image data
    ]

    @property
    def magic(self):
        return self._magic

    @property
    def checksum(self):
        return self._checksum

    @property
    def flash_offset(self):
        return self._flash_offset

    @property
    def partition_size(self):
        return self._partition_size

    @property
    def ext_len(self):
        return self._ext_len

    @property
    def name(self):
        return self._name.decode()

    @property
    def version(self):
        return self._version.decode()

    @property
    def len(self):
        return self._len

    @property
    def start(self):
        return self._start

    def __repr__(self):
        return f"{self.__class__.__qualname__}({self.name!r})"

    def debug_str(self, num):
        return ('Section {:2} name={:16} version={:24} start=0x{:08x}  len=0x{:08x}  crc32=0x{:08x}'
                '  flash=0x{:08x}  part_size=0x{:08x}').format(
            num, quote_string(self.name), quote_string(self.version), self.start, self.len, self.checksum,
            self.flash_offset, self.partition_size)


def quote_string(string):
    """Return the string surrounded with double-quotes."""
    return f'"{string}"'
