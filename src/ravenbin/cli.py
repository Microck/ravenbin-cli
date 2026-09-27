#!/usr/bin/env python3
"""Upload to or fetch a file from Raven Bin."""

import argparse
import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from . import __version__

URL = "https://ravenbin.com/"


def browser_options() -> dict[str, Any]:
    options = {"headless": True}
    executable = os.environ.get("RAVENBIN_CHROMIUM_PATH")
    if executable:
        options["executable_path"] = executable
    if os.geteuid() == 0:
        options["args"] = ["--no-sandbox"]
    return options


def add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--timeout",
        type=float,
        default=300,
        help="Operation timeout in seconds (default: 300).",
    )


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ravenbin",
        description="Upload and download encrypted files with Raven Bin.",
    )
    parser.add_argument(
        "--version", action="version", version=f"ravenbin {__version__}"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    upload_parser = commands.add_parser("upload", help="Encrypt and upload a file.")
    upload_parser.add_argument("file", type=Path)
    upload_parser.add_argument(
        "--expiry",
        choices=("5m", "15m", "1h", "2h", "4h", "12h"),
        default="12h",
        help="How long Raven Bin keeps the upload (default: 12h).",
    )
    add_common_options(upload_parser)

    fetch_parser = commands.add_parser(
        "fetch", aliases=["download"], help="Fetch and decrypt a share URL."
    )
    fetch_parser.add_argument(
        "url", help="Complete Raven Bin URL, including the # key."
    )
    fetch_parser.add_argument(
        "--output", type=Path, help="Output path (default: stored filename)."
    )
    fetch_parser.add_argument(
        "--force", action="store_true", help="Overwrite an existing output file."
    )
    add_common_options(fetch_parser)
    return parser.parse_args(argv)


async def upload(file_path: Path, expiry: str, timeout: float) -> str:
    expiry_seconds = {
        "5m": "300",
        "15m": "900",
        "1h": "3600",
        "2h": "7200",
        "4h": "14400",
        "12h": "43200",
    }
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**browser_options())
        page = await browser.new_page()
        page.set_default_timeout(timeout * 1000)
        try:
            await page.goto(URL, wait_until="domcontentloaded")
            # Some Chromium sandbox variants cannot expose /tmp to pages.
            # Stage the source under home so uploads work consistently.
            with tempfile.TemporaryDirectory(
                prefix="ravenbin-upload-", dir=Path.home()
            ) as staging_dir:
                staged_path = Path(staging_dir) / file_path.name
                shutil.copyfile(file_path, staged_path)
                await page.set_input_files("#file", str(staged_path))
                await page.select_option("#expiry", expiry_seconds[expiry])
                await page.click("#create")
                await page.wait_for_function(
                    "() => document.querySelector('#link')?.value?.includes('#')",
                    timeout=timeout * 1000,
                )
                link = await page.input_value("#link")
            if not link.startswith(URL) or "#" not in link:
                raise RuntimeError("Raven returned an unexpected share URL")
            return link
        except PlaywrightTimeoutError as error:
            message = await page.locator("#err").text_content()
            detail = (message or "upload timed out").strip()
            raise RuntimeError(detail) from error
        finally:
            await browser.close()


def validate_fetch_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "ravenbin.com":
        raise ValueError("URL must be a complete https://ravenbin.com/ share URL")
    if not parsed.query or not parsed.fragment:
        raise ValueError(
            "URL must include both the bin id and the decryption key after #"
        )


async def fetch_bin(
    url: str, output: Optional[Path], force: bool, timeout: float
) -> Path:
    validate_fetch_url(url)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**browser_options())
        page = await browser.new_page(accept_downloads=True)
        page.set_default_timeout(timeout * 1000)
        # Native save dialogs cannot be accepted headlessly. Use Raven's OPFS path.
        await page.add_init_script("window.showSaveFilePicker = undefined;")
        downloaded = asyncio.get_running_loop().create_future()
        page.on(
            "download",
            lambda item: downloaded.set_result(item) if not downloaded.done() else None,
        )
        ready = None
        try:
            await page.goto(url, wait_until="domcontentloaded")
            ready = asyncio.create_task(
                page.wait_for_function(
                    """() => {
                    const download = document.querySelector('#download[href]');
                    const text = document.querySelector('#output');
                    const error = document.querySelector('#read-err:not(.hidden)');
                    return download || (text && text.value) || error;
                }""",
                    timeout=timeout * 1000,
                )
            )
            done, _ = await asyncio.wait(
                [ready, downloaded],
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                raise RuntimeError("fetch timed out")
            if ready in done:
                await ready
                error = await page.locator("#read-err").text_content()
                if error and await page.locator("#read-err").is_visible():
                    raise RuntimeError(error.strip())
                if await page.locator("#download[href]").count():
                    await page.locator("#download").click()
                    await asyncio.wait_for(asyncio.shield(downloaded), timeout)
            if downloaded.done():
                download = downloaded.result()
                destination = output or Path(download.suggested_filename).name
            else:
                destination = output or Path("download.txt")
            destination = Path(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Keep a failed transfer away from the final path. A hard link also
            # refuses to replace an existing file when --force is absent.
            with tempfile.TemporaryDirectory(
                prefix="ravenbin-download-", dir=destination.parent
            ) as staging_dir:
                staged_path = Path(staging_dir) / "download"
                if downloaded.done():
                    await asyncio.wait_for(download.save_as(staged_path), timeout)
                else:
                    staged_path.write_text(await page.locator("#output").input_value())
                try:
                    if force:
                        staged_path.replace(destination)
                    else:
                        os.link(staged_path, destination)
                except FileExistsError as error:
                    raise FileExistsError(
                        f"output exists: {destination}; use --force to overwrite"
                    ) from error
            return destination
        except PlaywrightTimeoutError as error:
            message = await page.locator("#read-err").text_content()
            detail = (message or "fetch timed out").strip()
            raise RuntimeError(detail) from error
        finally:
            if ready and not ready.done():
                ready.cancel()
                await asyncio.gather(ready, return_exceptions=True)
            await browser.close()


def main() -> int:
    args = parse_args()
    try:
        if args.command in ("fetch", "download"):
            path = asyncio.run(
                fetch_bin(args.url, args.output, args.force, args.timeout)
            )
            print(path)
            return 0
        if not args.file.is_file():
            print(f"error: file does not exist: {args.file}", file=sys.stderr)
            return 2
        print(asyncio.run(upload(args.file.resolve(), args.expiry, args.timeout)))
        return 0
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
