import time
from playwright.sync_api import sync_playwright

# Format: (Display Name, tvpass.org TV Slug)
CHANNELS = [
    ("animal-planet-us-east", "animal-planet-us-east"),
    ("cartoon-network-usa-eastern-feed", "cartoon-network-usa-eastern-feed"),
    ("cinemax-eastern-feed", "cinemax-eastern-feed"),
    ("comedy-central-us-eastern-feed", "comedy-central-us-eastern-feed"),
    ("cbs-sports-network-usa", "cbs-sports-network-usa"),
    ("chicago-sports-network", "chicago-sports-network"),
    ("crime-investigation-network-usa-hd", "crime-investigation-network-usa-hd"),
    ("destination-america", "destination-america"),
    ("discovery-channel-us-eastern-feed", "discovery-channel-us-eastern-feed"),
    ("discovery-family-channel", "discovery-family-channel"),
    ("discovery-life-channel", "discovery-life-channel"),
    ("disney-eastern-feed", "disney-eastern-feed"),
    ("disney-junior-usa-east", "disney-junior-usa-east"),
    ("disney-xd-usa-eastern-feed", "disney-xd-usa-eastern-feed"),
    ("e-entertainment-usa-eastern-feed", "e-entertainment-usa-eastern-feed"),
    ("espn2", "espn2"),
    ("fanduel-sports-indiana", "fanduel-sports-indiana"),
    ("food-network-usa-eastern-feed", "food-network-usa-eastern-feed"),
    ("fx-movie-channel", "fx-movie-channel"),
    ("fx-networks-east-coast", "fx-networks-east-coast"),
    ("fxx-usa-eastern", "fxx-usa-eastern"),
    ("fyi-usa-eastern", "fyi-usa-eastern"),
    ("hallmark-eastern-feed", "hallmark-eastern-feed"),
    ("hallmark-family-hd", "hallmark-family-hd"),
    ("hallmark-mystery-eastern-hd", "hallmark-mystery-eastern-hd"),
    ("hbo-family-eastern-feed", "hbo-family-eastern-feed"),
    ("hbo-zone-hd-east", "hbo-zone-hd-east"),
    ("history-channel-us-eastern-feed", "history-channel-us-eastern-feed"),
    ("independent-film-channel-us", "independent-film-channel-us"),
    ("investigation-discovery-usa-eastern", "investigation-discovery-usa-eastern"),
    ("lifetime-movies-east", "lifetime-movies-east"),
    ("metv-toons-wjlp2-new-jersey", "metv-toons-wjlp2-new-jersey"),
    ("metv-wjlp-new-jerseynew-york", "metv-wjlp-new-jerseynew-york"),
    ("national-geographic-wild", "national-geographic-wild"),
    ("nba-tv-usa", "nba-tv-usa"),
    ("nick-jr-east", "nick-jr-east"),
    ("nickelodeon-usa-east-feed", "nickelodeon-usa-east-feed"),
    ("nicktoons-east", "nicktoons-east"),
    ("oprah-winfrey-network-usa-eastern", "oprah-winfrey-network-usa-eastern"),
    ("reelzchannel", "reelzchannel"),
    ("science", "science"),
    ("paramount-with-showtime-eastern-feed", "paramount-with-showtime-eastern-feed"),
    ("showtime-2-eastern", "showtime-2-eastern"),
    ("syfy-eastern-feed", "syfy-eastern-feed"),
    ("tbs-east", "tbs-east"),
    ("teennick-eastern", "teennick-eastern"),
    ("the-cooking-channel", "the-cooking-channel"),
    ("the-weather-channel", "the-weather-channel"),
    ("tlc-usa-eastern", "tlc-usa-eastern"),
    ("tmc-us-eastern-feed (MOVIE)", "the-movie-channel-east"),
    ("tnt-eastern-feed", "tnt-eastern-feed"),
    ("travel-us-east", "travel-us-east"),
    ("trutv-usa-eastern", "trutv-usa-eastern"),
    ("tsn1", "tsn1"),
    ("tsn2", "tsn2"),
    ("tsn3", "tsn3"),
    ("tsn4", "tsn4"),
    ("tsn5", "tsn5"),
    ("turner-classic-movies-usa", "turner-classic-movies-usa"),
    ("tv-land-eastern", "tv-land-eastern"),
    ("usa-network-east-feed", "usa-network-east-feed"),
    ("ae-us-eastern-feed", "ae-us-eastern-feed"),
    ("amc-eastern-feed", "amc-eastern-feed"),
    ("american-heroes-channel", "american-heroes-channel"),
    ("bbc-america-east", "bbc-america-east"),
    ("bravo-usa-eastern-feed", "bravo-usa-eastern-feed"),
    ("cmt-us-eastern-feed", "cmt-us-eastern-feed"),
    ("freeform-east-feed", "freeform-east-feed"),
    ("fuse-tv-eastern-feed", "fuse-tv-eastern-feed"),
    ("game-show-network-east", "game-show-network-east"),
    ("hgtv-usa-eastern-feed", "hgtv-usa-eastern-feed"),
    ("lifetime-network-us-eastern-feed", "lifetime-network-us-eastern-feed"),
    ("logo-east", "logo-east"),
    ("hbo-2-eastern-feed", "hbo-2-eastern-feed"),
    ("hbo-signature-hbo-3-eastern", "hbo-signature-hbo-3-eastern"),
    ("moremax-eastern", "moremax-eastern"),
    ("moviemax-max-6-east", "moviemax-max-6-east"),
    ("vh1-eastern-feed", "vh1-eastern-feed"),
    ("we-womens-entertainment-eastern", "we-womens-entertainment-eastern"),
    ("ion-eastern-feed", "ion-eastern-feed")
]

BASE_URL = "https://tvpass.org/tv/{}"

def main():
    m3u_lines = []
    m3u_lines.append("#EXTM3U")
    
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for idx, (display_name, slug) in enumerate(CHANNELS):
            print(f"[{idx+1}/{len(CHANNELS)}] Processing {display_name}...")
            
            captured_url = None
            
            def handle_request(request):
                nonlocal captured_url
                url = request.url
                if ".m3u8" in url and ("token=" in url or "expires=" in url):
                    captured_url = url

            page.on("request", handle_request)
            
            try:
                page.goto(BASE_URL.format(slug), wait_until="domcontentloaded", timeout=15000)
                time.sleep(2.5)
            except Exception as e:
                print(f"   [Error] Could not load page: {e}")
            
            page.remove_listener("request", handle_request)
            
            if captured_url:
                m3u_lines.append(f"#EXTINF:-1,{display_name}")
                m3u_lines.append(captured_url)
                print(f"   [Success] Captured stream link.")
            else:
                print(f"   [Failed] No stream link captured.")
                
        browser.close()
        
    # Write directly to file without blank lines
    with open("tvpass_playlist.m3u", "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_lines))
        
    print("\nPlaylist updated successfully.")

if __name__ == "__main__":
    main()
