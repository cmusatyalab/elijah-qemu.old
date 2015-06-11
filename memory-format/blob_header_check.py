#!/usr/bin/env python 
#

import struct
import argparse

# qemu writes each blob header as uint64_t, in native-endian
BLOB_HEADER_FMT  = "=Q"
BLOB_HEADER_SIZE = struct.calcsize(BLOB_HEADER_FMT)
BLOB_SIZE        = 4096

ITER_SEQ_BITS   = 16
ITER_SEQ_SHIFT  = BLOB_HEADER_SIZE * 8 - ITER_SEQ_BITS
BLOB_POS_MASK   = (1 << ITER_SEQ_SHIFT) - 1
ITER_SEQ_MASK   = ((1 << (BLOB_HEADER_SIZE * 8)) - 1) - BLOB_POS_MASK

def header_check(mem_file, out_file):
    # first 8 bytes is file size
    header = mem_file.read(BLOB_HEADER_SIZE)
    if len(header) != BLOB_HEADER_SIZE:
        print "couldn't read valid file size header"
        return
    file_size, = struct.unpack(BLOB_HEADER_FMT, header)

    if (file_size % BLOB_SIZE) != 0:
        print "reported file size (%d bytes) is not aligned at BLOB_SIZE boundary" % file_size
        return

    print "file size in header: %d" % file_size

    count_per_seq = {}
    blobs = set()
    blob_count = 0

    while True:
        header = mem_file.read(BLOB_HEADER_SIZE)
        if len(header) == 0:
            break

        if len(header) != BLOB_HEADER_SIZE:
            print "couldn't read valid blob header"
            break
        blob_offset, = struct.unpack(BLOB_HEADER_FMT, header)
        iter_seq = (blob_offset & ITER_SEQ_MASK) >> ITER_SEQ_SHIFT
        blob_offset = blob_offset & BLOB_POS_MASK

        if (blob_offset % BLOB_SIZE) != 0:
            print "offset in blob header is not aligned"
            return

        blob = blob_offset / BLOB_SIZE
        blobs.add(blob)
        blob_count += 1
        if iter_seq not in count_per_seq:
            count_per_seq[iter_seq] = 0
        count_per_seq[iter_seq] += 1

        page = mem_file.read(BLOB_SIZE)

        if out_file and len(page) > 0:
            out_file.seek(blob_offset)
            out_file.write(page)

        # file is padded to multiple of BLOB_SIZE
        if len(page) != BLOB_SIZE:
            print "invalid blob size for offset %d" % blob_offset
            return

    # check if all blobs up to max blob number are there
    passed = True
    for b in range(file_size / BLOB_SIZE):
        if b not in blobs:
            print "blob %d is missing" % b
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
        for iter_seq in count_per_seq:
            print "iteration %4d: %8d blobs" % (iter_seq, count_per_seq[iter_seq])
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
