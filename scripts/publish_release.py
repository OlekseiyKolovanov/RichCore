import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

GITHUB_OWNER = "OlekseiyKolovanov"
GITHUB_REPO = "RichCore"
RELEASE_ASSET = "dist/RichCore_v12.zip"


def get_token() -> str:
    for name in ("RICHCORE_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        token = os.environ.get(name)
        if token:
            return token
    raise SystemExit("Set RICHCORE_GITHUB_TOKEN, GITHUB_TOKEN or GH_TOKEN with repo permissions.")


def request_json(url: str, method: str = "GET", data=None, headers=None) -> dict:
    headers = {**(headers or {}), "User-Agent": "RichCorePublisher/1.0"}
    if data is not None:
        d = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    else:
        d = None
    req = urllib.request.Request(url, data=d, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def delete_asset(url: str, token: str) -> None:
    req = urllib.request.Request(url, headers={"Authorization": f"token {token}", "User-Agent": "RichCorePublisher/1.0"}, method="DELETE")
    with urllib.request.urlopen(req, timeout=30) as response:
        if response.status not in (200, 204):
            raise RuntimeError(f"Failed to delete asset: {response.status}")


def main() -> None:
    tag_name = sys.argv[1] if len(sys.argv) > 1 else None
    token = get_token()
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }

    if not tag_name:
        raise SystemExit("Usage: python scripts/publish_release.py v1.0.8")

    asset_path = Path(RELEASE_ASSET)
    if not asset_path.exists():
        raise SystemExit(f"Missing asset: {asset_path}")

    base_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
    release_url = f"{base_url}/releases/tags/{urllib.parse.quote(tag_name)}"

    release = None
    try:
        release = request_json(release_url, headers=headers)
        print(f"Found release {tag_name}")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print(f"Release {tag_name} not found, creating it")
        else:
            raise

    if release is None:
        create_url = f"{base_url}/releases"
        payload = {
            "tag_name": tag_name,
            "name": f"RichCore {tag_name.lstrip('v')}",
            "body": f"RichCore {tag_name.lstrip('v')} release",
            "draft": False,
            "prerelease": False,
        }
        release = request_json(create_url, method="POST", data=payload, headers=headers)
        print(f"Created release {tag_name}")

    upload_url = release.get("upload_url", "").split("{")[0]
    if not upload_url:
        raise SystemExit("Release upload URL not found.")

    existing_assets = release.get("assets", []) or []
    for asset in existing_assets:
        if asset.get("name") == asset_path.name:
            print(f"Deleting existing asset {asset_path.name}")
            delete_asset(asset.get("url"), token)

    upload_target = f"{upload_url}?name={urllib.parse.quote(asset_path.name)}"
    with asset_path.open("rb") as f:
        data = f.read()
    req = urllib.request.Request(upload_target, data=data, headers={**headers, "Content-Type": "application/octet-stream"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as response:
        result = json.loads(response.read().decode("utf-8"))
        print(f"Uploaded asset: {result.get('name')}")
        print(f"Download URL: {result.get('browser_download_url')}")


if __name__ == "__main__":
    main()
