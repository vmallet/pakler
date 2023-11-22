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


def quote_string(string):
    """Return the string surrounded with double-quotes."""
    return f'"{string}"'
