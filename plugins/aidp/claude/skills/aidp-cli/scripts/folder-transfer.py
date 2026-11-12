#!/usr/bin/env python3
# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
"""Transfer workspace/volume folder archives without exposing PAR URLs."""
from __future__ import annotations

import argparse
import errno
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit


class TransferError(Exception):
    pass


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("upload", "download"))
    p.add_argument("--aidpOCID", required=True)
    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument("--workspaceKey")
    target.add_argument("--volumeKey")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--sourcePath", help="Remote download folder; legacy archive upload alias")
    source.add_argument("--sourceFolderPath", help="Local folder to ZIP and upload/extract")
    source.add_argument("--sourceZipPath", help="Existing .zip archive (.aidp also supported for workspace)")
    p.add_argument("--destPath", required=True)
    p.add_argument("--aidp", default="aidp", help="AIDP CLI executable path")
    p.add_argument("--profile", default="DEFAULT")
    p.add_argument("--auth", default="security_token")
    route = p.add_mutually_exclusive_group(required=True)
    route.add_argument("--endpoint")
    route.add_argument("--region")
    p.add_argument("--config-file")
    p.add_argument("--overwrite", action="store_true", help="Replace existing remote files during upload extraction")
    p.add_argument("--waitTimeout", type=float, default=1800)
    p.add_argument("--pollInterval", type=float, default=5)
    p.add_argument("--requestTimeout", type=float, default=120)
    return p


def safe_detail(value):
    text = str(value or "").replace("\\/", "/")
    # Redact escaped/percent-encoded URLs as well as bare PAR path fragments.
    for _ in range(2):
        text = unquote(text)
    text = re.sub(r"https?://[^\s<>\"']+", "[URL redacted]", text, flags=re.I)
    text = re.sub(r"/p/[^\s<>\"']+", "[PAR redacted]", text, flags=re.I)
    return " ".join(text.split())[:500]


def api_error(response, status):
    parts = [f"AIDP request failed (HTTP {status})"]
    for label, field in [("code", "code"), ("message", "message"), ("request-id", "opc-request-id")]:
        value = safe_detail(response.get(field))
        if value:
            parts.append(f"{label}: {value}")
    return "; ".join(parts)


def api(args, command, body=None):
    cmd = [args.aidp, "--auth", args.auth, "--profile", args.profile,
           "--instance-id", args.aidpOCID, "--timeout", str(args.requestTimeout)]
    cmd += ["--endpoint", args.endpoint] if args.endpoint else ["--region", args.region]
    if args.config_file:
        cmd += ["--config-file", args.config_file]
    cmd += command
    if body is not None:
        cmd += ["--body", json.dumps(body)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=args.requestTimeout)
    except FileNotFoundError:
        raise TransferError("AIDP executable not found; pass --aidp with the prerequisite aidp_path.") from None
    except subprocess.TimeoutExpired:
        raise TransferError("AIDP request timed out; inspect operation state before repeating a mutation.") from None
    # CLI output includes a Response: prefix. Never emit raw output or stderr.
    try:
        text = result.stdout if "{" in result.stdout else result.stderr
        response, _ = json.JSONDecoder().raw_decode(text[text.index("{"):])
        status = int(response.get("status", 0))
    except (ValueError, TypeError, AttributeError):
        raise TransferError("AIDP CLI returned an unreadable response; raw output suppressed.") from None
    if result.returncode or not 200 <= status < 300:
        raise TransferError(api_error(response, status))
    data = response.get("data")
    if not isinstance(data, dict):
        raise TransferError("AIDP response is missing transfer metadata.")
    return data


def operation_key(data):
    key = data.get("operationKey")
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", key):
        raise TransferError("AIDP response is missing a valid operationKey.")
    print(f"Operation: {key}", flush=True)
    return key


def wait(args, key):
    deadline = time.monotonic() + args.waitTimeout
    last = None
    while time.monotonic() < deadline:
        status = api(args, ["async-operations", "get", key]).get("status")
        if status == "SUCCEEDED":
            print("Status: SUCCEEDED", flush=True)
            return
        if status in {"FAILED", "CANCELED", "CANCELLED", "ABORTED"}:
            raise TransferError("Async operation failed or was canceled; inspect its operation key.")
        if status != last:
            print("Status: waiting for completion", flush=True)
            last = status
        time.sleep(min(args.pollInterval, max(0, deadline - time.monotonic())))
    raise TransferError("Completion wait timed out; the remote operation may still be running. Do not repeat creation automatically.")


def tls_context():
    context = ssl.create_default_context()
    try:
        import certifi
    except ImportError:
        pass
    else:
        context.load_verify_locations(cafile=certifi.where())
    return context


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise TransferError("PAR redirect refused; obtain a fresh transfer URL.")


def par_request(url, method, timeout, data=None, headers=None):
    if not isinstance(url, str):
        raise TransferError("Transfer URL is missing.")
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise TransferError("Transfer URL must be HTTPS without embedded user credentials.")
    # ProxyHandler honors HTTPS_PROXY and NO_PROXY, including HTTPS CONNECT tunneling.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(),
                                        urllib.request.HTTPSHandler(context=tls_context()), NoRedirect())
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        return opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        exc.close()
        raise TransferError(f"Archive {method} failed (HTTP {exc.code}).") from None
    except urllib.error.URLError as exc:
        raise TransferError("Archive transfer connection failed: " + safe_detail(exc.reason)) from None


def put_archive(url, source, timeout):
    size = source.stat().st_size
    with source.open("rb") as stream:
        chunks = iter(lambda: stream.read(1024 * 1024), b"")
        with par_request(url, "PUT", timeout, data=chunks,
                         headers={"Content-Length": str(size), "Content-Type": "application/octet-stream"}) as response:
            if not 200 <= response.status < 300:
                raise TransferError(f"Archive upload failed (HTTP {response.status}).")
            etag = response.getheader("ETag")
    if not etag or source.stat().st_size != size:
        raise TransferError("Upload ETag is missing or archive size changed; completion was not submitted.")
    return etag, size


def validate_zip(path):
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise TransferError("ZIP CRC integrity verification failed.")
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
        raise TransferError("ZIP contents could not be validated.") from None


def download_path(source, destination):
    dest = Path(destination).expanduser()
    name = source.rstrip("/").rsplit("/", 1)[-1]
    if name in {"", ".", ".."}:
        name = "folder"
    # A .zip destination specifies the filename stem; otherwise it is a directory.
    stem = dest.stem if dest.suffix.lower() == ".zip" else name
    parent = dest.parent if dest.suffix.lower() == ".zip" else dest
    if not re.search(r"-\d{14}$", stem):
        stem += "-" + datetime.now().strftime("%Y%m%d%H%M%S")
    final = parent / (stem + ".zip")
    if final.exists():
        raise TransferError("Local download file already exists; it will not be overwritten.")
    parent.mkdir(parents=True, exist_ok=True)
    return final


def publish_download(source, destination):
    try:
        os.link(source, destination)
        return
    except FileExistsError:
        raise TransferError("Local download file already exists; it will not be overwritten.") from None
    except OSError as exc:
        unsupported = {errno.EXDEV, errno.EPERM, errno.EACCES, errno.ENOSYS,
                       errno.ENOTSUP, getattr(errno, "EOPNOTSUPP", errno.ENOTSUP)}
        if exc.errno not in unsupported:
            raise TransferError("Could not save the completed ZIP on the destination filesystem.") from None
    # Filesystems such as exFAT have no hard links. Exclusive creation still prevents overwrite.
    try:
        target = destination.open("xb")
    except FileExistsError:
        raise TransferError("Local download file already exists; it will not be overwritten.") from None
    except OSError:
        raise TransferError("Could not create a ZIP file on the destination filesystem.") from None
    try:
        with target, source.open("rb") as stream:
            shutil.copyfileobj(stream, target, length=1024 * 1024)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def get_archive(url, destination, timeout):
    with par_request(url, "GET", timeout) as response:
        if response.status != 200:
            raise TransferError(f"Archive download failed (HTTP {response.status}).")
        with tempfile.TemporaryDirectory(prefix=".aidp-download-", dir=destination.parent) as folder:
            partial = Path(folder) / "archive.zip"
            with partial.open("wb") as stream:
                shutil.copyfileobj(response, stream, length=1024 * 1024)
            length = response.getheader("Content-Length")
            if length is not None and partial.stat().st_size != int(length):
                raise TransferError("Archive download was incomplete.")
            validate_zip(partial)
            publish_download(partial, destination)


@contextmanager
def upload_source(args):
    if args.sourceFolderPath:
        folder = Path(args.sourceFolderPath).expanduser()
        if folder.is_symlink() or not folder.is_dir():
            raise TransferError("sourceFolderPath must be a local directory, not a symlink.")
        folder = folder.resolve()
        if not folder.name:
            raise TransferError("Uploading the filesystem root as a folder is not supported.")
        with tempfile.TemporaryDirectory(prefix="aidp-folder-upload-") as staging:
            staging_path = Path(staging).resolve()
            archive = staging_path / (folder.name + ".zip")
            print("Creating temporary ZIP from folder contents", flush=True)
            def unreadable_folder(error):
                raise TransferError("Cannot read all folder contents; upload was not started.")

            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
                for directory, dirs, files in os.walk(folder, followlinks=False, onerror=unreadable_folder):
                    current = Path(directory)
                    # Avoid including the staging archive when the source contains /tmp.
                    dirs[:] = sorted(d for d in dirs if (current / d).resolve() != staging_path)
                    for name in dirs + sorted(files):
                        path = current / name
                        if path.is_symlink():
                            raise TransferError("Folder contains a symlink; symbolic links are not supported.")
                        relative = path.relative_to(folder).as_posix()
                        if path.is_dir():
                            output.writestr(relative + "/", b"")
                        elif path.is_file():
                            output.write(path, relative)
                        else:
                            raise TransferError("Folder contains an unsupported non-regular file.")
            yield archive
        return
    source = Path(args.sourceZipPath or args.sourcePath).expanduser().resolve()
    allowed = {".zip", ".aidp"} if args.workspaceKey else {".zip"}
    if not source.is_file() or source.suffix.lower() not in allowed or source.stat().st_size <= 0:
        raise TransferError("Source must be a nonempty .zip archive (.aidp also supported for workspace).")
    if source.suffix.lower() == ".zip":
        validate_zip(source)
    yield source


def transfer(args):
    if not args.aidpOCID.strip() or not (args.workspaceKey or args.volumeKey or "").strip():
        raise TransferError("Instance and target keys must be nonempty.")
    source_value = args.sourceFolderPath or args.sourceZipPath or args.sourcePath or ""
    if not source_value.strip() or not args.destPath.strip():
        raise TransferError("Source and destination paths must be nonempty; use . for a remote root.")
    if min(args.requestTimeout, args.waitTimeout, args.pollInterval) <= 0:
        raise TransferError("Timeouts and poll interval must be positive.")
    if args.action == "download" and not args.sourcePath:
        raise TransferError("Download requires --sourcePath for the remote folder.")
    group = "workspace-object" if args.workspaceKey else "volume"
    key = args.workspaceKey or args.volumeKey
    if args.action == "upload":
        with upload_source(args) as source:
            command = "upload-and-extract-workspace-zip" if args.workspaceKey else "upload-and-extract-volume-zip"
            data = api(args, [group, command, key], {"action": "CREATE", "zipFileName": source.name,
                       "destinationFolderPath": args.destPath, "isOverwrite": args.overwrite})
            operation = operation_key(data)
            print("Uploading archive", flush=True)
            etag, size = put_archive(data.get("uploadUrl"), source, args.requestTimeout)
            api(args, [group, command, key], {"action": "UPDATE", "operationKey": operation,
                                            "eTag": etag, "sizeInBytes": size})
            wait(args, operation)
            print(f"Upload and extraction completed: {args.destPath.rstrip(chr(47))}/{source.stem}", flush=True)
    else:
        if args.overwrite:
            raise TransferError("--overwrite applies only to upload extraction.")
        destination = download_path(args.sourcePath, args.destPath)
        command = "zip-and-download-workspace-folder" if args.workspaceKey else "zip-and-download-volume-folder"
        data = api(args, [group, command, key], {"sourceFolderPath": args.sourcePath})
        operation = operation_key(data)
        wait(args, operation)
        print("Downloading ZIP", flush=True)
        get_archive(data.get("downloadUrl"), destination, args.requestTimeout)
        print(f"Downloaded: {destination.resolve()}", flush=True)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        transfer(args)
        return 0
    except TransferError as exc:
        print(f"Error: {exc}", file=sys.stderr)
    except KeyboardInterrupt:
        print("Interrupted; remote work may continue. Inspect the operation key before retrying.", file=sys.stderr)
    except Exception:
        # HTTP/CLI exceptions can contain PAR URLs; do not print exceptions or tracebacks.
        print("Transfer failed; sensitive exception details suppressed. Inspect the operation key before retrying.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
