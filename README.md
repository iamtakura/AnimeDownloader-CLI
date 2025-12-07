# AnimePahe CLI Downloader (MVP)

A CLI-based MVP that searches AnimePahe, lets you pick episodes, resolves obfuscated streaming links with headless Brave (via Selenium), and downloads them using `yt-dlp`.

## Features
- Search AnimePahe via their public API.
- Browse releases and select episodes by range (e.g., `1-3,5`).
- Headless Selenium to extract the `kwik` iframe stream URL.
- Downloads with `yt-dlp` into `~/Videos/AnimePahe Downloads/<Anime Title>/`.
- Auto-detects Brave browser on Windows, macOS, and Linux; falls back to manual path entry.

## Requirements
- Python 3.9+ recommended
- Brave Browser installed
- `ffmpeg` available in your `PATH` (for `yt-dlp` best results)

## Installation
1. Clone the repo and enter it:
   ```bash
   git clone https://github.com/iamtakura/AnimeDownloader-CLI.git
   cd AnimeDownloader-CLI
   ```

2. (Optional but recommended) create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   If you don’t have a `requirements.txt`, install directly:
   ```bash
   pip install requests selenium beautifulsoup4 yt-dlp webdriver-manager
   ```

## Usage
1. Run the downloader:
   ```bash
   python downloader.py
   ```

2. Enter a search term when prompted. Pick an anime by its index.

3. Enter episode selection using ranges and/or comma-separated numbers, e.g.:
   - `1-3,5` (episodes 1, 2, 3, and 5)
   - `7-9` (episodes 7, 8, 9)

4. The script will:
   - Fetch episode data,
   - Open the watch page headlessly in Brave,
   - Extract the `kwik` iframe link and resolve the direct stream URL,
   - Download with `yt-dlp` to `~/Videos/AnimePahe Downloads/<Anime Title>/`.

## Brave Browser Notes
- The script auto-detects Brave in common install locations:
  - **Windows:**  
    `C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe`  
    `C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe`
  - **macOS:**  
    `/Applications/Brave Browser.app/Contents/MacOS/Brave Browser`  
    `/Applications/Brave Browser Beta.app/Contents/MacOS/Brave Browser Beta`
  - **Linux:**  
    `/usr/bin/brave-browser`, `/usr/bin/brave-browser-beta`, `/usr/bin/brave`, `/snap/bin/brave`
- If auto-detection fails, you will be prompted to enter the Brave executable path manually.
- Selenium uses `webdriver_manager` to download the matching ChromeDriver and sets `binary_location` to Brave; headless mode uses `--headless=new`.

## Troubleshooting
- **Brave not found:** Provide the path manually when prompted.
- **Driver errors:** Delete any cached driver and rerun; `webdriver_manager` will fetch a fresh one.
- **Download fails:** Ensure network connectivity and that `ffmpeg` is installed and on `PATH`.
- **Selector timeouts:** AnimePahe or kwik may have changed markup; adjust the iframe selector or wait times in `downloader.py`.

## Output Location
Downloads are saved to:
```
~/Videos/AnimePahe Downloads/<Anime Title>/<episode>.%(ext)s
```

## License
MVP example for personal use. Review and comply with the terms of the content you access.
