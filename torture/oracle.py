class Oracle:
    def __init__(self):
        self.store = {}
    def put(self, key: bytes, value: bytes) -> None:
        self.store[key] = value
    def delete(self, key: bytes) -> None:
        if key in self.store:
            del self.store[key]
    def get(self, key: bytes) -> bytes | None:
        return self.store.get(key)