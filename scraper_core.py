
import asyncio
import pandas as pd
from playwright.async_api import async_playwright


BANK_NAMES = [
    "HBL",
    "MCB",
    "UBL",
    "Bank Alfalah",
    "Faysal Bank",
    "Askari Bank",
    "JS Bank",
    "SilkBank",
    "Standard Chartered"
]


def clean(t):
    return (t or "").strip()


async def extract_table(page, bank):
    rows = await page.query_selector_all("table tr")
    data = []

    for r in rows[1:]:
        cols = await r.query_selector_all("td")
        if len(cols) < 2:
            continue
        try:
            tenure = clean(await cols[0].inner_text())
            monthly = clean(await cols[1].inner_text())

            tenure = tenure.replace("Months", "").replace("Month", "").strip()
            tenure_col = f"{tenure} Months"

            monthly = (
                monthly
                .replace("Rs.", "").replace("Rs", "")
                .replace(",", "").strip()
            )

            data.append({"Bank": bank, "Tenure": tenure_col, "Monthly": monthly})
        except:
            continue

    return data


async def find_tab_container(page):
    for role in ["tablist", "list"]:
        candidates = page.get_by_role(role)
        count = await candidates.count()
        for i in range(count):
            el = candidates.nth(i)
            text = await el.inner_text()
            hits = sum(1 for b in BANK_NAMES if b in text)
            if hits >= 3:
                return el

    loc = page.locator(f"text={BANK_NAMES[0]}").first
    if await loc.count() == 0:
        return None

    for level in range(1, 8):
        ancestor = loc.locator(f"xpath={'/..'*level}")
        try:
            text = await ancestor.inner_text(timeout=1000)
            hits = sum(1 for b in BANK_NAMES if b in text)
            if hits >= 3:
                return ancestor
        except:
            break

    return None


async def click_bank_tab(page, tab_container, bank_name, log):
    # Tier 1: exact match inside container
    if tab_container is not None:
        try:
            scoped = tab_container.get_by_text(bank_name, exact=True)
            if await scoped.count() > 0:
                el = scoped.first
                await el.scroll_into_view_if_needed()
                await el.click()
                return
        except:
            pass

    # Tier 2: partial match inside container
    if tab_container is not None:
        try:
            scoped = tab_container.locator(f"text={bank_name}")
            if await scoped.count() > 0:
                el = scoped.first
                actual = (await el.inner_text()).strip().replace("\n", " ")
                log(f"  ⚠ Partial match for '{bank_name}' → '{actual[:50]}'")
                await el.scroll_into_view_if_needed()
                await el.click()
                return
        except:
            pass

    # Tier 3: partial match across whole page
    loc = page.locator(f"text={bank_name}")
    count = await loc.count()
    log(f"  ⚠ Page-wide fallback: {count} matches for '{bank_name}'")
    if count > 0:
        await loc.first.scroll_into_view_if_needed()
        await loc.first.click()


async def scrape(url: str, log=print) -> pd.DataFrame | None:
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()

        log(f"🌐 Loading page...")
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        await page.mouse.wheel(0, 2500)
        await page.wait_for_timeout(1500)

        # Find installment section
        heading = page.locator("text=Installment Plans").first
        if await heading.count() == 0:
            log("❌ Installment section not found on this page.")
            await browser.close()
            return None
        log("✅ Installment section found")

        # Open accordion
        try:
            parent = heading.locator("xpath=ancestor::*[2]")
            accordion_btn = parent.locator("xpath=following::*[name()='svg'][1]")
            if await accordion_btn.count() > 0:
                await accordion_btn.first.click()
                await page.wait_for_timeout(1000)
        except:
            pass

        # Find tab container
        tab_container = await find_tab_container(page)
        if tab_container:
            log("✅ Tab strip located")
        else:
            log("⚠ Tab strip not found — using page-wide search")

        # Detect banks
        log("🔍 Detecting banks...")
        banks_found = []
        for bank in BANK_NAMES:
            loc = page.locator(f"text={bank}")
            if await loc.count() > 0:
                banks_found.append(bank)

        if not banks_found:
            log("❌ No banks detected.")
            await browser.close()
            return None

        log(f"✅ Found {len(banks_found)} banks: {', '.join(banks_found)}")

        # Click & scrape each bank
        for bank_name in banks_found:
            log(f"📊 Scraping {bank_name}...")
            try:
                await click_bank_tab(page, tab_container, bank_name, log)
                await page.wait_for_timeout(1200)
                rows = await extract_table(page, bank_name)
                log(f"   └─ {len(rows)} rows extracted")
                results.extend(rows)
            except Exception as e:
                log(f"   └─ ❌ Error: {e}")

        await browser.close()

    if not results:
        log("❌ No data extracted.")
        return None

    df = pd.DataFrame(results)
    pivot = df.pivot_table(
        index="Bank", columns="Tenure", values="Monthly", aggfunc="first"
    ).reset_index()

    month_cols = [c for c in pivot.columns if c != "Bank"]

    def month_num(x):
        try:
            return int(x.split()[0])
        except:
            return 999

    month_cols = sorted(month_cols, key=month_num)
    pivot = pivot[["Bank"] + month_cols]

    log(f"✅ Done! {len(banks_found)} banks scraped.")
    return pivot


def run_scrape(url: str, log=print) -> pd.DataFrame | None:
    """Synchronous wrapper — safe to call from threads."""
    return asyncio.run(scrape(url, log))