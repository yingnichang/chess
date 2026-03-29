from playwright.sync_api import sync_playwright
import pandas as pd
import time

PLAYER_URL = "https://ratings.uschess.org/player/32172683"

def scrape_uschess_tournament_history():
    rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(PLAYER_URL, wait_until="networkidle")

        # Adjust selector after inspecting the page
        # Try clicking the Tournament History tab/button
        possible_tab_texts = ["Tournament History", "Tnmt. Hst", "Tournaments"]
        clicked = False
        for txt in possible_tab_texts:
            try:
                page.get_by_text(txt, exact=False).click(timeout=2000)
                clicked = True
                break
            except:
                pass

        if not clicked:
            print("Could not find Tournament History tab. Inspect selectors manually.")
            browser.close()
            return pd.DataFrame()

        time.sleep(2)

        # Update selectors after inspection
        while True:
            table = page.locator("table")
            if table.count() == 0:
                break

            # Grab all rows except header
            trs = table.locator("tr")
            n = trs.count()

            for i in range(1, n):
                cells = trs.nth(i).locator("th, td")
                vals = [cells.nth(j).inner_text().strip() for j in range(cells.count())]
                if vals:
                    rows.append(vals)

            # Try pagination
            next_found = False
            for label in ["Next", ">", "›"]:
                try:
                    btn = page.get_by_role("button", name=label)
                    if btn.is_enabled():
                        btn.click()
                        page.wait_for_load_state("networkidle")
                        time.sleep(1)
                        next_found = True
                        break
                except:
                    pass

            if not next_found:
                break

        browser.close()

    df = pd.DataFrame(rows)
    return df

if __name__ == "__main__":
    df = scrape_uschess_tournament_history()
    print(df.head())
    df.to_csv("uschess_player_32172683_tournament_history.csv", index=False)