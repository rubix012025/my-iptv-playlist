import os
import re
import time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
import yt_dlp

# === CONFIGURATION ===
# Set to False if you want only raw URLs (2 lines per channel).
# Set to True if you want the extra VLC/IPTV player compatibility headers.
INCLUDE_HEADERS = False

def clean_string(s):
    # Standardizes string for comparison (keeps only alphanumeric lowercase characters)
    return re.sub(r'[^a-z0-9]', '', s.lower())

def clean_slug(name):
    # Generates a clean URL slug (e.g. "American Heroes Channel" -> "american-heroes-channel")
    s = name.lower()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    return re.sub(r'[\s-]+', '-', s).strip('-')

def parse_m3u(filename):
    """
    Parses the existing M3U file into blocks to preserve custom metadata structures
    """
    if not os.path.exists(filename):
        return []
        
    print(f"Reading existing playlist '{filename}' to map metadata...")
    try:
        with open(filename, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading {filename}: {e}")
        return []
        
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            extinf = line
            options = []
            url_line = None
            
            # Read ahead to find options and URL
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if not next_line:
                    j += 1
                    continue
                if next_line.startswith("#EXTINF") or next_line.startswith("#EXTM3U"):
                    break
                if next_line.startswith("#"):
                    # Exclude old compatibility headers as they will be re-added if INCLUDE_HEADERS is True
                    if not next_line.startswith("#EXTVLCOPT"):
                        options.append(next_line)
                else:
                    url_line = next_line
                    break
                j += 1
            
            # Extract display name (after the last comma)
            display_name = ""
            if "," in extinf:
                display_name = extinf.split(",")[-1].strip()
            
            is_tvpass = False
            is_youtube = False
            
            if url_line:
                url_lower = url_line.lower()
                if "thetvapp.to" in url_lower or "tvpass.org" in url_lower or "jmp2.uk/plu-" in url_lower:
                    is_tvpass = True
                elif "googlevideo.com" in url_lower or "youtube.com" in url_lower:
                    is_youtube = True
                    
            blocks.append({
                'extinf': extinf,
                'options': options,
                'url': url_line,
                'display_name': display_name,
                'is_tvpass': is_tvpass,
                'is_youtube': is_youtube
            })
            
            i = j if url_line else (i + 1)
        else:
            i += 1
            
    print(f"Parsed {len(blocks)} channel entries.")
    return blocks

def get_youtube_url_for_channel(display_name):
    """
    Fuzzy-matches your display names to their permanent YouTube live handles
    """
    name_lower = display_name.lower()
    if "kapamilya" in name_lower:
        return "https://www.youtube.com/@ABSCBNentertainment/live"
    elif "kapuso" in name_lower or "gma" in name_lower:
        return "https://www.youtube.com/@GMANetwork/live"
    elif "anc" in name_lower:
        return "https://www.youtube.com/@ancalerts/live"
    elif "teleradyo" in name_lower or "dzmm" in name_lower:
        return "https://www.youtube.com/@TeleRadyoSerbisyo/live"
    return None

def get_youtube_stream_url(url):
    """
    Extracts the active .m3u8 stream link from a YouTube live channel URL
    """
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'best',
            'skip_download': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('url')
    except Exception as e:
        print(f"   [Error] YouTube extraction failed: {e}")
        return None

def main():
    # Detects if running on GitHub Actions or locally in PyCharm
    is_github = os.getenv("GITHUB_ACTIONS") == "true"
    m3u_lines = ["#EXTM3U"]
    output_filename = "exclusive.m3u"
    
    # Step 1: Parse the existing M3U file to keep all custom metadata blocks
    blocks = parse_m3u(output_filename)
    if not blocks:
        print("[FATAL] exclusive.m3u not found or empty. Please upload your base playlist first.")
        return
        
    tvpass_blocks = [b for b in blocks if b['is_tvpass']]
    youtube_blocks = [b for b in blocks if b['is_youtube']]
    
    # Step 2: Extract TVPass channels using Playwright (only if TVPass channels are in your file)
    if tvpass_blocks:
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
                    
            print(f"Found {len(scraped_links)} channel links on the TVPass homepage.")
            
            # Scrape each mapped URL in isolated page contexts
            for idx, block in enumerate(tvpass_blocks):
                display_name = block['display_name']
                cleaned_desired = clean_string(display_name)
                
                # Match desired channel name with scraped links
                target_url = None
                for scraped_text, scraped_href in scraped_links:
                    cleaned_scraped = clean_string(scraped_text)
                    if cleaned_desired == cleaned_scraped or cleaned_scraped in cleaned_desired or cleaned_desired in cleaned_scraped:
                        target_url = scraped_href
                        break
                        
                if not target_url:
                    # Fallback URL using clean slug logic
                    slug = clean_slug(display_name)
                    target_url = f"https://tvpass.org/watch/{slug}"
                
                print(f"[{idx+1}/{len(tvpass_blocks)}] Loading: {display_name} -> {target_url}...")
                
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
                    for _ in range(16):
                        if captured_url:
                            break
                        time.sleep(0.5)
                except Exception as e:
                    print(f"   [Error] Page load failed: {e}")
                    
                page.close()
                
                if captured_url:
                    block['url'] = captured_url
                    print(f"   [Success] Captured stream link.")
                else:
                    print(f"   [Failed] No stream link captured. Keeping old link as fallback.")
                    
            browser.close()

    # Step 3: Extract YouTube Live Channels using yt-dlp
    if youtube_blocks:
        print("\nProcessing YouTube Live channels...")
        for idx, block in enumerate(youtube_blocks):
            display_name = block['display_name']
            yt_url = get_youtube_url_for_channel(display_name)
            if yt_url:
                print(f"[{idx+1}/{len(youtube_blocks)}] Extracting YouTube link for {display_name}...")
                captured_yt_url = get_youtube_stream_url(yt_url)
                if captured_yt_url:
                    block['url'] = captured_yt_url
                    print("   [Success] Captured active stream link.")
                else:
                    print("   [Failed] Could not capture stream link. Keeping old link as fallback.")
            else:
                print(f"   [Skip] No matched YouTube handle for {display_name}.")
        
    # Step 4: Assemble and write to final combined M3U file
    for block in blocks:
        if block['url']:
            m3u_lines.append(block['extinf'])
            if block['is_tvpass'] and INCLUDE_HEADERS:
                m3u_lines.append('#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
                m3u_lines.append('#EXTVLCOPT:http-referrer=https://tvpass.org/')
            # Append other non-user-agent options
            for opt in block['options']:
                m3u_lines.append(opt)
            m3u_lines.append(block['url'])

    with open(output_filename, "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_lines))
        
    print(f"\nCompleted! Saved as '{output_filename}' with no blank lines.")

if __name__ == "__main__":
    main()
