import os
import re
import time
import urllib.request
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

# === CONFIGURATION ===
# Set to True if you want the extra VLC/IPTV player compatibility headers for the TVPass channels.
# If your playlist already has these options defined per channel, they will be preserved regardless.
INCLUDE_HEADERS = False

# The filename of your large playlist (e.g. 500+ channels)
M3U_FILENAME = "exclusive.m3u"


def clean_string(s):
    # Standardizes string for comparison (keeps only alphanumeric lowercase characters)
    return re.sub(r'[^a-z0-9]', '', s.lower())


def clean_slug(name):
    # Generates a clean URL slug (e.g. "STUDIO UNIVERSAL" -> "studio-universal")
    s = name.lower()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    return re.sub(r'[\s-]+', '-', s).strip('-')


def verify_m3u8_stream(url):
    """
    Directly tests the .m3u8 link.
    Returns True if the stream is alive and returning valid segments,
    and False if it is offline, blocked, or returns a "No Signal" error page.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://tvpass.org/'
            }
        )
        # 6-second timeout so dead servers don't hang the update process
        with urllib.request.urlopen(req, timeout=6) as response:
            if response.getcode() != 200:
                return False
            
            # Read the first 1500 bytes of the manifest to inspect the content
            chunk = response.read(1500).decode('utf-8', errors='ignore')
            if not chunk.strip().startswith("#EXTM3U"):
                return False
            
            # Verify the manifest contains valid sub-playlists, segments, or chunklists
            valid_indicators = ["#EXT-X-STREAM-INF", "#EXTINF", "#EXT-X-MEDIA", "chunklist"]
            if any(indicator in chunk for indicator in valid_indicators):
                return True
            
            return False
    except Exception:
        # Returns False if the server is offline or returns an error (403/404/503)
        return False


def parse_m3u(filename):
    """
    Parses the entire M3U file into structural blocks.
    Any channels identified as YouTube streams are skipped completely (deleted from the output).
    The remaining stable channels are preserved exactly as-is.
    """
    if not os.path.exists(filename):
        return [], []

    print(f"Reading existing playlist '{filename}'...")
    try:
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {filename}: {e}")
        return [], []

    lines = content.splitlines()
    header_lines = []
    blocks = []
    
    # Extract global EXTM3U header lines at the very top
    start_idx = 0
    while start_idx < len(lines):
        line = lines[start_idx].strip()
        if line.startswith("#EXTM3U"):
            header_lines.append(lines[start_idx])
            start_idx += 1
        elif not line:
            start_idx += 1
        else:
            break

    i = start_idx
    deleted_youtube_count = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            raw_lines = [lines[i]]
            url_line_index = -1
            
            # Read ahead to compile the block for this single channel
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if not next_line:
                    raw_lines.append(lines[j])  # Preserve formatting/empty lines
                    j += 1
                    continue
                if next_line.startswith("#EXTINF"):
                    break
                
                raw_lines.append(lines[j])
                if not next_line.startswith("#"):
                    url_line_index = len(raw_lines) - 1
                j += 1
            
            # Extract display name (after the last comma)
            display_name = ""
            if "," in line:
                display_name = line.split(",")[-1].strip()
                
            url = ""
            if url_line_index != -1:
                url = raw_lines[url_line_index].strip()
                
            if url:
                url_lower = url.lower()
                
                # Check for YouTube links to filter out and delete
                if "youtube.com" in url_lower or "googlevideo.com" in url_lower or "youtu.be" in url_lower:
                    deleted_youtube_count += 1
                    i = j  # Fast-forward pointer to skip this channel block
                    continue
            
            is_expiring = False
            if url:
                url_lower = url.lower()
                
                # Rule 1: Match standard/previous TVPass URL footprints
                if "tvpass.org" in url_lower or "thetvapp.to" in url_lower:
                    is_expiring = True
                # Rule 2: Match active Akamai live stream CDN endpoints (to catch previously updated links)
                elif "akamaized.net" in url_lower or "dice-live" in url_lower:
                    is_expiring = True
                
                # Rule 3: Match explicitly named expiring channels as a fallback
                name_lower = display_name.lower()
                exp_names = ["studio universal", "tap movies", "tap action flix", "blast movies", "tap silog", "tap tv"]
                if any(exp_n in name_lower for exp_n in exp_names):
                    is_expiring = True
                
                # Rule 4: Explicitly EXCLUDE stable proxies (e.g. Pluto TV) so we never touch them
                if "jmp2.uk" in url_lower or "plu-" in url_lower:
                    is_expiring = False
            
            blocks.append({
                'raw_lines': raw_lines,
                'url_line_index': url_line_index,
                'display_name': display_name,
                'url': url,
                'is_expiring': is_expiring
            })
            i = j
        else:
            i += 1

    print(f"Parsed {len(blocks)} channels. Removed {deleted_youtube_count} YouTube channels from the playlist.")
    print(f"Target update count: {len([b for b in blocks if b['is_expiring']])} expiring channels.")
    return header_lines, blocks


def main():
    # Detect if executing inside a headless GitHub Actions environment
    is_github = os.getenv("GITHUB_ACTIONS") == "true"
    
    # Step 1: Parse the large playlist (skips and deletes YouTube channels here)
    header_lines, blocks = parse_m3u(M3U_FILENAME)
    if not blocks:
        print(f"[FATAL] '{M3U_FILENAME}' was not found or is empty. Please place your base playlist first.")
        return

    expiring_blocks = [b for b in blocks if b['is_expiring']]

    # Step 2: Use Playwright to update the target expiring channels
    if expiring_blocks:
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
            
            scraped_links = []
            try:
                temp_page.goto("https://tvpass.org/", wait_until="domcontentloaded", timeout=25000)
                time.sleep(3)
                anchors = temp_page.query_selector_all("a")
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
                print(f"Found {len(scraped_links)} channel links on the TVPass homepage.")
            except Exception as e:
                print(f"[WARNING] Failed to load tvpass.org homepage: {e}. Falling back to default URL slugs.")
            finally:
                temp_page.close()

            # Scrape each mapped URL in isolated page contexts
            for idx, block in enumerate(expiring_blocks):
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
                    # Fallback URL using clean slug logic (e.g., tap-movies)
                    slug = clean_slug(display_name)
                    target_url = f"https://tvpass.org/watch/{slug}"

                print(f"[{idx + 1}/{len(expiring_blocks)}] Loading: {display_name} -> {target_url}...")

                page = context.new_page()
                
                # Performance optimization: Abort heavy and unnecessary image/CSS elements to save RAM
                def block_assets(route):
                    if route.request.resource_type in ["image", "stylesheet", "font", "media"]:
                        route.abort()
                    else:
                        route.continue_()
                page.route("**/*", block_assets)

                captured_url = None

                def handle_request(request):
                    nonlocal captured_url
                    url = request.url
                    parsed = urlparse(url)
                    # Capture direct .m3u8 URLs only
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
                    print("   [Validation] Testing captured stream connection...")
                    # Verify if the stream is active and readable (200 OK & valid playlist data)
                    if verify_m3u8_stream(captured_url):
                        block['raw_lines'][block['url_line_index']] = captured_url
                        print(f"   [Success] Stream is verified active and saved.")
                    else:
                        print(f"   [Rejected] Stream is currently offline or returned 'No Signal'. Keeping old link as fallback.")
                else:
                    print(f"   [Failed] No stream link captured. Keeping old link as fallback.")

            browser.close()

    # Step 3: Assemble and write everything back to the file (excluding YouTube channels)
    final_output = []
    
    # Add preserved global headers if present
    if header_lines:
        final_output.extend(header_lines)
    else:
        final_output.append("#EXTM3U")

    for block in blocks:
        # If this is an expiring channel and INCLUDE_HEADERS is set to True, inject player options safely
        if block['is_expiring'] and INCLUDE_HEADERS and block['url_line_index'] != -1:
            has_ua = any("http-user-agent" in l.lower() for l in block['raw_lines'])
            if not has_ua:
                block['raw_lines'].insert(block['url_line_index'], '#EXTVLCOPT:http-referrer=https://tvpass.org/')
                block['raw_lines'].insert(block['url_line_index'], '#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        final_output.extend(block['raw_lines'])

    # Write non-destructively back to the target file
    with open(M3U_FILENAME, "w", encoding="utf-8") as f:
        f.write("\n".join(final_output))

    print(f"\nCompleted! Saved and updated '{M3U_FILENAME}' with no impact to other channels.")


if __name__ == "__main__":
    main()
