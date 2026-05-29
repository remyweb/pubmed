#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx",
#   "aioftp",
#   "beautifulsoup4",
# ]
# ///

import asyncio
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import aioftp
import httpx
from bs4 import BeautifulSoup

OA_API   = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
FTP_HOST = "ftp.ncbi.nlm.nih.gov"
OUTPUT_DIR = Path("pdf")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

async def get_ftp_path(client: httpx.AsyncClient, pmcid: str) -> str | None:
    resp = await client.get(OA_API, params={"id": pmcid, "format": "pdf"})
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    if root.find(".//error") is not None:
        return None
    for link in root.iter("link"):
        if link.get("format") == "pdf":
            path = urlparse(link.get("href", "")).path
            return path.replace("/pub/pmc/oa_pdf/", "/pub/pmc/deprecated/oa_pdf/")
    return None

async def get_filename_from_wayback(client: httpx.AsyncClient, pmcid: str) -> str | None:
    """Récupère le nom du fichier PDF depuis citation_pdf_url via Wayback."""
    pmc_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
    archive_url = f"https://web.archive.org/web/2if_/{pmc_url}"

    print(f"  Fetching Wayback snapshot for {pmcid}...")
    try:
        resp = await client.get(archive_url, follow_redirects=True, timeout=30)
        if resp.status_code != 200:
            return None
    except Exception as e:
        print(f"  Wayback error: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    meta = soup.find("meta", attrs={"name": "citation_pdf_url"})
    if not meta:
        return None

    content = meta.get("content", "")
    # Extrait le nom du fichier : https://.../pdf/1607.pdf -> 1607.pdf
    filename = content.rstrip("/").split("/")[-1]
    return filename if filename.endswith(".pdf") else None


async def download_via_europepmc(client: httpx.AsyncClient, pmcid: str, filename: str, dest: Path) -> bool:
    """Télécharge via l'API Europe PMC fulltextRepo."""
    url = "https://europepmc.org/api/fulltextRepo"
    params = {
        "pmcId": pmcid,
        "type": "FILE",
        "fileName": filename,
        "mimeType": "application/pdf",
        "version": "1",
        "pmc_pageType": "pdf",
        "pmc_domain": "jco",
    }
    print(f"  Europe PMC: {url}?pmcId={pmcid}&fileName={filename}")
    try:
        resp = await client.get(url, params=params, timeout=30)
        resp.raise_for_status()
        if not resp.content.startswith(b"%PDF"):
            print(f"  Not a PDF — Content-Type: {resp.headers.get('content-type')}")
            return False
        dest.write_bytes(resp.content)
        return True
    except Exception as e:
        print(f"  Europe PMC error: {e}")
        return False


async def download_via_ftp(ftp_path: str, dest: Path) -> bool:
    async with aioftp.Client.context(FTP_HOST, 21) as ftp:
        await ftp.login()
        async with ftp.download_stream(ftp_path) as stream:
            data = b""
            async for block in stream.iter_by_block():
                data += block
    if not data.startswith(b"%PDF"):
        return False
    dest.write_bytes(data)
    return True


async def download(pmcid: str) -> None:
    pmcid = pmcid.upper()
    if not pmcid.startswith("PMC"):
        pmcid = f"PMC{pmcid}"

    OUTPUT_DIR.mkdir(exist_ok=True)
    dest = OUTPUT_DIR / f"{pmcid}.pdf"

    if dest.exists():
        print(f"Already downloaded: {dest}")
        return

    async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:

        # 1. NCBI OA FTP
        print(f"[1/2] Trying NCBI OA FTP...")
        ftp_path = await get_ftp_path(client, pmcid)
        if ftp_path:
            print(f"  FTP: {ftp_path}")
            if await download_via_ftp(ftp_path, dest):
                print(f"[OK] {dest} ({dest.stat().st_size // 1024} KB)")
                return

        # 2. Wayback -> filename -> Europe PMC fulltextRepo
        print(f"[2/2] Trying Wayback + Europe PMC fallback...")
        filename = await get_filename_from_wayback(client, pmcid)
        if not filename:
            print(f"[FAIL] Could not find PDF filename for {pmcid}")
            sys.exit(1)

        print(f"  Filename: {filename}")
        if await download_via_europepmc(client, pmcid, filename, dest):
            print(f"[OK] {dest} ({dest.stat().st_size // 1024} KB)")
        else:
            print(f"[FAIL] Could not download PDF for {pmcid}")
            sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run main.py <PMCID>")
        print("Example: uv run main.py PMC3549297")
        sys.exit(1)
    asyncio.run(download(sys.argv[1]))


if __name__ == "__main__":
    main()