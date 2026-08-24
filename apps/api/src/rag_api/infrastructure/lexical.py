import hashlib
import math
import re
from itertools import pairwise


def feature_hash_embedding(content: str, dimensions: int = 384) -> list[float]:
    tokens = _tokens(content.casefold())
    features = tokens + [f"{left}::{right}" for left, right in pairwise(tokens)]
    vector = [0.0] * dimensions
    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0 if digest[4] & 1 else -1.0
    magnitude = math.sqrt(sum(value * value for value in vector))
    return [value / magnitude for value in vector] if magnitude else vector


def dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _tokens(content: str) -> list[str]:
    tokens: list[str] = []
    for match in re.finditer(r"[a-z0-9_]+|[\u4e00-\u9fff]+", content):
        value = match.group()
        if value.isascii():
            tokens.append(value)
        else:
            tokens.extend(value)
            tokens.extend(value[index : index + 2] for index in range(len(value) - 1))
    return tokens
