import os
import sys
import time

import dataclasses
import typing
import re
import pathlib
import pydantic_settings

from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager


import sys
sys.path.append('../src')
sys.path.append('src')
import mediatools
#import util



@dataclasses.dataclass
class PathComponents:
    name: str
    album_id: str
    video_id: str
    resolution: str

    @classmethod
    def from_filename(cls, filename: str) -> typing.Self:
        filename = str(filename).strip()
        # Regex pattern explanation:
        # ^(?P<name>.+)          : Match anything from start (name)
        # -(?P<album_id>\d{8})   : Match exactly 8 digits preceded by a hyphen
        # -(?P<video_id>\d{2})   : Match exactly 2 digits preceded by a hyphen
        # -(?P<resolution>[^.]+) : Match everything up to the dot (resolution)
        # \.mp4$                 : Match the file extension at the end
        regex_pattern = r"^(?P<name>.+)-(?P<album_id>\d{8})-(?P<video_id>\d{2})-(?P<resolution>[^.]+)\.mp4$"
        match = re.search(regex_pattern, filename)
        if match:
            return cls(**match.groupdict())
        raise ValueError(f"Filename '{filename}' does not match the expected pattern.")

class FirefoxScraper:
    def __init__(self, driver):
        """Private constructor: Use the static factory methods instead."""
        self.driver = driver
        self.wait = WebDriverWait(self.driver, 20)

    @classmethod
    def create_scraper(cls, headless=False):
        """Static Factory Constructor"""
        options = Options()
        if headless:
            options.add_argument("-headless")
            
        driver = webdriver.Firefox(
            service=Service(GeckoDriverManager().install()), 
            options=options
        )
        return cls(driver)

    # --- Context Manager Methods ---
    def __enter__(self):
        """Returns the instance when entering the 'with' block."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensures the driver quits when exiting the 'with' block."""
        print("Closing browser session...")
        self.close()

    # --- Interaction Methods ---
    def navigate_to(self, url):
        print(f"Navigating to: {url}")
        self.driver.get(url)

    def wait_for_manual_login(self):
        input("Please log in manually in the browser, then press Enter here...")

    def wait_for_element(self, selector, by=By.TAG_NAME):
        print(f"Waiting for element: {selector}")
        self.wait.until(EC.presence_of_element_located((by, selector)))

    def scroll_to_bottom(self, pause_time=2):
        print("Scrolling to ensure full page load...")
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        while True:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(pause_time)
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

    def download_html(self, filepath):
        print(f"Saving HTML to {filepath}...")
        full_html = self.driver.page_source
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(full_html)
        print("Successfully saved!")

    def close(self):
        if self.driver:
            self.driver.quit()

class Settings(pydantic_settings.BaseSettings):
    download_dir: str
    site_base_url: str
    files_dir: str
    class Config:
        env_file = ".env_scraper"

# --- Usage Example ---
if __name__ == "__main__":
    app_settings = Settings()

    # Use the static factory to create the instance
    scraper = FirefoxScraper.create_scraper(headless=False)
    mdir = mediatools.scan_directory(app_settings.files_dir)
    vid_parts = [PathComponents.from_filename(vf.path.name) for vf in mdir.all_video_files()]

    print(f"Found {len(vid_parts)} video files to process.")
    with FirefoxScraper.create_scraper(headless=False) as scraper:
        for vp in vid_parts:
            print(f"Video: {vp.name}, Album ID: {vp.album_id}, Video ID: {vp.video_id}, Resolution: {vp.resolution}")

            scraper.navigate_to(app_settings.site_base_url.format(id=int(vp.album_id)))
            #scraper.wait_for_manual_login()
            
            # Ensure a specific element on the dashboard exists before proceeding
            scraper.wait_for_element("body") 
            scraper.scroll_to_bottom()
            
            scraper.download_html("my_downloaded_page.html")
            break
            
