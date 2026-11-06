"""Binary file and transaction format for the KV database."""

import struct
import zlib
from collections.abc import Sequence


MAGIC = b"KVDB"
VERSION = 1
HEADER_SIZE = 5

OP_PUT = 1
OP_DEL = 2

COMMIT_MAGIC = b"CMIT"
MAX_KEY_SIZE = 1024
MAX_VALUE_SIZE = 1024 * 1024
MAX_BATCH_SIZE = 10_000
MAX_FRAME_SIZE = 0xFFFFFFFF

_HEADER = struct.Struct("<4sB")
_LENGTH = struct.Struct("<I")
_CRC = struct.Struct("<I")
_OP_HEADER = struct.Struct("<BHI")

Operation = tuple[str, bytes, bytes | None]


class CorruptFrameError(Exception):
    """Raised when a header or transaction frame is structurally invalid."""


def encode_header() -> bytes:
    return _HEADER.pack(MAGIC, VERSION)


def validate_header(header: bytes) -> None:
    if len(header) != HEADER_SIZE:
        raise CorruptFrameError("incomplete database header")
    magic, version = _HEADER.unpack(header)
    if magic != MAGIC:
        raise CorruptFrameError("invalid database magic")
    if version != VERSION:
        raise CorruptFrameError(f"unsupported database version: {version}")


def encode_transaction(ops: Sequence[Operation]) -> bytes:
    if not 1 <= len(ops) <= MAX_BATCH_SIZE:
        raise ValueError(f"transaction must contain 1..{MAX_BATCH_SIZE} operations")

    payload = bytearray(_LENGTH.pack(len(ops)))
    for operation in ops:
        if not isinstance(operation, tuple) or len(operation) != 3:
            raise TypeError("each operation must be a (type, key, value) tuple")
        kind, key, value = operation
        if not isinstance(key, bytes):
            raise TypeError("key must be bytes")
        if not 1 <= len(key) <= MAX_KEY_SIZE:
            raise ValueError(f"key must be 1..{MAX_KEY_SIZE} bytes")

        if kind == "put":
            if not isinstance(value, bytes):
                raise TypeError("put value must be bytes")
            if len(value) > MAX_VALUE_SIZE:
                raise ValueError(f"value must be at most {MAX_VALUE_SIZE} bytes")
            op_type = OP_PUT
            value_bytes = value
        elif kind == "delete":
            if value is not None:
                raise ValueError("delete operation value must be None")
            op_type = OP_DEL
            value_bytes = b""
        else:
            raise ValueError(f"unsupported operation type: {kind!r}")

        payload.extend(_OP_HEADER.pack(op_type, len(key), len(value_bytes)))
        payload.extend(key)
        payload.extend(value_bytes)

    if len(payload) > MAX_FRAME_SIZE:
        raise ValueError("transaction payload exceeds the format size limit")

    return (
        _LENGTH.pack(len(payload))
        + payload
        + _CRC.pack(zlib.crc32(payload) & 0xFFFFFFFF)
        + COMMIT_MAGIC
    )


def decode_transaction(frame: bytes) -> list[Operation]:
    if len(frame) < _LENGTH.size + _LENGTH.size + _CRC.size + len(COMMIT_MAGIC):
        raise CorruptFrameError("transaction frame is too short")

    payload_length = _LENGTH.unpack_from(frame)[0]
    expected_size = _LENGTH.size + payload_length + _CRC.size + len(COMMIT_MAGIC)
    if len(frame) != expected_size:
        raise CorruptFrameError("transaction frame length does not match its prefix")

    payload_start = _LENGTH.size
    payload_end = payload_start + payload_length
    payload = frame[payload_start:payload_end]
    expected_crc = _CRC.unpack_from(frame, payload_end)[0]
    if (zlib.crc32(payload) & 0xFFFFFFFF) != expected_crc:
        raise CorruptFrameError("transaction checksum mismatch")
    if frame[payload_end + _CRC.size:] != COMMIT_MAGIC:
        raise CorruptFrameError("transaction commit marker is missing")

    if len(payload) < _LENGTH.size:
        raise CorruptFrameError("transaction payload is missing its operation count")
    operation_count = _LENGTH.unpack_from(payload)[0]
    if not 1 <= operation_count <= MAX_BATCH_SIZE:
        raise CorruptFrameError("transaction operation count is out of range")

    operations: list[Operation] = []
    offset = _LENGTH.size
    for _ in range(operation_count):
        if len(payload) - offset < _OP_HEADER.size:
            raise CorruptFrameError("truncated operation header")
        op_type, key_length, value_length = _OP_HEADER.unpack_from(payload, offset)
        offset += _OP_HEADER.size

        if not 1 <= key_length <= MAX_KEY_SIZE:
            raise CorruptFrameError("operation key length is out of range")
        if value_length > MAX_VALUE_SIZE:
            raise CorruptFrameError("operation value length is out of range")
        if len(payload) - offset < key_length + value_length:
            raise CorruptFrameError("truncated operation data")

        key = payload[offset:offset + key_length]
        offset += key_length
        value_bytes = payload[offset:offset + value_length]
        offset += value_length

        if op_type == OP_PUT:
            operations.append(("put", key, value_bytes))
        elif op_type == OP_DEL and value_length == 0:
            operations.append(("delete", key, None))
        else:
            raise CorruptFrameError("unknown operation type or invalid delete value")

    if offset != len(payload):
        raise CorruptFrameError("unexpected data at end of transaction payload")
    return operations
