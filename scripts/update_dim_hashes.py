import subprocess
import os
import requests

# Paths
DIM_ENUMS_TS_URL = "https://raw.githubusercontent.com/DestinyItemManager/DIM/master/src/data/d2/generated-enums.ts"
DIM_ENUMS_TS = os.path.join(os.path.dirname(__file__), "../web_app/backend/generated-enums.ts")
OUTPUT_PY = os.path.join(os.path.dirname(__file__), "../web_app/backend/dim_socket_hashes.py")

def fetch_dim_enums():
    print("Fetching latest generated-enums.ts from DIM GitHub...")
    resp = requests.get(DIM_ENUMS_TS_URL)
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch DIM enums: {resp.status_code}")
    with open(DIM_ENUMS_TS, "w", encoding="utf-8") as f:
        f.write(resp.text)
    print(f"Downloaded to {DIM_ENUMS_TS}")

def convert_to_python_enum():
    print("Converting TypeScript enums to Python using enum-converter...")
    result = subprocess.run([
        "enumc",
        DIM_ENUMS_TS,
        "--to", "python",
        "--out", OUTPUT_PY
    ], capture_output=True, text=True)
    if result.returncode != 0:
        print("Error running enum-converter:")
        print(result.stderr)
        raise RuntimeError("enum-converter failed")
    print(f"Python enums written to {OUTPUT_PY}")

def main():
    fetch_dim_enums()
    convert_to_python_enum()

if __name__ == "__main__":
    main() 