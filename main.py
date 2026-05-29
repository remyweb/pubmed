#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx",
#   "aioftp",
# ]
# ///

import asyncio
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import aioftp
import httpx

OA_API = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
FTP_HOST = "ftp.ncbi.nlm.nih.gov"
OUTPUT_DIR = Path("pdf")


async def get_ftp_path(pmcid: str) -> str | None:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(OA_API, params={"id": pmcid, "format": "pdf"})
        resp.raise_for_status()

    root = ET.fromstring(resp.text)

    if root.find(".//error") is not None:
        return None

    for link in root.iter("link"):
        if link.get("format") == "pdf":
            href = link.get("href", "")
            path = urlparse(href).path
            return path.replace("/pub/pmc/oa_pdf/", "/pub/pmc/deprecated/oa_pdf/")

    return None


async def download(pmcid: str) -> None:
    pmcid = pmcid.upper()
    if not pmcid.startswith("PMC"):
        pmcid = f"PMC{pmcid}"

    print(f"Fetching PDF URL for {pmcid}...")
    ftp_path = await get_ftp_path(pmcid)

    if not ftp_path:
        print(f"Error: {pmcid} is not available as open access.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)
    dest = OUTPUT_DIR / f"{pmcid}.pdf"

    print(f"Downloading: {ftp_path}")
    async with aioftp.Client.context(FTP_HOST, 21) as ftp:
        await ftp.login()
        async with ftp.download_stream(ftp_path) as stream:
            data = b""
            async for block in stream.iter_by_block():
                data += block

    if not data.startswith(b"%PDF"):
        print("Error: downloaded file is not a valid PDF.")
        sys.exit(1)

    dest.write_bytes(data)
    print(f"Saved: {dest} ({len(data) // 1024} KB)")


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run main.py <PMCID>")
        print("Example: uv run main.py PMC7265004")
        sys.exit(1)

    asyncio.run(download(sys.argv[1]))


if __name__ == "__main__":
    main()