import hashlib
import sys


def calculate_sha256_hexdigest(filename):
    sha256_hash = hashlib.sha256()

    try:
        with open(filename, "rb") as f:
            # Read and update hash string value in blocks of 4K
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except FileNotFoundError:
        print(f"Error: The file '{filename}' was not found.")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python sha256_hash.py <filename>")
        sys.exit(1)

    filename = sys.argv[1]
    hexdigest = calculate_sha256_hexdigest(filename)
    print(hexdigest)
