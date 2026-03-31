#!/usr/bin/env python3
"""
Anno 2205 Save Game Tool
Usage:
    anno2205_save.py <savefile> dump [--csv]
    anno2205_save.py <savefile> set <field> <value>   (not yet implemented)

File format (reverse engineered):
    Bytes 0x000-0x007: Magic/version header (LE uint32 at 0 = 0x224 = 548)
    Bytes 0x008-0x027: 32-byte ASCII hex hash (MD5 or similar)
    Bytes 0x028-0x227: Null-padded header block
    Bytes 0x228-EOF  : zlib-compressed game data (magic: 78 DA)

Decompressed data format — tag-value binary stream:
    Each field:
        field_id  : 1 byte
        0x80      : marker byte
        type/len  : 1 byte
            0x01 = bool/uint8  (1 byte value)
            0x02 = uint16 LE   (2 byte value)
            0x04 = uint32 LE   (4 byte value)
            0x08 = uint64 LE   (8 byte value)
            N    = UTF-16LE string, N bytes long (N/2 characters, no null terminator)
        value     : type-dependent bytes

    Compact inline: field_id followed by a non-0x80 byte encodes a small value
    with no separate type marker (e.g. 02 00 = field 2, value 0).

Known top-level fields:
    0x01 = internal format version    (uint32 = 2)
    0x02 = CorporationFileVersion     (compact inline)
    0x03 = CorporationName            (UTF-16LE, length-prefixed)
    0x04 = CorporationLogo            (UTF-16LE, length-prefixed)
    0x05 = CorporationGUID            (uint32)
    0x26 = CorporationLevel           (uint32)

DifficultySettings fields (field_id 0x06-0x25, type uint16):
    Values: 0=Easy, 1=Normal, 2=Hard
    (DifficultyTraderPrices 0x25 uses uint32 with wider range)
"""

import sys
import zlib
import struct
import csv
import io
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Field name maps
# ---------------------------------------------------------------------------

DIFFICULTY_FIELDS = {
    0x06: "DifficultyConstructionCostRefund",
    0x07: "DifficultySatisfactionInfluencesTaxes",
    0x08: "DifficultyTemporarySectorEffects",
    0x09: "DifficultyConsumption",
    0x0a: "DifficultyDominanceAgriculture",
    0x0b: "DifficultyOptionalQuestTimeout",
    0x0c: "DifficultyNpcLevelSpeed",
    0x0d: "DifficultyRevenue",
    0x0e: "DifficultyWorkforce",
    0x0f: "DifficultyTraderRefillRate",
    0x10: "DifficultyDistributionCenterOutput",
    0x11: "DifficultyMetropolisFactor",
    0x12: "DifficultyMilitaryProgress",
    0x13: "DifficultyPermanentSectorEffects",
    0x14: "DifficultyIncreasingDistributionCenterCosts",
    0x15: "DifficultyMilitaryEnemyStrength",
    0x16: "DifficultyRelocateBuildings",
    0x17: "DifficultyTradeRouteAdminCosts",
    0x18: "DifficultyOptionalQuestFrequency",
    0x19: "DifficultyDominanceHiTech",
    0x1a: "DifficultyDominanceHeavy",
    0x1b: "DifficultyDominanceEnergy",
    0x1c: "DifficultyDominanceBiotech",
    0x1d: "DifficultyDominanceShareBonus",
    0x1e: "DifficultyInactiveCosts",
    0x1f: "DifficultyDestructibleShips",
    0x20: "DifficultyMilitaryProgress2",
    0x21: "DifficultyMilitaryInvasions",
    0x22: "DifficultyMilitaryEnemyStrength2",
    0x23: "DifficultyStartCredits",
    0x24: "DifficultyFacilityAuctions",
    0x25: "DifficultyTraderPrices",
}

# ---------------------------------------------------------------------------
# Parsing constants
# ---------------------------------------------------------------------------

RAW_HEADER_SIZE        = 0x008
HASH_OFFSET            = 0x008
HASH_SIZE              = 0x020   # 32 ASCII hex bytes
ZLIB_SEARCH_START      = 0x028
DIFFICULTY_BLOCK_START = 0x08a   # fallback; computed dynamically per save

# String field encoding: field_id 0x80 [byte_len] [utf-16le data]
# The third byte is the BYTE LENGTH of the string (not a type code).
# byte_len / 2 = number of UTF-16LE characters. No null terminator.
# Example: 03 80 1e -> field 3, 0x1e=30 bytes = 15 chars = "Eden Initiative"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SaveMetadata:
    file_version: int = 0
    raw_hash: str = ""
    corporation_name: str = ""
    corporation_logo: str = ""
    corporation_guid: int = 0
    corporation_time: int = 0    # field 0x26 in game session object (in-game turns/time)
    zlib_offset: int = 0
    compressed_size: int = 0
    decompressed_size: int = 0
    _difficulty_offset: int = 0   # set dynamically by parse_metadata

@dataclass
class DifficultySettings:
    values: dict = field(default_factory=dict)  # field_id -> value

    def get(self, name: str) -> Optional[int]:
        for fid, fname in DIFFICULTY_FIELDS.items():
            if fname == name:
                return self.values.get(fid)
        return None

    def set(self, name: str, value: int) -> bool:
        for fid, fname in DIFFICULTY_FIELDS.items():
            if fname == name:
                self.values[fid] = value
                return True
        return False

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _read_utf16le_len(data: bytes, offset: int, byte_len: int) -> str:
    """Read a length-prefixed UTF-16LE string (no null terminator)."""
    return data[offset: offset + byte_len].decode("utf-16-le", errors="replace")


def parse_metadata(raw: bytes, dec: bytes, zlib_offset: int) -> SaveMetadata:
    """
    Parse save metadata from raw file header and decompressed data.

    Decompressed layout (verified by reverse engineering):
      0x000: 01 80 04 [uint32]        field 1 (internal format version = 2)
      0x007: 02 00 03 00 04 00        fields 2,3,4 compact-inline (value 0, no type byte)
      0x00d: 00 80 04 [uint32] x3     GUID fragments (field_id = 0x00)
      0x024: 02 80 04 [uint32]        secondary GUID / timestamp
      0x02b: 03 80 [N] [N bytes]      CorporationName  (UTF-16LE, N = byte length)
      0x04c: 04 80 [N] [N bytes]      CorporationLogo  (UTF-16LE, N = byte length)
      0x081: 05 80 04 [uint32]        CorporationGUID
      0x088: 05 00                    compact-inline null
      0x08a: 06 80 02 [uint16] ...    DifficultySettings block starts

    String encoding: field_id 0x80 [byte_len] [byte_len bytes of UTF-16LE].
    The third byte is the raw byte count, NOT a type identifier.
    """
    meta = SaveMetadata()

    # Raw file header
    meta.file_version      = struct.unpack_from("<I", raw, 0)[0]
    meta.raw_hash          = raw[HASH_OFFSET: HASH_OFFSET + HASH_SIZE].decode("ascii", errors="replace")
    meta.zlib_offset       = zlib_offset
    meta.compressed_size   = len(raw) - zlib_offset
    meta.decompressed_size = len(dec)

    # CorporationName: field 3, starts at fixed offset 0x02b
    # 03 80 [byte_len] [utf16le data]
    CORP_NAME_OFF = 0x02b
    if dec[CORP_NAME_OFF] == 0x03 and dec[CORP_NAME_OFF + 1] == 0x80:
        name_byte_len = dec[CORP_NAME_OFF + 2]
        meta.corporation_name = _read_utf16le_len(dec, CORP_NAME_OFF + 3, name_byte_len)
        pos = CORP_NAME_OFF + 3 + name_byte_len
    else:
        pos = CORP_NAME_OFF

    # CorporationLogo: field 4, immediately after name
    # 04 80 [byte_len] [utf16le data]
    if pos + 2 < len(dec) and dec[pos] == 0x04 and dec[pos + 1] == 0x80:
        logo_byte_len = dec[pos + 2]
        meta.corporation_logo = _read_utf16le_len(dec, pos + 3, logo_byte_len)
        pos = pos + 3 + logo_byte_len
    
    # CorporationGUID: field 5, immediately after logo
    # 05 80 04 [uint32]
    if pos + 6 < len(dec) and dec[pos] == 0x05 and dec[pos + 1] == 0x80 and dec[pos + 2] == 0x04:
        meta.corporation_guid = struct.unpack_from("<I", dec, pos + 3)[0]
        pos = pos + 7

    # Store the computed difficulty block start for use by parse_difficulty
    # Skip the compact-inline field (05 00) if present
    if pos + 1 < len(dec) and dec[pos] == 0x05 and dec[pos + 1] != 0x80:
        pos += 2
    meta._difficulty_offset = pos  # dynamic offset for difficulty block

    # CorporationTime: field 0x26 (uint32), first occurrence after the difficulty block.
    # In-game this appears to be a turn/progression counter that correlates with
    # campaign progress. In new/fresh saves this field may hold an uninitialized value.
    for off in range(pos, min(pos + 0x2000, len(dec) - 6)):
        if dec[off] == 0x26 and dec[off + 1] == 0x80 and dec[off + 2] == 0x04:
            meta.corporation_time = struct.unpack_from("<I", dec, off + 3)[0]
            break

    return meta


def parse_difficulty(dec: bytes, start: int = DIFFICULTY_BLOCK_START) -> DifficultySettings:
    """
    Parse the DifficultySettings block starting at `start`.

    All difficulty fields (0x06-0x25) are encoded as uint16 (type byte 0x02).
    The block may contain compact-inline entries (second byte != 0x80) which are
    skipped. Parsing stops as soon as a known difficulty field_id appears with a
    type other than u16 — that signals the session-object fields have begun
    (they reuse the same field IDs but with u32/u64/string types).

    Field encoding:
        [field_id] 0x80 0x02 [uint16 LE]   — difficulty value (0=Easy, 1=Normal, 2=Hard)
        [field_id] [non-0x80]              — compact-inline; skip 2 bytes
        [field_id] 0x80 0x04/0x08/…       — session field reusing ID; stop here
    """
    settings = DifficultySettings()
    pos = start

    while pos < len(dec) - 4:
        fid = dec[pos]

        # Compact-inline (second byte is not 0x80): always skip 2 bytes
        if dec[pos + 1] != 0x80:
            pos += 2
            continue

        type_b = dec[pos + 2]

        # Any field above the difficulty range: we've left the block
        if fid > 0x25:
            break

        # Known difficulty field with non-u16 type → session fields have begun
        if fid in DIFFICULTY_FIELDS and type_b != 0x02:
            break

        if type_b == 0x02:
            val = struct.unpack_from("<H", dec, pos + 3)[0]
            if fid in DIFFICULTY_FIELDS:
                settings.values[fid] = val
            pos += 5
        elif type_b == 0x04:
            pos += 7
        elif type_b == 0x08:
            pos += 11
        else:
            pos += 3 + type_b

    return settings


def load_save(path: str):
    """
    Load and decompress a save file.
    Returns (raw_bytes, decompressed_bytes, zlib_offset).
    """
    with open(path, "rb") as f:
        raw = f.read()

    # Find zlib magic (78 DA)
    zlib_offset = raw.find(b"\x78\xda", ZLIB_SEARCH_START)
    if zlib_offset < 0:
        raise ValueError("No zlib stream found in save file")

    dec = zlib.decompress(raw[zlib_offset:])
    return raw, dec, zlib_offset


# ---------------------------------------------------------------------------
# Write back (skeleton for future 'set' command)
# ---------------------------------------------------------------------------

def _patch_difficulty(dec: bytes, settings: DifficultySettings, start: int = DIFFICULTY_BLOCK_START) -> bytes:
    """
    Write updated DifficultySettings values back into decompressed data.
    Returns modified decompressed bytes.
    """
    buf = bytearray(dec)
    pos = start

    while pos < len(buf) - 4:
        fid = buf[pos]

        if buf[pos + 1] != 0x80:
            if fid > 0x25:
                break
            pos += 2
            continue

        type_b = buf[pos + 2]
        if fid > 0x25:
            break

        new_val = settings.values.get(fid)

        if type_b == 0x02:
            if new_val is not None and fid in DIFFICULTY_FIELDS:
                struct.pack_into("<H", buf, pos + 3, new_val)
            pos += 5
        elif type_b == 0x04:
            if new_val is not None and fid in DIFFICULTY_FIELDS:
                struct.pack_into("<I", buf, pos + 3, new_val)
            pos += 7
        elif type_b == 0x08:
            pos += 11
        else:
            pos += 3 + type_b

    return bytes(buf)


def save_file(path: str, raw: bytes, dec: bytes, zlib_offset: int):
    """
    Recompress and write modified save. Does NOT update the hash yet
    (hash algorithm unknown — the game may recalculate it on load).
    """
    compressed = zlib.compress(dec, level=6)
    # zlib.compress uses deflate with header; Anno uses 78 DA (default compression)
    # Verify the magic matches
    if compressed[:2] != b"\x78\x9c" and compressed[:2] != b"\x78\xda":
        raise ValueError(f"Unexpected zlib magic after recompression: {compressed[:2].hex()}")

    new_raw = raw[:zlib_offset] + compressed
    with open(path, "wb") as f:
        f.write(new_raw)


# ---------------------------------------------------------------------------
# Dump command
# ---------------------------------------------------------------------------

def cmd_dump(path: str, as_csv: bool = False):
    raw, dec, zlib_offset = load_save(path)
    meta = parse_metadata(raw, dec, zlib_offset)
    difficulty = parse_difficulty(dec, start=meta._difficulty_offset)

    if as_csv:
        _dump_csv(meta, difficulty)
    else:
        _dump_human(path, meta, difficulty)


def _dump_human(path: str, meta: SaveMetadata, difficulty: DifficultySettings):
    print(f"=== Anno 2205 Save: {path} ===\n")

    print("[Metadata]")
    print(f"  File version        : 0x{meta.file_version:08x} ({meta.file_version})")
    print(f"  Header hash         : {meta.raw_hash}")
    print(f"  Corporation name    : {meta.corporation_name!r}")
    print(f"  Corporation logo    : {meta.corporation_logo!r}")
    print(f"  Corporation GUID    : 0x{meta.corporation_guid:08x} ({meta.corporation_guid})")
    print(f"  Corporation time    : {meta.corporation_time}")
    print(f"  Compressed size     : {meta.compressed_size:,} bytes")
    print(f"  Decompressed size   : {meta.decompressed_size:,} bytes")

    print("\n[Difficulty Settings]")
    print(f"  {'Field':<50} {'Raw':>5}")
    print(f"  {'-'*50} {'-'*5}")
    for fid in sorted(DIFFICULTY_FIELDS):
        name = DIFFICULTY_FIELDS[fid]
        raw_val = difficulty.values.get(fid)
        if raw_val is None:
            # Field absent in save game treats it as 0
            print(f"  {name:<50} {'unset':>5}")
        else:
            print(f"  {name:<50} {raw_val!r:>5}")


def _dump_csv(meta: SaveMetadata, difficulty: DifficultySettings):
    out = io.StringIO()
    w = csv.writer(out)

    # Metadata section
    w.writerow(["section", "field", "value"])
    w.writerow(["metadata", "file_version",      f"0x{meta.file_version:08x}"])
    w.writerow(["metadata", "header_hash",        meta.raw_hash])
    w.writerow(["metadata", "corporation_name",   meta.corporation_name])
    w.writerow(["metadata", "corporation_logo",   meta.corporation_logo])
    w.writerow(["metadata", "corporation_guid",   f"0x{meta.corporation_guid:08x}"])
    w.writerow(["metadata", "corporation_time",   meta.corporation_time])
    w.writerow(["metadata", "compressed_size",    meta.compressed_size])
    w.writerow(["metadata", "decompressed_size",  meta.decompressed_size])

    # Difficulty section — absent fields default to 0 (Easy)
    for fid in sorted(DIFFICULTY_FIELDS):
        name = DIFFICULTY_FIELDS[fid]
        val = difficulty.values.get(fid)
        if val is None:
            w.writerow(["difficulty", name, 'unset'])
        else:
            w.writerow(["difficulty", name, val])

    print(out.getvalue(), end="")


# ---------------------------------------------------------------------------
# set command (skeleton)
# ---------------------------------------------------------------------------

def cmd_set(path: str, field_name: str, value: int):
    """
    Set a difficulty field to a new value and write the save back.
    Backs up the original file to <path>.bak first.
    """
    import shutil
    raw, dec, zlib_offset = load_save(path)
    meta = parse_metadata(raw, dec, zlib_offset)
    difficulty = parse_difficulty(dec, start=meta._difficulty_offset)

    if field_name not in DIFFICULTY_FIELDS.values():
        print(f"ERROR: Unknown field '{field_name}'")
        print("Known fields:")
        for name in sorted(DIFFICULTY_FIELDS.values()):
            print(f"  {name}")
        sys.exit(1)

    old_val = difficulty.get(field_name)
    difficulty.set(field_name, value)

    new_dec = _patch_difficulty(dec, difficulty, start=meta._difficulty_offset)

    backup = path + ".bak"
    shutil.copy2(path, backup)
    print(f"Backed up original to: {backup}")

    save_file(path, raw, new_dec, zlib_offset)
    print(f"Set {field_name}: {old_val} -> {value}")
    print(f"Saved: {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]

    if len(args) < 2:
        print(__doc__)
        sys.exit(1)

    save_path = args[0]
    command   = args[1].lower()

    if command == "dump":
        as_csv = "--csv" in args
        cmd_dump(save_path, as_csv=as_csv)

    elif command == "set":
        if len(args) < 4:
            print("Usage: anno2205_save.py <savefile> set <field_name> <value>")
            sys.exit(1)
        field_name = args[2]
        try:
            value = int(args[3])
        except ValueError:
            print(f"ERROR: value must be an integer, got '{args[3]}'")
            sys.exit(1)
        cmd_set(save_path, field_name, value)

    else:
        print(f"Unknown command: {command}")
        print("Commands: dump [--csv]  |  set <field> <value>")
        sys.exit(1)


if __name__ == "__main__":
    main()
