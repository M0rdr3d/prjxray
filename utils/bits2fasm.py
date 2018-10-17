#!/usr/bin/env python3
'''
Take raw .bits files and decode them to higher level functionality
This output is intended for debugging and not directly related to FASM
However, as of 2018-10-16, the output is being parsed to create FASM,
so be mindful when changing output format

TODO: 
'''

import sys, os, json, re


class NoDB(Exception):
    pass


def line(s=''):
    print(s)


def comment(s):
    print('# %s' % s)


# cache
segbitsdb = dict()


# TODO: migrate to library
def get_database(segtype):
    if segtype in segbitsdb:
        return segbitsdb[segtype]

    main_fn = "%s/%s/segbits_%s.db" % (
        os.getenv("XRAY_DATABASE_DIR"), os.getenv("XRAY_DATABASE"),
        segtype.lower())
    int_fn = "%s/%s/segbits_int_%s.db" % (
        os.getenv("XRAY_DATABASE_DIR"), os.getenv("XRAY_DATABASE"),
        segtype[-1].lower())

    if not os.path.exists(main_fn) or not os.path.exists(int_fn):
        raise NoDB(segtype)

    segbitsdb[segtype] = list()

    with open(main_fn, "r") as f:
        for line in f:
            line = line.split()
            segbitsdb[segtype].append(line)

    with open(int_fn, "r") as f:
        for line in f:
            line = line.split()
            segbitsdb[segtype].append(line)

    return segbitsdb[segtype]


def mk_segbits(seginfo, bitdata):
    baseframe = int(seginfo["baseaddr"][0], 16)
    basewordidx = int(seginfo["baseaddr"][1])
    numframes = int(seginfo["frames"])
    numwords = int(seginfo["words"])

    segbits = set()
    for frame in range(baseframe, baseframe + numframes):
        if frame not in bitdata:
            continue
        for wordidx in range(basewordidx, basewordidx + numwords):
            if wordidx not in bitdata[frame]:
                continue
            for bitidx in bitdata[frame][wordidx]:
                segbits.add(
                    "%02d_%02d" %
                    (frame - baseframe, 32 * (wordidx - basewordidx) + bitidx))
    return segbits


def tagmatch(entry, segbits):
    for bit in entry[1:]:
        if bit[0] != "!" and bit not in segbits:
            return False
        if bit[0] == "!" and bit[1:] in segbits:
            return False
    return True


def tag_matched(entry, segbits):
    for bit in entry[1:]:
        if bit[0] != "!":
            segbits.remove(bit)


def seg_decode(seginfo, segbits):
    fasms = set()

    try:
        for entry in get_database(seginfo["type"]):
            if not tagmatch(entry, segbits):
                continue
            tag_matched(entry, segbits)
            fasms.add('%s.%s 1' % (seginfo['tile_name'], entry[0]))
    except NoDB:
        print("WARNING: failed to load DB for %s" % seginfo["type"])
    return fasms


def handle_segment(segname, grid, bitdata):

    assert segname

    # only print bitstream tiles
    if segname not in grid["segments"]:
        return
    seginfo = grid["segments"][segname]

    segbits = mk_segbits(seginfo, bitdata)

    fasms = seg_decode(seginfo, segbits)

    # Found something to print?
    if len(segbits) == 0 and len(fasms) == 0:
        return

    line('')
    comment("seg %s" % (segname, ))

    for fasm in sorted(fasms):
        print(fasm)

    if len(segbits) > 0:
        comment('WARNING: %u unknown bits' % len(segbits))
        for bit in sorted(segbits):
            comment("bit %s" % bit)


def load_bitdata(bits_file):
    bitdata = dict()

    with open(bits_file, "r") as f:
        for line in f:
            line = line.split("_")
            frame = int(line[1], 16)
            wordidx = int(line[2], 10)
            bitidx = int(line[3], 10)

            if frame not in bitdata:
                bitdata[frame] = dict()

            if wordidx not in bitdata[frame]:
                bitdata[frame][wordidx] = set()

            bitdata[frame][wordidx].add(bitidx)
    return bitdata


def mk_grid():
    '''Load tilegrid, flattening all blocks into one dictionary'''

    with open("%s/%s/tilegrid.json" % (os.getenv("XRAY_DATABASE_DIR"),
                                       os.getenv("XRAY_DATABASE")), "r") as f:
        new_grid = json.load(f)

    # TODO: Migrate to new tilegrid format via library.
    grid = {'tiles': new_grid, 'segments': {}}

    for tile_name, tile in grid['tiles'].items():
        bits = tile.get('bits', None)
        if not bits:
            continue
        for block_name, block in bits.items():
            segname = mksegment(tile_name, block_name)
            grid['segments'][segname] = {
                'baseaddr': [
                    block['baseaddr'],
                    block['offset'],
                ],
                'type': tile['type'],
                'frames': block['frames'],
                'words': block['words'],
                'tile_name': tile_name,
                'block_name': block_name,
            }
    return grid


def mksegment(tile_name, block_name):
    '''Create a segment name'''
    return '%s:%s' % (tile_name, block_name)


def tile_segnames(grid):
    ret = []
    for tile_name, tile in grid['tiles'].items():
        for block_name in tile['bits'].keys():
            ret.append(mksegment(tile_name, block_name))
    return ret


def run(bits_file, segnames, verbose=False):
    grid = mk_grid()

    bitdata = load_bitdata(bits_file)

    # Default: print all
    if segnames:
        for i, segname in enumerate(segnames):
            # Default to common tile config area if tile given without explicit block
            if ':' not in segname:
                segnames[i] = mksegment(segname, 'CLB_IO_CLK')
    else:
        segnames = sorted(tile_segnames(grid))

    comment('Segments: %u' % len(segnames))

    # XXX: previously this was sorted by address, not name
    # revisit?
    for segname in segnames:
        handle_segment(segname, grid, bitdata)


def main():
    import argparse

    # XXX: tool still works, but not well
    # need to eliminate segments entirely
    parser = argparse.ArgumentParser(
        description='XXX: does not print all data?')

    parser.add_argument('--verbose', action='store_true', help='')
    parser.add_argument('bits_file', help='')
    parser.add_argument(
        'segnames', nargs='*', help='List of tile or tile:block to print')
    args = parser.parse_args()

    run(args.bits_file, args.segnames, verbose=args.verbose)


if __name__ == '__main__':
    main()
