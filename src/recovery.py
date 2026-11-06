
"""Crash recovery for the append-only KV database."""

import os
import struct

from src.format import (
    HEADER_SIZE,
    MAX_BATCH_SIZE,
    MAX_KEY_SIZE,
    MAX_VALUE_SIZE,
    CorruptFrameError,
    decode_transaction,
)

# A transaction contains a 4-byte operation count.
# Each operation contains 7 bytes of metadata.
MAX_PAYLOAD_SIZE = (
    4 + MAX_BATCH_SIZE * (7 + MAX_KEY_SIZE + MAX_VALUE_SIZE)
)

TRAILER_SIZE = 8  # CRC32 (4 bytes) + CMIT (4 bytes)


def recover(fh) -> tuple[dict[bytes, bytes | None], int]:
    """Replay valid transactions without modifying the file."""

    if fh.tell() != HEADER_SIZE:
        raise ValueError("recovery must begin at offset 5")

    index: dict[bytes, bytes | None] = {}
    valid_end = fh.tell()

    # Find the file size without losing our position.
    fh.seek(0, os.SEEK_END)
    file_size = fh.tell()
    fh.seek(valid_end)

    while fh.tell() < file_size:
        frame_start = fh.tell()

        # Read the payload-length prefix.
        length_bytes = fh.read(4)

        if len(length_bytes) < 4:
            # Incomplete final length prefix.
            return index, valid_end

        payload_length = struct.unpack("<I", length_bytes)[0]

        if not 4 <= payload_length <= MAX_PAYLOAD_SIZE:
            raise CorruptFrameError(
                f"invalid payload length at offset {frame_start}"
            )

        frame_size = 4 + payload_length + TRAILER_SIZE

        if frame_start + frame_size > file_size:
            # Incomplete final transaction.
            return index, valid_end

        # The full frame exists. Validate it using
        # Person 1's format decoder.
        fh.seek(frame_start)
        frame = fh.read(frame_size)

        if len(frame) != frame_size:
            raise OSError("short read while recovering complete frame")

        operations = decode_transaction(frame)

        # Only apply operations AFTER validation succeeds.
        for kind, key, value in operations:
            if kind == "put":
                index[key] = value
            elif kind == "delete":
                index[key] = None
            else:
                raise CorruptFrameError(
                    f"unsupported operation: {kind}"
                )

        valid_end = fh.tell()

    return index, valid_end
