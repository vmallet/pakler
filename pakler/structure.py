from ctypes import LittleEndianStructure, c_char, c_uint32, c_uint64, sizeof
from typing import Any, Iterator, Union

from pakler.types import IOBytes


class _Base(LittleEndianStructure):

    def __iter__(self) -> "Iterator[tuple[str, Any]]":
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
    def from_fd(cls, fd: IOBytes):
        return cls.from_buffer_copy(fd.read(sizeof(cls)))


class _PAKHeader(_Base):

    _magic: int
    _crc32: int
    _type: int

    @property
    def magic(self) -> int:
        return self._magic

    @property
    def crc32(self) -> int:
        return self._crc32

    @property
    def type(self) -> int:
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
    _name: bytes
    _version: bytes
    _start: int
    _len: int

    @property
    def name(self) -> str:
        return self._name.decode()

    @property
    def version(self) -> str:
        return self._version.decode()

    @property
    def start(self) -> int:
        return self._start

    @property
    def len(self) -> int:
        return self._len

    def __repr__(self) -> str:
        return f"{self.__class__.__qualname__}({self.name!r})"

    def debug_str(self, num: int) -> str:
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
    _name: bytes
    _a: int
    _mtd: bytes
    _start: int
    _len: int

    @property
    def name(self) -> str:
        return self._name.decode()

    @property
    def a(self) -> int:
        return self._a

    @property
    def mtd(self) -> str:
        return self._mtd.decode()

    @property
    def start(self) -> int:
        return self._start

    @property
    def len(self) -> int:
        return self._len

    def __repr__(self) -> str:
        return f"{self.__class__.__qualname__}({self.name!r})"

    def debug_str(self) -> str:
        return 'Mtd_part name={:16} mtd={:16}  a=0x{:08x}  start=0x{:08x}  len=0x{:08x}'.format(
            quote_string(self.name), quote_string(self.mtd), self.a, self.start, self.len)


class PAKSHeader(_Base):
    _fields_ = [
        ("_magic", c_uint32),
        ("_unknown0", c_uint32),  # one of these is probably a checksum (maybe both)
        ("_file_size", c_uint32),
        ("_unknown1", c_uint32),  # always 1?
        ("_unknown2", c_uint32),  # always 0?
        ("_bdid", c_uint32),
        ("_unknown3", c_uint32),  # one of these is probably a checksum (maybe both)
        ("_hwver", c_char * 32),
        ("_fwver", c_char * 32),
        ("_data_size", c_uint32),  # _file_size - 104 (header size)
        ("_nb_sections", c_uint32),
        ("_unknown4", c_uint32),  # always 0?
    ]
    _magic: int
    _unknown0: int
    _file_size: int
    _unknown1: int
    _unknown2: int
    _bdid: int
    _unknown3: int
    _hwver: bytes
    _fwver: bytes
    _data_size: int
    _nb_sections: int
    _unknown4: int

    @property
    def magic(self) -> int:
        return self._magic

    @property
    def file_size(self) -> int:
        return self._file_size

    @property
    def hwver(self) -> str:
        return self._hwver.decode()

    @property
    def fwver(self) -> str:
        return self._fwver.decode()

    @property
    def data_size(self) -> int:
        return self._data_size

    @property
    def nb_sections(self) -> int:
        return self._nb_sections


class PAKSSection(_Base):
    _fields_ = [
        ("_imgs", c_uint32),
        ("_checksum", c_uint32),
        ("_name", c_char * 32),
        ("_version", c_char * 32),
        ("_len", c_uint32),
        ("_unknown0", c_uint32),  # may be equal for different firmwares of the same device. might be needed during upgrade process?. always higher than previous section's?
        ("_unknown1", c_uint32),  # may be equal for different firmwares of the same device. might be needed during upgrade process?
        ("_unknown2", c_uint32),  # always 0?
    ]
    _imgs: int
    _checksum: int
    _name: bytes
    _version: bytes
    _len: int
    _unknown0: int
    _unknown1: int
    _unknown2: int
    _start: int

    @property
    def checksum(self) -> int:
        return self._checksum

    @property
    def name(self) -> str:
        return self._name.decode()

    @property
    def version(self) -> str:
        return self._version.decode()

    @property
    def len(self) -> int:
        return self._len

    @property
    def start(self) -> int:
        return self._start

    def __repr__(self) -> str:
        return f"{self.__class__.__qualname__}({self.name!r})"

    def debug_str(self, num: int) -> str:
        return 'Section {:2} name={:16} version={:16} start=0x{:08x}  len=0x{:08x}  (start={:8} len={:8})'.format(
            num, quote_string(self.name), quote_string(self.version), self.start, self.len, self.start, self.len)


def quote_string(string: str) -> str:
    """Return the string surrounded with double-quotes."""
    return f'"{string}"'


Header = Union[PAK32Header, PAK64Header, PAKSHeader]
Section = Union[PAK32Section, PAK64Section, PAKSSection]
