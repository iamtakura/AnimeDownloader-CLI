"""
AnimePahe CLI Downloader (MVP)
==============================
Searches AnimePahe, lets you pick episodes, resolves obfuscated streaming links
with headless Brave (via Selenium), and downloads them using yt-dlp. 

Language handling:
- Append "(Dub)" to your search to prefer dubbed versions. 
- Append "(Sub)" to your search to prefer subbed versions.
- If neither is specified, the script downloads whatever is available.

Quality:
- Automatically selects the highest quality available.
"""

import os
import platform
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from yt_dlp import YoutubeDL


ANIMEPAHE_API = "https://animepahe.ru/api"
ANIMEPAHE_BASE = "https://animepahe.ru"
DEFAULT_DOWNLOAD_ROOT = Path.home() / "Videos" / "AnimePahe Downloads"
REQUEST_TIMEOUT = 15
SELENIUM_WAIT = 20


@dataclass
class AnimeResult:
    """Represents a single anime search result."""
    id: int
    title: str
    session: str


@dataclass
class EpisodeInfo:
    """Represents a single episode."""
    episode: int
    session: str
    snapshot: Dict


class PaheDownloader:
    """
    Main downloader class that handles:
    - Brave browser detection and Selenium setup
    - AnimePahe API interactions (search, episode listing)
    - Link extraction from kwik iframe
    - Downloading via yt-dlp with highest quality
    """

    def __init__(self, brave_path: Optional[str] = None, headless: bool = True):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": ANIMEPAHE_BASE,
            }
        )
        self.brave_path = brave_path or self.detect_brave_binary()
        self.headless = headless
        self.driver = None  # Initialized lazily

        # Language preference: "dub", "sub", or None (no preference)
        self.language_preference: Optional[str] = None

    # -------------------- Browser Configuration --------------------

    @staticmethod
    def detect_brave_binary() -> Optional[str]:
        """
        Auto-detect the Brave browser executable on Windows, macOS, and Linux.
        Returns the path if found, otherwise None.
        """
        system = platform.system()
        candidates = []

        if system == "Windows":
            candidates = [
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
            ]
        elif system == "Darwin":  # macOS
            candidates = [
                "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                "/Applications/Brave Browser Beta.app/Contents/MacOS/Brave Browser Beta",
            ]
        else:  # Linux and others
            candidates = [
                "/usr/bin/brave-browser",
                "/usr/bin/brave-browser-beta",
                "/usr/bin/brave",
                "/snap/bin/brave",
            ]

        for path in candidates:
            if Path(path).exists():
                return path
        return None

    def get_driver(self):
        """
        Lazily initialize and return the Selenium WebDriver for Brave.
        Uses webdriver_manager to fetch the matching ChromeDriver. 
        """
        if self.driver:
            return self.driver

        if not self.brave_path or not Path(self.brave_path).exists():
            raise FileNotFoundError(
                "Brave executable not found. Please provide a valid path."
            )

        options = ChromeOptions()
        # Point to Brave instead of Chrome
        options.binary_location = self.brave_path
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])

        if self.headless:
            options.add_argument("--headless=new")

        try:
            service = ChromeService(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
        except WebDriverException as exc:
            raise RuntimeError(
                f"Failed to start Brave (Chromium) driver: {exc}"
            ) from exc

        return self.driver

    # -------------------- Search Query Parsing --------------------

    def parse_search_query(self, raw_query: str) -> Tuple[str, Optional[str]]:
        """
        Parse the user's search query to extract:
        - The actual anime title (without language suffix)
        - The language preference: "dub", "sub", or None

        Examples:
        - "Jujutsu Kaisen (Dub)" -> ("Jujutsu Kaisen", "dub")
        - "Jujutsu Kaisen (Sub)" -> ("Jujutsu Kaisen", "sub")
        - "Jujutsu Kaisen" -> ("Jujutsu Kaisen", None)
        """
        query = raw_query.strip()
        lang_pref = None

        # Check for (Dub) suffix (case-insensitive)
        dub_match = re.search(r"\s*\(dub\)\s*$", query, re.IGNORECASE)
        if dub_match:
            query = query[: dub_match.start()].strip()
            lang_pref = "dub"

        # Check for (Sub) suffix (case-insensitive)
        sub_match = re.search(r"\s*\(sub\)\s*$", query, re.IGNORECASE)
        if sub_match:
            query = query[: sub_match.start()].strip()
            lang_pref = "sub"

        return query, lang_pref

    def filter_results_by_language(
        self, results: List[AnimeResult], lang_pref: Optional[str]
    ) -> List[AnimeResult]:
        """
        Filter search results based on language preference. 
        - If lang_pref is "dub", prioritize titles containing "dub" (case-insensitive). 
        - If lang_pref is "sub", exclude titles containing "dub". 
        - If lang_pref is None, return all results.
        """
        if not lang_pref:
            return results

        filtered = []
        for r in results:
            title_lower = r.title.lower()
            if lang_pref == "dub":
                # Prefer dubbed versions
                if "dub" in title_lower:
                    filtered.append(r)
            elif lang_pref == "sub":
                # Exclude dubbed versions (subbed is usually the default)
                if "dub" not in title_lower:
                    filtered.append(r)

        # If filtering removes everything, return original results
        return filtered if filtered else results

    # -------------------- API Helpers --------------------

    def search(self, query: str) -> List[AnimeResult]:
        """
        Search AnimePahe for anime matching the query.
        Returns a list of AnimeResult objects. 
        """
        params = {"m": "search", "q": query}
        resp = self.session.get(ANIMEPAHE_API, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("data", []):
            results.append(
                AnimeResult(
                    id=int(item["id"]),
                    title=item["title"],
                    session=item["session"],
                )
            )
        return results

    def fetch_all_episodes(self, anime_id: int) -> List[EpisodeInfo]:
        """
        Fetch all episodes for a given anime ID. 
        Handles pagination automatically.
        """
        page = 1
        episodes: List[EpisodeInfo] = []

        while True:
            params = {
                "m": "release",
                "id": anime_id,
                "sort": "asc",
                "page": page,
                "l": 100,
            }
            resp = self.session.get(
                ANIMEPAHE_API, params=params, timeout=REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            payload = resp.json()

            for ep in payload.get("data", []):
                episodes.append(
                    EpisodeInfo(
                        episode=int(ep["episode"]),
                        session=ep["session"],
                        snapshot=ep,
                    )
                )

            last_page = payload.get("last_page", page)
            if page >= last_page:
                break
            page += 1

        return episodes

    # -------------------- Episode Selection Parsing --------------------

    @staticmethod
    def parse_episode_selection(selection: str) -> List[int]:
        """
        Parse episode selection input like "1-3,5,7-9". 
        Returns a sorted unique list of episode numbers. 
        """
        chosen = set()
        parts = [p.strip() for p in selection.split(",") if p.strip()]

        for part in parts:
            if "-" in part:
                bounds = part.split("-", 1)
                if len(bounds) == 2 and bounds[0].isdigit() and bounds[1].isdigit():
                    a, b = int(bounds[0]), int(bounds[1])
                    for num in range(min(a, b), max(a, b) + 1):
                        chosen.add(num)
            else:
                if part.isdigit():
                    chosen.add(int(part))

        return sorted(chosen)

    # -------------------- Link Extraction --------------------

    def build_watch_url(self, anime_session: str, episode_session: str) -> str:
        """Build the watch page URL for a specific episode."""
        return f"{ANIMEPAHE_BASE}/play/{anime_session}/{episode_session}"

    def extract_kwik_link(self, watch_url: str) -> str:
        """
        Load the watch page in Selenium, wait for the kwik iframe, and return its src.
        """
        driver = self.get_driver()
        driver.get(watch_url)

        try:
            iframe = WebDriverWait(driver, SELENIUM_WAIT).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "iframe[src*='kwik']")
                )
            )
        except TimeoutException as exc:
            raise TimeoutException(
                f"Timed out waiting for kwik iframe on {watch_url}"
            ) from exc

        kwik_src = iframe.get_attribute("src")
        if not kwik_src:
            raise RuntimeError("kwik iframe src not found")

        return kwik_src

    def resolve_direct_link(self, kwik_url: str, referer: str) -> str:
        """
        Attempt to resolve the direct media URL from a kwik link.
        This is heuristic and may need updates if kwik changes its layout.
        """
        headers = {
            "Referer": referer,
            "User-Agent": self.session.headers["User-Agent"],
        }
        resp = self.session.get(kwik_url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        # Try to find an explicit download link in the page
        soup = BeautifulSoup(resp.text, "html.parser")
        download_btn = soup.find(id="download") or soup.find("a", {"id": "download"})
        if download_btn and download_btn.get("href"):
            return download_btn["href"]

        # Fallback: return the final URL after redirects
        return resp.url

    # -------------------- Download with Highest Quality --------------------

    def download_video(self, url: str, out_path: Path):
        """
        Download the video using yt-dlp with highest quality.
        Automatically creates output directories if needed.
        """
        out_path.parent.mkdir(parents=True, exist_ok=True)

        ydl_opts = {
            "outtmpl": str(out_path),
            "quiet": False,
            "noplaylist": True,
            # Select best video + best audio, merge if needed
            # Falls back to best single file if merging not possible
            "format": "bestvideo+bestaudio/best",
            # Merge into mp4 container
            "merge_output_format": "mp4",
            # Embed subtitles if available
            "writesubtitles": True,
            "subtitleslangs": ["en", "eng"],
            "subtitlesformat": "srt/best",
            "embedsubtitles": True,
            # Progress hooks for better UX
            "progress_hooks": [self._progress_hook],
        }

        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    @staticmethod
    def _progress_hook(d):
        """Progress hook for yt-dlp to show download status."""
        if d["status"] == "downloading":
            percent = d.get("_percent_str", "N/A")
            speed = d.get("_speed_str", "N/A")
            eta = d.get("_eta_str", "N/A")
            print(f"\r  Downloading: {percent} at {speed}, ETA: {eta}", end="", flush=True)
        elif d["status"] == "finished":
            print("\n  Download complete, processing...")

    # -------------------- High-Level Workflow --------------------

    def run(self):
        """Main CLI workflow."""
        print("\n" + "=" * 60)
        print("  AnimePahe Downloader (Brave + Selenium + yt-dlp)")
        print("=" * 60)
        print("\nTip: Add (Dub) or (Sub) to your search to filter results.")
        print("     Example: 'Jujutsu Kaisen (Dub)' or 'Attack on Titan (Sub)'")
        print("-" * 60)

        # 1) Search
        raw_query = input("\nSearch anime: ").strip()
        if not raw_query:
            print("No query provided. Exiting.")
            return

        # Parse query for language preference
        query, lang_pref = self.parse_search_query(raw_query)
        self.language_preference = lang_pref

        if lang_pref:
            print(f"Language preference: {lang_pref.upper()}")
        print(f"Searching for: {query}...")

        try:
            results = self.search(query)
        except Exception as exc:
            print(f"Search failed: {exc}")
            return

        if not results:
            print("No results found.")
            return

        # Filter results by language preference
        filtered_results = self.filter_results_by_language(results, lang_pref)

        print(f"\nSearch results ({len(filtered_results)} found):")
        print("-" * 40)
        for idx, item in enumerate(filtered_results, 1):
            # Indicate if it's dubbed
            dub_indicator = " [DUB]" if "dub" in item.title.lower() else ""
            print(f"  [{idx}] {item.title}{dub_indicator}")

        sel = input("\nSelect anime by number: ").strip()
        if not sel.isdigit() or int(sel) < 1 or int(sel) > len(filtered_results):
            print("Invalid selection. Exiting.")
            return

        chosen = filtered_results[int(sel) - 1]
        print(f"\nSelected: {chosen.title}")

        # 2) Fetch episodes
        print("Fetching episodes...")
        try:
            eps = self.fetch_all_episodes(chosen.id)
        except Exception as exc:
            print(f"Failed to fetch episodes: {exc}")
            return

        if not eps:
            print("No episodes found.")
            return

        min_ep = min(ep.episode for ep in eps)
        max_ep = max(ep.episode for ep in eps)
        print(f"Episodes available: {min_ep} - {max_ep} (Total: {len(eps)})")

        selection = input('Enter episodes to download (e.g., "1-3,5" or "all"): ').strip()

        if selection.lower() == "all":
            selected_eps = [ep.episode for ep in eps]
        else:
            selected_eps = self.parse_episode_selection(selection)

        if not selected_eps:
            print("No episodes selected. Exiting.")
            return

        print(f"\nWill download {len(selected_eps)} episode(s): {selected_eps}")

        # 3) Download loop
        sanitized_title = re.sub(r'[\\/*?:"<>|]', "_", chosen.title).strip() or "Anime"
        base_dir = DEFAULT_DOWNLOAD_ROOT / sanitized_title

        print(f"Download location: {base_dir}")
        print("-" * 60)

        success_count = 0
        fail_count = 0

        for idx, ep_num in enumerate(selected_eps, 1):
            match = next((e for e in eps if e.episode == ep_num), None)
            if not match:
                print(f"\n[{idx}/{len(selected_eps)}] Episode {ep_num}: NOT FOUND, skipping.")
                fail_count += 1
                continue

            print(f"\n[{idx}/{len(selected_eps)}] Episode {ep_num}: Extracting link...")

            watch_url = self.build_watch_url(chosen.session, match.session)

            try:
                kwik_link = self.extract_kwik_link(watch_url)
                print(f"  Found kwik link, resolving...")
                direct_link = self.resolve_direct_link(kwik_link, referer=watch_url)
            except Exception as exc:
                print(f"  Failed to resolve link: {exc}")
                fail_count += 1
                continue

            outfile = base_dir / f"Episode_{ep_num:03d}.%(ext)s"
            print(f"  Downloading to: {outfile.parent.name}/{outfile.name}")

            try:
                self.download_video(direct_link, outfile)
                success_count += 1
            except Exception as exc:
                print(f"  Download failed: {exc}")
                fail_count += 1
                continue

        # Summary
        print("\n" + "=" * 60)
        print("  DOWNLOAD COMPLETE")
        print("=" * 60)
        print(f"  Successful: {success_count}")
        print(f"  Failed: {fail_count}")
        print(f"  Location: {base_dir}")
        print("=" * 60 + "\n")


def prompt_brave_path() -> Optional[str]:
    """Prompt user for Brave executable path if auto-detection fails."""
    print("\n" + "-" * 60)
    print("Brave browser not detected automatically.")
    print("Common locations:")
    print("  Windows: C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe")
    print("  macOS:   /Applications/Brave Browser.app/Contents/MacOS/Brave Browser")
    print("  Linux:   /usr/bin/brave-browser")
    print("-" * 60)
    custom = input("Enter Brave executable path (or leave blank to abort): ").strip()
    return custom or None


def main():
    """Entry point for the CLI command."""
    downloader = PaheDownloader()

    # Handle Brave path
    if downloader.brave_path is None:
        manual = prompt_brave_path()
        if not manual:
            sys.exit("Brave path not provided. Exiting.")
        downloader.brave_path = manual
    else:
        print(f"Brave detected: {downloader.brave_path}")

    try:
        downloader.run()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting.")
    finally:
        if downloader.driver:
            downloader.driver.quit()


if __name__ == "__main__":
    main()
