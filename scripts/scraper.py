HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) "
        "Gecko/20100101 Firefox/124.0"
    )
}

import sys
import requests

def download_webpage(url, output_file):
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        with open(output_file, 'w', encoding=response.encoding or 'utf-8') as f:
            f.write(response.text)
        print(f"Webpage downloaded and saved to {output_file}")
    except requests.RequestException as e:
        print(f"Error downloading webpage: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python scraper.py <url> <output_file>")
        sys.exit(1)
    url = sys.argv[1]
    output_file = sys.argv[2]
    download_webpage(url, output_file)
