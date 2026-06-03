import requests
import sys

BASE = "http://localhost:8000"
AUTH = ("admin", "admin")
passed = 0
failed = 0

def test(name, expected_status, method="get", path="/", auth=AUTH, **kwargs):
    global passed, failed
    url = f"{BASE}{path}"
    try:
        resp = requests.request(method, url, auth=auth, **kwargs)
        status = resp.status_code
        if status == expected_status:
            print(f"  PASS {name} (status={status})")
            passed += 1
            return resp
        else:
            print(f"  FAIL {name}: expected {expected_status}, got {status}")
            if status != 200:
                print(f"    body: {resp.text[:200]}")
            failed += 1
            return resp
    except Exception as e:
        print(f"  FAIL {name}: {e}")
        failed += 1
        return None

def test_contains(name, text, **kwargs):
    global passed, failed
    resp = test(name, 200, **kwargs)
    if resp and text in resp.text:
        print(f"    -> content check PASS ('{text}' found)")
        passed += 1
    elif resp:
        print(f"    -> content check FAIL ('{text}' not found)")
        failed += 1
    return resp

print("=== File Manager E2E Tests ===\n")

# 1. 401
test("1. Unauthorized", 401, auth=None)

# 2. 200
test("2. Root page", 200)

# 3. Create folder
test_contains("3. Create folder", "TestFolder",
    method="post", path="/mkdir", data={"name": "TestFolder"})

# 4. Upload file
test_contains("4. Upload file", "test",
    method="post", path="/upload", files={"file": ("test.txt", b"hello world\n")})

# 5. Download
test("5. Download file", 200, path="/download/2")

# 6. Rename
test_contains("6. Rename file", "renamed",
    method="patch", path="/rename/2", data={"new_name": "renamed.txt"})

# 7. Delete
test("7. Delete file", 200, method="delete", path="/delete/2")

# 8. 404
test("8. Not found", 404, path="/browse/99999")

# 9. 409
test("9. Duplicate folder", 409,
    method="post", path="/mkdir", data={"name": "TestFolder"})

print(f"\n=== Results: {passed} passed, {failed} failed ===")
sys.exit(0 if failed == 0 else 1)
