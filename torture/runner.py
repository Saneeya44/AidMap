import sys
import os
import random
import subprocess
import argparse
from oracle import Oracle

class TortureRunner:
    def __init__(self, db_path: str, seed: int, iterations: int):
        self.db_path = db_path
        self.seed = seed
        self.iterations = iterations
        random.seed(self.seed)

    def run_command(self, cmd_args):
        full_cmd = [sys.executable, "src/cli.py"] + cmd_args
        return subprocess.run(full_cmd, capture_output=True, text=True)

    def test_sequential(self):
        print(f"[*] Running Sequential Mode with seed {self.seed}...")
        oracle = Oracle()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        for i in range(self.iterations):
            key = f"key_{i}".encode()
            val = f"val_{i}".encode()
            res = self.run_command(["put", self.db_path, key.decode(), val.decode()])
            if res.returncode != 0:
                print(f"[!] Put failed at iteration {i}: {res.stderr}")
                return False
            oracle.put(key, val)
            get_res = self.run_command(["get", self.db_path, key.decode()])
            if val.decode().strip() not in get_res.stdout.strip():
                print(f"[!] Mismatch at iteration {i}!")
                return False
        print("[+] Sequential Mode Passed Successfully!")
        return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--mode", type=str, default="sequential")
    parser.add_argument("--db", type=str, default="test_kv.db")
    args = parser.parse_args()
    runner = TortureRunner(args.db, args.seed, args.iterations)
    if args.mode == "sequential":
        success = runner.test_sequential()
        sys.exit(0 if success else 1)