#!/usr/bin/env python 
#

import struct
import argparse

# qemu writes each blob header as uint64_t, in native-endian
BLOB_HEADER_FMT = "=Q"
BLOB_SIZE       = 4096

def header_check(mem_file, out_file):
    header_size = struct.calcsize(BLOB_HEADER_FMT)

    # first 8 bytes is file size
    header = mem_file.read(header_size)
    if len(header) != header_size:
        print "couldn't read valid file size header"
        return
    file_size, = struct.unpack(BLOB_HEADER_FMT, header)

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
        blobs.add(blob)
        blob_count += 1

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

    # check for blobs at offset beyond reported file size
    for b in blobs:
        if (b * BLOB_SIZE) >= file_size:
            print "blob % exceeds reported file size"
            passed = False
            break

    if passed:
        print "test passed (%d blobs, %d processed)" % (file_size / BLOB_SIZE, blob_count)
    else:
        print "test failed"

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('mem_file', type=argparse.FileType('rb'))
    parser.add_argument('out_file', type=argparse.FileType('wb'))
    args = parser.parse_args()

    header_check(args.mem_file, args.out_file)

    args.mem_file.close()
    args.out_file.close()

if __name__ == "__main__":
    main()
