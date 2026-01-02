"""GM/Executive data scraper from Pro Football Reference.

This module downloads executive data CSVs from PFR for all NFL teams
using Selenium with headless Chrome to bypass Cloudflare blocking.

For programmatic use:
    from gridiron_yampylytics.loaders.gm_data import download_gm_data
    result = download_gm_data()

The scraper:
1. Uses Selenium with headless Chrome (bypasses Cloudflare)
2. Downloads executive data for all 32 NFL teams
3. Adds randomized delays (3.5-5.5s) between requests
4. Saves individual team CSVs to data/raw/executives/
"""
import logging
import time
import random
from pathlib import Path
from typing import Any
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)


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
        logger.info(f"  Fetching {team_code}... ")

        driver.get(url)

        # Sleep AFTER successful request (3.5-5.5s randomized)
        sleeptime = random.uniform(3.5, 5.5)
        time.sleep(sleeptime)

        # Get the page source and parse with pandas
        page_html = driver.page_source
        tables = pd.read_html(page_html)

        if not tables:
            logger.warning("No tables found")
            return False

        # Usually the first table is the executives table
        executives_df = tables[0]

        # Save to CSV
        output_file = output_dir / f"{team_code}_executives.csv"
        executives_df.to_csv(output_file, index=False)

        logger.info(f"✓ ({len(executives_df)} rows, slept {sleeptime:.2f}s)")
        return True

    except Exception as e:
        logger.error(f"Error: {e}")
        return False


def download_gm_data(
    output_dir: Path | None = None,
    teams: list[str] | None = None
) -> dict[str, Any]:
    """Download GM/executive data for NFL teams using Selenium.

    Scrapes executive data from Pro Football Reference for specified teams
    (or all teams by default) using Selenium with headless Chrome.

    :param output_dir: Directory to save CSV files (default: data/raw/executives)
    :param teams: List of PFR team codes to download (default: all 32 teams)
    :return: Summary dict with download statistics
    """
    from gridiron_yampylytics.manifest import update_gm_data

    # Set default values
    if output_dir is None:
        output_dir = Path.cwd() / "data" / "raw" / "executives"
    if teams is None:
        teams = PFR_TEAMS

    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("="*80)
    logger.info("DOWNLOADING GM/EXECUTIVE DATA FROM PRO FOOTBALL REFERENCE")
    logger.info("="*80)
    logger.info(f"\nOutput directory: {output_dir}")
    logger.info(f"Teams to download: {len(teams)}")
    logger.info("\nNote: Using Selenium with headless Chrome (3.5-5.5s sleep)\n")

    # Set up Selenium with headless Chrome
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')

    logger.info("Starting Chrome WebDriver (downloading ChromeDriver if needed)...")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    successful = 0
    failed = 0

    try:
        for i, team_code in enumerate(teams, 1):
            logger.info(f"[{i:2d}/{len(teams)}] ")

            if download_team_executives(team_code, output_dir, driver):
                successful += 1
            else:
                failed += 1
    finally:
        logger.info("\nClosing WebDriver...")
        driver.quit()

    logger.info("\n" + "="*80)
    logger.info("DOWNLOAD COMPLETE")
    logger.info("="*80)
    logger.info(f"  ✓ Successful: {successful}")
    logger.info(f"  ❌ Failed: {failed}")
    logger.info(f"  📁 Files saved to: {output_dir}")

    if successful > 0:
        logger.info("\nUpdating manifest...")
        try:
            update_gm_data(num_files=successful)
            logger.info("  ✓ Manifest updated")
        except Exception as e:
            logger.warning(f"  Warning: Could not update manifest: {e}")

    # Return structured data for programmatic use
    return {
        'successful': successful,
        'failed': failed,
        'total_teams': len(teams),
        'output_dir': output_dir,
    }
