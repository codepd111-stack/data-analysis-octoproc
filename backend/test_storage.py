"""Checks that file storage works. Run from backend/ with the S3 settings in .env."""
from app.services.storage import get_storage

storage = get_storage()
print("Backend:", type(storage).__name__)

key = "healthcheck/hello.txt"
storage.put_bytes(key, b"hello from OCTOPROC")
print("1. Upload OK")

print("2. Listing:", storage.list_keys("healthcheck"))

path = storage.get_local_path(key)
if type(storage).__name__ == "S3Storage":
    path.unlink()  # drop the cached copy so the next call is a real download
    path = storage.get_local_path(key)
print("3. Download OK:", path.read_bytes())

try:
    missing = storage.get_local_path("healthcheck/does-not-exist.txt")
    print("4. Missing file:", "reported as missing" if not missing.exists() else "UNEXPECTED")
except FileNotFoundError:
    print("4. Missing file: reported as missing (good)")

print("\nAll good. Delete healthcheck/hello.txt from the bucket if you like.")