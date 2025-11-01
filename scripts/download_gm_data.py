"""Download GM/Executive data from Pro Football Reference.

This script downloads executive data CSVs from PFR for all NFL teams.
Uses Selenium with headless Chrome to bypass Cloudflare blocking.

Usage:
    python download_gm_data.py
"""
import sys
import time
import random
from pathlib import Path
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from gridiron_yampylytics.manifest import update_gm_data

# Team abbreviations used by PFR
PFR_TEAMS = [
    'crd',  # Arizona Cardinals
    'atl',  # Atlanta Falcons
    'rav',  # Baltimore Ravens
    'buf',  # Buffalo Bills
    'car',  # Carolina Panthers
    'chi',  # Chicago Bears
    'cin',  # Cincinnati Bengals
    'cle',  # Cleveland Browns
    'dal',  # Dallas Cowboys
    'den',  # Denver Broncos
    'det',  # Detroit Lions
    'gnb',  # Green Bay Packers
    'htx',  # Houston Texans
    'clt',  # Indianapolis Colts
    'jax',  # Jacksonville Jaguars
    'kan',  # Kansas City Chiefs
    'sdg',  # Los Angeles Chargers
    'ram',  # Los Angeles Rams
    'rai',  # Las Vegas Raiders
    'mia',  # Miami Dolphins
    'min',  # Minnesota Vikings
    'nwe',  # New England Patriots
    'nor',  # New Orleans Saints
    'nyg',  # New York Giants
    'nyj',  # New York Jets
    'phi',  # Philadelphia Eagles
    'pit',  # Pittsburgh Steelers
    'sfo',  # San Francisco 49ers
    'sea',  # Seattle Seahawks
    'tam',  # Tampa Bay Buccaneers
    'oti',  # Tennessee Titans
    'was',  # Washington Commanders
]

def download_team_executives(team_code: str, output_dir: Path, driver: webdriver.Chrome) -> bool:
    """Download executive data for a single team using Selenium.

    :param team_code: PFR team code (e.g., 'nwe', 'dal')
    :param output_dir: Directory to save CSV files
    :param driver: Selenium Chrome WebDriver instance
    :return: True if successful, False otherwise
    """
    url = f"https://www.pro-football-reference.com/teams/{team_code}/executives.htm"

    try:
        print(f"  Fetching {team_code}... ", end='', flush=True)

        driver.get(url)

        # Sleep AFTER successful request (3.5-5.5s randomized)
        sleeptime = random.uniform(3.5, 5.5)
        time.sleep(sleeptime)

        # Get the page source and parse with pandas
        page_html = driver.page_source
        tables = pd.read_html(page_html)

        if not tables:
            print("❌ No tables found")
            return False

        # Usually the first table is the executives table
        executives_df = tables[0]

        # Save to CSV
        output_file = output_dir / f"{team_code}_executives.csv"
        executives_df.to_csv(output_file, index=False)

        print(f"✓ ({len(executives_df)} rows, slept {sleeptime:.2f}s)")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main() -> None:
    """Download GM/executive data for all teams using Selenium."""
    sys.stdout.reconfigure(encoding='utf-8')

    # Set up output directory
    output_dir = Path(__file__).parent.parent / "data" / "raw" / "executives"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("="*80)
    print("DOWNLOADING GM/EXECUTIVE DATA FROM PRO FOOTBALL REFERENCE")
    print("="*80)
    print(f"\nOutput directory: {output_dir}")
    print(f"Teams to download: {len(PFR_TEAMS)}")
    print("\nNote: Using Selenium with headless Chrome (3.5-5.5s sleep)\n")

    # Set up Selenium with headless Chrome
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')

    print("Starting Chrome WebDriver (downloading ChromeDriver if needed)...")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    successful = 0
    failed = 0

    try:
        for i, team_code in enumerate(PFR_TEAMS, 1):
            print(f"[{i:2d}/{len(PFR_TEAMS)}] ", end='')

            if download_team_executives(team_code, output_dir, driver):
                successful += 1
            else:
                failed += 1
    finally:
        print("\nClosing WebDriver...")
        driver.quit()

    print("\n" + "="*80)
    print("DOWNLOAD COMPLETE")
    print("="*80)
    print(f"  ✓ Successful: {successful}")
    print(f"  ❌ Failed: {failed}")
    print(f"  📁 Files saved to: {output_dir}")

    if successful > 0:
        print("\nUpdating manifest...")
        try:
            update_gm_data(num_files=successful)
            print("  ✓ Manifest updated")
        except Exception as e:
            print(f"  ⚠ Warning: Could not update manifest: {e}")

        print("\nNext steps:")
        print("  1. Combine individual team CSVs into single dataset")
        print("  2. Extract GM tenure ranges (start year, end year)")
        print("  3. Standardize team codes to match nflverse format")

if __name__ == "__main__":
    main()
