#!/usr/bin/env python 
#

import struct
import argparse
import sys

from blob_header_check import header_check

class _QemuMemoryHeader(object):
    HEADER_MAGIC = 'LibvirtQemudSave'
    HEADER_MAGIC2 = 'LibvirtQemudPart'
    HEADER_VERSION = 2
    HEADER_FORMAT = str(len(HEADER_MAGIC)) + 's19I'
    HEADER_LENGTH = struct.calcsize(HEADER_FORMAT)
    HEADER_UNUSED_VALUES = 15

    COMPRESS_RAW = 0
    COMPRESS_XZ = 3
    COMPRESS_CLOUDLET = 4

    EXPECTED_HEADER_LENGTH = 4096*2

    def __init__(self, f):
        # Read header struct
        f.seek(0)
        buf = f.read(self.HEADER_LENGTH)
        header = list(struct.unpack(self.HEADER_FORMAT, buf))
        magic = header.pop(0)
        version = header.pop(0)
        self._xml_len = header.pop(0)
        self.was_running = header.pop(0)
        self.compressed = header.pop(0)

        # Check header
        if magic != self.HEADER_MAGIC and magic != self.HEADER_MAGIC2:
            raise MachineGenerationError('Invalid memory image magic')
        if version != self.HEADER_VERSION:
            raise MachineGenerationError('Unknown memory image version %d' %
                    version)
        if header != [0] * self.HEADER_UNUSED_VALUES:
            raise MachineGenerationError('Unused header values not 0')

        libvirt_header_len = self._xml_len + self.HEADER_LENGTH
        if libvirt_header_len != self.EXPECTED_HEADER_LENGTH:
            sys.stdout.write("libvirt header length is not aligned with 8KB\n")

        # Read XML, drop trailing NUL padding
        self.xml = f.read(self._xml_len - 1).rstrip('\0')
        if f.read(1) != '\0':
            raise MachineGenerationError('Missing NUL byte after XML')

    def seek_body(self, f):
        f.seek(self.HEADER_LENGTH + self._xml_len)

def process_libvirt_header(mem_file_fd):
    libvirt_header = _QemuMemoryHeader(mem_file_fd)
    libvirt_header.seek_body(mem_file_fd)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('mem_file_fd', type=argparse.FileType('rb'))
    parser.add_argument('out_file', type=argparse.FileType('wb'))
    args = parser.parse_args()

    process_libvirt_header(args.mem_file_fd)
    header_check(args.mem_file_fd, args.out_file)

    args.mem_file_fd.close()
    args.out_file.close()

if __name__ == "__main__":
    main()
