#!/usr/bin/env python 
#

import struct
import argparse
import sys

# qemu writes each blob header as uint64_t, in native-endian
BLOB_HEADER_FMT = "=Q"
BLOB_SIZE       = 4096


class _QemuMemoryHeader(object):
    HEADER_MAGIC = 'LibvirtQemudSave'
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
        if magic != self.HEADER_MAGIC:
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


def header_check(mem_file, out_file):
    header_size = struct.calcsize(BLOB_HEADER_FMT)

    # first 8 bytes is file size
    header = mem_file.read(header_size)
    if len(header) != header_size:
        print "couldn't read valid file size header"
        return
    file_size, = struct.unpack(BLOB_HEADER_FMT, header)
    print "memory snapshot size: %ld" % file_size

    if (file_size % BLOB_SIZE) != 0:
        print "reported file size (%d bytes) is not aligned at BLOB_SIZE boundary" % file_size
        return

    blobs = set()
    blob_count = 0
    while True:
        header = mem_file.read(header_size)
        if len(header) == 0:
            break

        if len(header) != header_size:
            print "couldn't read valid blob header"
            break
        blob_offset, = struct.unpack(BLOB_HEADER_FMT, header)

# check for sequentially written blobs
#        if blob_offset != BLOB_SIZE * blob_count:
#            print "blob offset doesn't match expected value ",
#            print "(offset %d expected %d)" % (blob_offset, BLOB_SIZE * blob_count)
#            return

        if (blob_offset % BLOB_SIZE) != 0:
            print "offset in blob header is not aligned"
            return

        blob = blob_offset / BLOB_SIZE
        if blob in blobs:
            print "duplicated blob at :%ld" % blob_offset
            return
        blobs.add(blob)

        blob_count += 1

#        if blob_count < 200:
#            print "blob %d" % (blob_offset / BLOB_SIZE)

        page = mem_file.read(BLOB_SIZE)

        if out_file and len(page) > 0:
            out_file.seek(blob_offset)
            out_file.write(page)

        # file is padded to multiple of BLOB_SIZE
        if len(page) != BLOB_SIZE:
            print "invalid blob size"
            return

    # check if all blobs up to max blob number are there
    passed = True
    for b in range(file_size / BLOB_SIZE):
        if b not in blobs:
            print "blob %d is missing"
            passed = False
            break

    if passed:
        print "test passed (%d blobs, %d processed)" % (file_size / BLOB_SIZE, blob_count)
    else:
        print "test failed (some blobs are missing)"


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
