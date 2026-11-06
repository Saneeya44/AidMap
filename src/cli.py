# src/cli.py
# CLI launcher and command handler for KVDB

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    if len(sys.argv) < 2:
        print("Usage: python src/cli.py <command> [args...]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "put":
        if len(sys.argv) < 5:
            print("Usage: python src/cli.py put <path> <key> <value>")
            sys.exit(1)
        db_path = sys.argv[2]
        key = sys.argv[3]
        value = sys.argv[4]
        
        with open(db_path, "a", encoding="utf-8") as f:
            f.write(f"PUT {key} {value}\n")
        print("OK")

    elif command == "get":
        if len(sys.argv) < 4:
            print("Usage: python src/cli.py get <path> <key>")
            sys.exit(1)
        db_path = sys.argv[2]
        key = sys.argv[3]
        
        found_val = "NOTFOUND"
        if os.path.exists(db_path):
            with open(db_path, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split(" ", 2)
                    if len(parts) == 3 and parts[0] == "PUT" and parts[1] == key:
                        found_val = parts[2]
        print(found_val)

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()