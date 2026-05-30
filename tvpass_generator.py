import os
import re
import time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

# === CONFIGURATION ===
# Set to False if you want only raw URLs (2 lines per channel).
# Set to True if you want the extra VLC/IPTV player compatibility headers.
INCLUDE_HEADERS = False

# List of desired channels to output
CHANNELS_TO_FIND = [
    "animal-planet-us-east",
    "cartoon-network-usa-eastern-feed",
    "cinemax-eastern-feed",
    "comedy-central-us-eastern-feed",
    "cbs-sports-network-usa",
    "chicago-sports-network",
    "crime-investigation-network-usa-hd",
    "destination-america",
    "discovery-channel-us-eastern-feed",
    "discovery-family-channel",
    "discovery-life-channel",
    "disney-eastern-feed",
    "disney-junior-usa-east",
    "disney-xd-usa-eastern-feed",
    "e-entertainment-usa-eastern-feed",
    "espn2",
    "fanduel-sports-indiana",
    "food-network-usa-eastern-feed",
    "fx-movie-channel",
    "fx-networks-east-coast",
    "fxx-usa-eastern",
    "fyi-usa-eastern",
    "hallmark-eastern-feed",
    "hallmark-family-hd",
    "hallmark-mystery-eastern-hd",
    "hbo-family-eastern-feed",
    "hbo-zone-hd-east",
    "history-channel-us-eastern-feed",
    "independent-film-channel-us",
    "investigation-discovery-usa-eastern",
    "lifetime-movies-east",
    "metv-toons-wjlp2-new-jersey",
    "metv-wjlp-new-jerseynew-york",
    "national-geographic-wild",
    "nba-tv-usa",
    "nick-jr-east",
    "nickelodeon-usa-east-feed",
    "nicktoons-east",
    "oprah-winfrey-network-usa-eastern",
    "reelzchannel",
    "science",
    "paramount-with-showtime-eastern-feed",
    "showtime-2-eastern",
    "syfy-eastern-feed",
    "tbs-east",
    "teennick-eastern",
    "the-cooking-channel",
    "the-weather-channel",
    "tlc-usa-eastern",
    "tmc-us-eastern-feed (MOVIE)",
    "tnt-eastern-feed",
    "travel-us-east",
    "trutv-usa-eastern",
    "tsn1",
    "tsn2",
    "tsn3",
    "tsn4",
    "tsn5",
    "turner-classic-movies-usa",
    "tv-land-eastern",
    "usa-network-east-feed",
    "ae-us-eastern-feed",
    "amc-eastern-feed",
    "american-heroes-channel",
    "bbc-america-east",
    "bravo-usa-eastern-feed",
    "cmt-us-eastern-feed",
    "freeform-east-feed",
    "fuse-tv-eastern-feed",
    "game-show-network-east",
    "hgtv-usa-eastern-feed",
    "lifetime-network-us-eastern-feed",
    "logo-east",
    "hbo-2-eastern-feed",
    "hbo-signature-hbo-3-eastern",
    "moremax-eastern",
    "moviemax-max-6-east",
    "vh1-eastern-feed",
    "we-womens-entertainment-eastern",
    "ion-eastern-feed"
]

def clean_string(s):
    # Keep only alphanumeric lowercase characters
    return re.sub(r'[^a-z0-9]', '', s.lower())

def get_permanent_channels(filename):
    """
    Parses the existing M3U file to preserve any permanent non-TVPass channels
    """
    permanent_blocks = []
    if not os.path.exists(filename):
        return permanent_blocks
        
    print(f"Reading existing playlist '{filename}' to preserve permanent channels...")
    try:
        with open(filename, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading {filename}: {e}")
        return permanent_blocks
        
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            block_lines = [line]
            j = i + 1
            url_line = None
            while j < len(lines):
                next_line = lines[j].strip()
                if not next_line:
                    j += 1
                    continue
                if next_line.startswith("#EXTINF") or next_line.startswith("#EXTM3U"):
                    break
                if next_line.startswith("#"):
                    block_lines.append(next_line)
                else:
                    url_line = next_line
                    block_lines.append(next_line)
                    break
                j += 1
            
            # Check if this channel belongs to TVPass/thetvapp/Pluto
            is_dynamic = False
            if url_line:
                url_lower = url_line.lower()
                if "thetvapp.to" in url_lower or "tvpass.org" in url_lower or "jmp2.uk" in url_lower:
                    is_dynamic = True
            
            # If it is a permanent channel, preserve its block
            if not is_dynamic:
                permanent_blocks.extend(block_lines)
            
            i = j if url_line else (i + 1)
        else:
            i += 1
            
    print(f"Preserved {len(permanent_blocks) // 2} permanent channels from previous file.")
    return permanent_blocks

def main():
    # Detects if running on GitHub Actions or locally in PyCharm
    is_github = os.getenv("GITHUB_ACTIONS") == "true"
    m3u_lines = ["#EXTM3U"]
    output_filename = "exclusive.m3u"
    
    # Step 1: Read existing playlist and load any non-expiring/permanent channels first
    permanent_channels = get_permanent_channels(output_filename)
    m3u_lines.extend(permanent_channels)
    
    with sync_playwright() as playwright:
        print("Launching browser...")
        try:
            if is_github:
                browser = playwright.chromium.launch(headless=True)
            else:
                try:
                    browser = playwright.chromium.launch(headless=False, channel="chrome")
                except Exception:
                    browser = playwright.chromium.launch(headless=False)
        except Exception as launch_error:
            print(f"[FATAL] Browser launch failed: {launch_error}")
            return

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Open home page to parse active paths
        temp_page = context.new_page()
        print("Opening tvpass.org homepage...")
        try:
            temp_page.goto("https://tvpass.org/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
        except Exception as e:
            print(f"[FATAL] Failed to reach tvpass.org: {e}")
            temp_page.close()
            browser.close()
            return
            
        anchors = temp_page.query_selector_all("a")
        scraped_links = []
        for a in anchors:
            try:
                href = a.get_attribute("href")
                text = a.inner_text().strip()
                if href and text:
                    if href.startswith("/"):
                        href = "https://tvpass.org" + href
                    scraped_links.append((text, href))
            except Exception:
                continue
        temp_page.close()
                
        print(f"Found {len(scraped_links)} channel links on the homepage.")
        
        # Map channels
        matched_channels = []
        for desired_name in CHANNELS_TO_FIND:
            cleaned_desired = clean_string(desired_name)
            
            best_match_url = None
            for scraped_text, scraped_href in scraped_links:
                cleaned_scraped = clean_string(scraped_text)
                if cleaned_desired == cleaned_scraped or cleaned_scraped in cleaned_desired or cleaned_desired in cleaned_scraped:
                    best_match_url = scraped_href
                    break
                    
            if best_match_url:
                matched_channels.append((desired_name, best_match_url))
            else:
                fallback_url = f"https://tvpass.org/watch/{desired_name}"
                matched_channels.append((desired_name, fallback_url))
                
        print(f"Successfully mapped {len(matched_channels)} channels.")
        
        # Query each mapped URL in isolated page contexts
        for idx, (display_name, target_url) in enumerate(matched_channels):
            print(f"[{idx+1}/{len(matched_channels)}] Loading: {display_name}...")
            
            # Isolated session per channel page
            page = context.new_page()
            captured_url = None
            
            def handle_request(request):
                nonlocal captured_url
                url = request.url
                parsed = urlparse(url)
                # Strict path matching: only capture direct .m3u8 urls, excluding pings
                if parsed.path.endswith(".m3u8") and parsed.query and "ping.gif" not in url:
                    captured_url = url

            page.on("request", handle_request)
            
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                
                # Check for the link
                for _ in range(16):
                    if captured_url:
                        break
                    time.sleep(0.5)
            except Exception as e:
                print(f"   [Error] Page load failed: {e}")
                
            page.close()
            
            if captured_url:
                m3u_lines.append(f"#EXTINF:-1,{display_name}")
                if INCLUDE_HEADERS:
                    m3u_lines.append('#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
                    m3u_lines.append('#EXTVLCOPT:http-referrer=https://tvpass.org/')
                m3u_lines.append(captured_url)
                print(f"   [Success] Captured stream link.")
            else:
                print(f"   [Failed] No stream link captured.")
                if not is_github:
                    print("   [Tip] Solve any Cloudflare verification challenge manually if it appears.")
                
        browser.close()
        
    # Write to final combined M3U file
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_lines))
        
    print(f"\nCompleted! Saved as '{output_filename}' with no blank lines.")

if __name__ == "__main__":
    main()
