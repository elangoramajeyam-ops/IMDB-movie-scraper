"""
IMDb Movie Rating Scraper
-------------------------
Scrapes the IMDb Top 250 movies (rank, title, year, rating) using
Selenium + Chrome WebDriver and saves the result to a CSV file.

Install requirements first:
    pip install selenium pandas webdriver-manager

Run:
    python imdb_scraper.py
"""

import json
import time

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

URL = "https://www.imdb.com/chart/top/"
OUTPUT_FILE = "imdb_top_250.csv"
HEADLESS = False  # IMDb often blocks headless Chrome. Set True only if this works for you.


def create_driver(headless: bool = False) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=en-US")
    # Reduce the "automated browser" fingerprint
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def scroll_to_bottom(driver, pause: float = 1.0) -> None:
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height


def parse_next_data(driver) -> list[dict]:
    """Method 1: read the JSON IMDb embeds in the page (most reliable)."""
    raw = driver.find_element(By.ID, "__NEXT_DATA__").get_attribute("innerHTML")
    data = json.loads(raw)
    edges = data["props"]["pageProps"]["pageData"]["chartTitles"]["edges"]

    movies = []
    for i, edge in enumerate(edges, start=1):
        node = edge["node"]
        movies.append(
            {
                "Rank": i,
                "Title": node["titleText"]["text"],
                "Year": (node.get("releaseYear") or {}).get("year", ""),
                "IMDb Rating": (node.get("ratingsSummary") or {}).get("aggregateRating", ""),
            }
        )
    return movies


def parse_dom(driver) -> list[dict]:
    """Method 2 (fallback): read the visible HTML list."""
    scroll_to_bottom(driver)
    items = driver.find_elements(By.CSS_SELECTOR, "li.ipc-metadata-list-summary-item")
    movies = []
    for item in items:
        try:
            raw_title = item.find_element(By.CSS_SELECTOR, "h3.ipc-title__text").text
            rank, _, title = raw_title.partition(". ")
            meta = item.find_elements(By.CSS_SELECTOR, "span.cli-title-metadata-item")
            year = meta[0].text if meta else ""
            rating = item.find_element(By.CSS_SELECTOR, "span.ipc-rating-star--imdb").text.split()[0]
            movies.append(
                {"Rank": int(rank), "Title": title.strip(), "Year": year, "IMDb Rating": float(rating)}
            )
        except Exception as e:
            print(f"Skipping an item: {e}")
    return movies


def scrape_top_movies(driver) -> list[dict]:
    driver.get(URL)

    try:
        WebDriverWait(driver, 90).until(  # long wait so you can solve a human check if shown
            lambda d: d.find_elements(By.ID, "__NEXT_DATA__")
            or d.find_elements(By.CSS_SELECTOR, "li.ipc-metadata-list-summary-item")
        )
    except TimeoutException:
        # Save what the browser actually saw, to help debugging
        driver.save_screenshot("debug_screenshot.png")
        with open("debug_page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print("Page did not load as expected. Saved debug_screenshot.png and debug_page.html")
        print("Page title:", driver.title)
        return []

    try:
        movies = parse_next_data(driver)
        if movies:
            return movies
    except Exception as e:
        print(f"Embedded-JSON method failed ({e}); trying HTML method...")

    return parse_dom(driver)


def main() -> None:
    try:
        driver = create_driver(HEADLESS)
    except Exception as e:
        print("\nCould not start Chrome.")
        print("Error type:", type(e).__name__)
        print("Message:", str(e).split("Stacktrace:")[0].strip()[:500])
        return

    try:
        movies = scrape_top_movies(driver)
    except Exception as e:
        print("\nScraping failed.")
        print("Error type:", type(e).__name__)
        print("Message:", str(e).split("Stacktrace:")[0].strip()[:500])
        try:
            driver.save_screenshot("debug_screenshot.png")
            print("Saved debug_screenshot.png | page title:", driver.title)
        except Exception:
            pass
        movies = []
    finally:
        # Keep the browser open so you can look at the page
        input("\nBrowser is still open. Press Enter here to close it... ")
        driver.quit()

    if not movies:
        print("No movies scraped.")
        return

    df = pd.DataFrame(movies)
    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
    print(f"Scraped {len(df)} movies -> saved to {OUTPUT_FILE}")
    print(df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
