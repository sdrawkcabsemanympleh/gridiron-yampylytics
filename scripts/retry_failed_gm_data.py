"""Retry downloading GM/Executive data for specific teams.

This script re-attempts downloading executive data for teams that failed
in the initial scrape. Uses Selenium with headless Chrome.

Usage:
    python retry_failed_gm_data.py car chi
    python retry_failed_gm_data.py --all  # retry all missing teams
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

# All valid PFR team codes
ALL_TEAMS = [
    'crd', 'atl', 'rav', 'buf', 'car', 'chi', 'cin', 'cle',
    'dal', 'den', 'det', 'gnb', 'htx', 'clt', 'jax', 'kan',
    'sdg', 'ram', 'rai', 'mia', 'min', 'nwe', 'nor', 'nyg',
    'nyj', 'phi', 'pit', 'sfo', 'sea', 'tam', 'oti', 'was'
]

def get_missing_teams(output_dir: Path) -> list[str]:
    """Find teams that don't have executive CSV files yet.

    :param output_dir: Directory where CSV files are stored
    :return: List of team codes that are missing
    """
    existing_files = {f.stem.replace('_executives', '') for f in output_dir.glob('*_executives.csv')}
    return [team for team in ALL_TEAMS if team not in existing_files]

def retry_team(team_code: str, output_dir: Path, driver: webdriver.Chrome) -> bool:
    """Retry downloading executive data for a single team.

    :param team_code: PFR team code (e.g., 'car', 'chi')
    :param output_dir: Directory to save CSV files
    :param driver: Selenium Chrome WebDriver instance
    :return: True if successful, False otherwise
    """
    url = f"https://www.pro-football-reference.com/teams/{team_code}/executives.htm"

    try:
        print(f"  Fetching {team_code}... ", end='', flush=True)

        driver.get(url)

        sleeptime = random.uniform(3.5, 5.5)
        time.sleep(sleeptime)

        page_html = driver.page_source
        tables = pd.read_html(page_html)

        if not tables:
            print("❌ No tables found")
            return False

        executives_df = tables[0]
        output_file = output_dir / f"{team_code}_executives.csv"
        executives_df.to_csv(output_file, index=False)

        print(f"✓ ({len(executives_df)} rows, slept {sleeptime:.2f}s)")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main() -> None:
    """Retry downloading GM/executive data for specified teams."""
    sys.stdout.reconfigure(encoding='utf-8')

    output_dir = Path(__file__).parent.parent / "data" / "raw" / "executives"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine which teams to retry
    if len(sys.argv) > 1:
        if sys.argv[1] == '--all':
            teams_to_retry = get_missing_teams(output_dir)
            if not teams_to_retry:
                print("✓ All teams already downloaded!")
                return
            print(f"Found {len(teams_to_retry)} missing teams: {', '.join(teams_to_retry)}\n")
        else:
            teams_to_retry = sys.argv[1:]
    else:
        print("Usage: python retry_failed_gm_data.py <team_code> [team_code ...]")
        print("   or: python retry_failed_gm_data.py --all")
        print(f"\nValid team codes: {', '.join(ALL_TEAMS)}")
        return

    print("="*80)
    print("RETRYING GM/EXECUTIVE DATA DOWNLOAD")
    print("="*80)
    print(f"\nOutput directory: {output_dir}")
    print(f"Teams to retry: {len(teams_to_retry)}\n")

    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')

    print("Starting Chrome WebDriver...")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    successful = 0
    failed = 0

    try:
        for i, team_code in enumerate(teams_to_retry, 1):
            print(f"[{i:2d}/{len(teams_to_retry)}] ", end='')

            if retry_team(team_code, output_dir, driver):
                successful += 1
            else:
                failed += 1
    finally:
        print("\nClosing WebDriver...")
        driver.quit()

    print("\n" + "="*80)
    print("RETRY COMPLETE")
    print("="*80)
    print(f"  ✓ Successful: {successful}")
    print(f"  ❌ Failed: {failed}")
    print(f"  📁 Files saved to: {output_dir}")

if __name__ == "__main__":
    main()
