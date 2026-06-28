import time
import threading
import base64
import hashlib
from jwebs import JWebs

try:
    from flask import Flask, request, jsonify
except ImportError:
    print("Please install Flask: pip install flask")
    exit(1)

app = Flask(__name__)

@app.route('/basic-auth/<username>/<password>', methods=['GET'])
def protected(username, password):
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Basic '):
        return jsonify({"error": "No Authorization header"}), 401
    
    encoded = auth_header[6:]
    encoding = request.args.get('encoding', 'base64')
    
    try:
        if encoding == "base64":
            decoded = base64.b64decode(encoded).decode()
            parts = decoded.split(':', 1)
            if len(parts) != 2 or parts[0] != username or parts[1] != password:
                return jsonify({"error": "Invalid credentials"}), 401
            return jsonify({"ok": True}), 200
            
        elif encoding == "base85":
            decoded = base64.b85decode(encoded).decode()
            parts = decoded.split(':', 1)
            if len(parts) != 2 or parts[0] != username or parts[1] != password:
                return jsonify({"error": "Invalid credentials"}), 401
            return jsonify({"ok": True}), 200
            
        elif encoding.startswith("hash-"):
            algo = encoding.split("-", 1)[1]
            try:
                hash_func = getattr(hashlib, algo)
            except AttributeError:
                return jsonify({"error": "Unsupported hash algorithm"}), 401
            
            credential_bytes = f"{username}:{password}".encode('utf-8')
            correct_hash = base64.b64encode(hash_func(credential_bytes).digest()).decode()
            if encoded == correct_hash:
                return jsonify({"ok": True}), 200
            else:
                return jsonify({"error": "Invalid hash", "sent": encoded, "expected": correct_hash}), 401
        else:
            return jsonify({"error": f"Unsupported encoding: {encoding}"}), 401
    except Exception as e:
        return jsonify({"error": f"Decoding failed: {str(e)}"}), 401

@app.route('/health')
def health():
    return "OK", 200

def run_server():
    app.run(host='127.0.0.1', port=9000, debug=False, use_reloader=False)

def test_auth():
    print("Starting server on port 9000...")
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    time.sleep(2)
    
    j = JWebs()
    if j.GET("http://127.0.0.1:9000/health").status != 200:
        print("Server not running")
        return
    
    url = "http://127.0.0.1:9000/basic-auth/user/pass"
    results = []
    
    r = j.GET(url)
    results.append(("No auth", r.status == 401))
    print(f"No auth: {r.status} (expected 401) {'PASS' if r.status == 401 else 'FAIL'}")
    
    r = JWebs(auth=("user", "pass")).GET(url)
    results.append(("Tuple", r.status == 200))
    print(f"Tuple: {r.status} (expected 200) {'PASS' if r.status == 200 else 'FAIL'}")
    
    r = JWebs(auth=("x", "x")).GET(url, auth=("user", "pass"))
    results.append(("Override", r.status == 200))
    print(f"Override: {r.status} (expected 200) {'PASS' if r.status == 200 else 'FAIL'}")
    
    r = j.GET(url, auth={"user": "user", "password": "pass"})
    results.append(("Dict base64", r.status == 200))
    print(f"Dict base64: {r.status} (expected 200) {'PASS' if r.status == 200 else 'FAIL'}")
    
    r = j.GET(url + "?encoding=base85", auth={"user": "user", "password": "pass", "encoding": "base85"})
    results.append(("base85", r.status == 200))
    print(f"base85: {r.status} (expected 200) {'PASS' if r.status == 200 else 'FAIL'}")
    
    r = j.GET(url + "?encoding=hash-sha256", auth={"user": "user", "password": "pass", "encoding": "hash-sha256"})
    results.append(("sha256", r.status == 200))
    print(f"sha256: {r.status} (expected 200) {'PASS' if r.status == 200 else 'FAIL'}")
    
    r = j.GET(url + "?encoding=hash-sha512", auth={"user": "user", "password": "pass", "encoding": "hash-sha512"})
    results.append(("sha512", r.status == 200))
    print(f"sha512: {r.status} (expected 200) {'PASS' if r.status == 200 else 'FAIL'}")
    
    r = JWebs(auth=("user", "pass")).GET(url, auth=False)
    results.append(("auth=False", r.status == 401))
    print(f"auth=False: {r.status} (expected 401) {'PASS' if r.status == 401 else 'FAIL'}")
    
    try:
        j.GET(url, auth={"user": "user", "password": "pass", "encoding": "invalid"})
        print("Invalid encoding: FAIL (should raise ValueError)")
        results.append(("Invalid encoding", False))
    except ValueError:
        print("Invalid encoding: PASS")
        results.append(("Invalid encoding", True))
    
    print("\n" + "-"*56)
    passed = sum(1 for _, p in results if p)
    print(f"Passed: {passed}/{len(results)}")
    if passed == len(results):
        print("All auth tests passed.")
    else:
        print("Some tests failed.")
        print("Note: If hash tests (sha256/sha512) fail, it's because the test server")
        print("calculates hash on the full 'username:password' string, which matches")
        print("what jwebs does. Make sure you're using the corrected server code.")

if __name__ == "__main__":
    test_auth()
