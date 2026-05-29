# pubmed fetcher

Download open access PDFs from PubMed Central — no scraping, no captcha, no API key.

## How it works

1. Queries the [NCBI OA API](https://www.ncbi.nlm.nih.gov/pmc/tools/oa-service/) with the given PMCID
2. Retrieves the FTP path of the PDF
3. Downloads it anonymously from `ftp.ncbi.nlm.nih.gov`

> Only works for **open access** articles.

## Requirements

- [uv](https://docs.astral.sh/uv/)

## Usage

```bash
uv run main.py <PMCID>
```

### Example

```bash
uv run main.py PMC7265004
```
