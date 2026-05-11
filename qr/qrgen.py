#!/usr/bin/env python
# coding: utf8

#
# Copyright (c) 2019 Stefan Kienzle
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


import argparse
import json
import os.path
import re
import shutil
import subprocess
import urllib.parse
import urllib.request

# Parse the command line arguments
arg_parser = argparse.ArgumentParser(
    description="Generates an HTML page containing cards with embedded QR codes that can be interpreted by `qrplay`."
)
arg_parser.add_argument(
    "--input", help="the file containing the list of commands and songs to generate"
)
arg_parser.add_argument(
    "--generate-images",
    action="store_true",
    help="generate an individual PNG image for each card",
)
arg_parser.add_argument(
    "--print-dublex",
    action="store_true",
    help="generate cards optimized for duplex print",
    default=False,
)
arg_parser.add_argument(
    "--sonos-hostname",
    help="hostname or IP of the machine running node-sonos-http-api, used to fetch playlist/favorite artwork",
)
args = arg_parser.parse_args()
print(args)


# Matches Apple Music playlist URLs, e.g.
# https://music.apple.com/nl/playlist/cowboy/pl.u-9N9L24eF7Z9Am8?l=en
_APPLE_MUSIC_PLAYLIST_URL_RE = re.compile(
    r"https://music\.apple\.com/[^/\s]+/playlist/([^/?#\s]+)/(pl\.[^?#&\s]+)"
)
# Matches the short playlist ID suffix users can type instead of the full URL,
# e.g. "9N9L24eF7Z9Am8" (the part after "pl.u-").
# Requires mixed case AND at least one digit — real words like "Californication"
# never match because they lack digits or uppercase letters.
_APPLE_MUSIC_PLAYLIST_SHORT_RE = re.compile(
    r"^(?=.*\d)(?=.*[A-Z])(?=.*[a-z])[A-Za-z0-9]{10,}$"
)


def fetch_apple_music_artwork(url):
    """Scrape the og:image tag from an Apple Music page to get playlist cover art."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            },
        )
        html = (
            urllib.request.urlopen(req, timeout=10)
            .read()
            .decode("utf-8", errors="replace")
        )
        for pattern in [
            r'property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
            r'content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
        ]:
            m = re.search(pattern, html)
            if m:
                art = m.group(1)
                # og:image is 1200x630 (widescreen). Swap to square on the mzstatic CDN.
                art = re.sub(r"\d+x\d+\S+\.jpg$", "600x600bb.jpg", art)
                return art
        print("Warning: no og:image found on Apple Music page")
    except Exception as e:
        print("Warning: could not fetch Apple Music artwork from {}: {}".format(url, e))
    return None


def expand_apple_music_url(line):
    """Detect an Apple Music playlist reference and expand it into a full qrgen line.

    Supported input formats (name is optional — derived from the URL slug if absent):
      https://music.apple.com/.../playlist/name/pl.xxx     ← full share URL
      Custom Name | https://music.apple.com/.../playlist/name/pl.xxx
      Custom Name | 9N9L24eF7Z9Am8                         ← short ID (part after pl.u-)

    Returns an expanded line like:
      applemusic:playlist:pl.xxx|Display Name||artwork_url
    or None if the line doesn\'t match any of the above formats.
    """
    # --- Full URL format ---
    m = _APPLE_MUSIC_PLAYLIST_URL_RE.search(line)
    if m:
        url_slug = m.group(1)  # e.g. "cowboy"
        playlist_id = m.group(2)  # e.g. "pl.u-9N9L24eF7Z9Am8"
        full_url = m.group(0)  # the matched URL (without query string)
        custom_name = line.replace(full_url, "").replace("|", "").strip()
        name = custom_name if custom_name else url_slug.replace("-", " ").title()
        arturl = (
            fetch_apple_music_artwork(full_url)
            or "https://img.icons8.com/ios/540/playlist.png"
        )
        print("Apple Music playlist '{}' ({})".format(name, playlist_id))
        return "applemusic:playlist:{}|{}||{}".format(playlist_id, name, arturl)

    # --- Short ID format: Name | SHORTID ---
    parts = [p.strip() for p in line.split("|")]
    if len(parts) == 2:
        name, shortid = parts
        if _APPLE_MUSIC_PLAYLIST_SHORT_RE.match(shortid) and not shortid.isdigit():
            playlist_id = "pl.u-" + shortid
            # Construct a minimal Apple Music URL so we can scrape the artwork.
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            art_url = "https://music.apple.com/us/playlist/{}/{}".format(
                slug, playlist_id
            )
            arturl = (
                fetch_apple_music_artwork(art_url)
                or "https://img.icons8.com/ios/540/playlist.png"
            )
            print("Apple Music playlist '{}' ({})".format(name, playlist_id))
            return "applemusic:playlist:{}|{}||{}".format(playlist_id, name, arturl)

    return None


# Cache iTunes artwork lookups so repeated runs (or duplicate entries) don't
# hammer the API.
_itunes_cache = {}
_itunes_search_cache = {}


def get_itunes_artwork(album_id):
    """Return a 600x600 artwork URL for an iTunes album ID, or None on failure."""
    if album_id in _itunes_cache:
        return _itunes_cache[album_id]
    try:
        url = "https://itunes.apple.com/lookup?id={}".format(album_id)
        response = urllib.request.urlopen(url, timeout=10)
        data = json.loads(response.read().decode("utf-8"))
        results = data.get("results", [])
        if results:
            art = results[0].get("artworkUrl100", "")
            # Scale up from the default 100x100 thumbnail to 600x600.
            art = art.replace("100x100bb", "600x600bb")
            print("iTunes artwork for {}: {}".format(album_id, art))
            _itunes_cache[album_id] = art
            return art
        print("Warning: no iTunes results for album ID {}".format(album_id))
    except Exception as e:
        print("Warning: iTunes lookup failed for ID {}: {}".format(album_id, e))
    _itunes_cache[album_id] = None
    return None


def lookup_apple_music_album(artist, title):
    """Search the iTunes API for an album by artist + title.

    Strategy:
      1. Direct album search (fast, works for many artists).
      2. If that finds nothing, look up the artist ID then browse their full
         discography (slower but far more reliable).

    Returns (album_id, artwork_url) or (None, None) on failure.
    """
    key = (artist.lower(), title.lower())
    if key in _itunes_search_cache:
        return _itunes_search_cache[key]

    artist_l = artist.lower()
    title_l = title.lower()

    def best_match(results):
        """Return the first result whose artist AND title are substring matches."""
        for r in results:
            r_artist = r.get("artistName", "").lower()
            r_title = r.get("collectionName", "").lower()
            if (artist_l in r_artist or r_artist in artist_l) and (
                title_l in r_title or r_title in title_l
            ):
                return r
        return None

    found = None

    # --- Step 1: direct search (single API call, fast) ---
    try:
        q = urllib.parse.quote_plus("{} {}".format(artist, title))
        url = "https://itunes.apple.com/search?term={}&entity=album&limit=10".format(q)
        data = json.loads(
            urllib.request.urlopen(url, timeout=10).read().decode("utf-8")
        )
        found = best_match(data.get("results", []))
    except Exception as e:
        print(
            "Warning: direct iTunes search error for '{}' by '{}': {}".format(
                title, artist, e
            )
        )

    # --- Step 2: artist ID → full discography browse (more reliable fallback) ---
    if not found:
        try:
            q = urllib.parse.quote_plus(artist)
            url = "https://itunes.apple.com/search?term={}&entity=musicArtist&limit=3".format(
                q
            )
            data = json.loads(
                urllib.request.urlopen(url, timeout=10).read().decode("utf-8")
            )
            artists = data.get("results", [])
            if artists:
                artist_id = artists[0]["artistId"]
                url2 = "https://itunes.apple.com/lookup?id={}&entity=album&limit=100".format(
                    artist_id
                )
                data2 = json.loads(
                    urllib.request.urlopen(url2, timeout=10).read().decode("utf-8")
                )
                albums = [
                    r
                    for r in data2.get("results", [])
                    if r.get("wrapperType") == "collection"
                ]
                found = best_match(albums)
        except Exception as e:
            print(
                "Warning: artist-browse iTunes search error for '{}' by '{}': {}".format(
                    title, artist, e
                )
            )

    if found:
        album_id = str(found["collectionId"])
        art = found.get("artworkUrl100", "").replace("100x100bb", "600x600bb")
        print(
            "iTunes: '{}' by '{}' → ID {} ('{}' by '{}')".format(
                title,
                artist,
                album_id,
                found.get("collectionName"),
                found.get("artistName"),
            )
        )
        _itunes_search_cache[key] = (album_id, art)
        return album_id, art

    print("Warning: could not find '{}' by '{}' on iTunes".format(title, artist))
    _itunes_search_cache[key] = (None, None)
    return None, None


def expand_simple_apple_music(line):
    """Detect and expand simple Apple Music shorthand into a full qrgen line.

    Supported formats:
      Artist | Title | iTunesID   →  uses ID directly, fetches artwork
      Artist | Title              →  searches iTunes for the album ID + artwork

    Returns the expanded line, or None if the line doesn't match either format.
    """
    parts = [p.strip() for p in line.split("|")]
    if len(parts) == 3 and parts[2].isdigit():
        # Format: Artist | Title | ID
        artist, title, album_id = parts
        arturl = get_itunes_artwork(album_id) or ""
    elif len(parts) == 2 and not any(
        p.startswith(
            (
                "applemusic:",
                "spotify:",
                "favorite:",
                "playlist:",
                "cmd:",
                "tunein:",
                "lib:",
                "amazonmusic:",
            )
        )
        for p in parts
    ):
        artist, title_raw = parts
        # Also accept: Artist | Title (iTunesID)
        id_in_parens = re.match(r"^(.+?)\s*\((\d+)\)\s*$", title_raw)
        if id_in_parens:
            title, album_id = id_in_parens.group(1).strip(), id_in_parens.group(2)
            arturl = get_itunes_artwork(album_id) or ""
        else:
            # No ID at all — search iTunes
            title = title_raw
            album_id, arturl = lookup_apple_music_album(artist, title)
            if not album_id:
                print(
                    "Warning: skipping '{}' by '{}' — could not find on iTunes".format(
                        title, artist
                    )
                )
                return None
    else:
        return None
    return "applemusic:album:{}|{}|{}|{}".format(album_id, title, artist, arturl)


def get_sonos_artwork(name):
    """Look up the artwork URL for a favorite/playlist by name from the Sonos HTTP API.
    If multiple entries share the same name, returns the first whose URL is reachable."""
    if not args.sonos_hostname:
        return None

    def normalize(s):
        """Collapse visually identical quote/apostrophe characters so that
        e.g. U+2019 (curly \u2019) and U+0027 (straight ') compare equal."""
        return (
            s.replace("\u2018", "'")
            .replace("\u2019", "'")
            .replace("\u201c", '"')
            .replace("\u201d", '"')
        )

    name_norm = normalize(name)
    try:
        url = "http://{}:5005/favorites/detailed".format(args.sonos_hostname)
        response = urllib.request.urlopen(url, timeout=5)
        favorites = json.loads(response.read().decode("utf-8"))
        candidates = [
            f.get("albumArtUri")
            for f in favorites
            if normalize(f.get("title", "")) == name_norm
        ]
        if not candidates:
            print("Warning: no Sonos artwork found for '{}'".format(name))
            return None
        for art in candidates:
            try:
                urllib.request.urlopen(art, timeout=5)
                print("Found Sonos artwork for '{}': {}".format(name, art))
                return art
            except Exception:
                print(
                    "Skipping unreachable artwork URL for '{}': {}".format(
                        name, art[:60]
                    )
                )
        print("Warning: all artwork URLs for '{}' were unreachable".format(name))
    except Exception as e:
        print("Warning: could not fetch artwork from Sonos: {}".format(e))
    return None


def process_command(line, index):
    split = re.split("\\|", line)

    if line.startswith("cmd:say"):
        (cmdname, arturl, qrcode) = (
            split[2],
            split[3],
            (split[0] + "|" + split[1] + "|" + split[2]),
        )
    elif line.startswith("cmd:room"):
        (cmdname, arturl, qrcode) = (split[1], split[2], (split[0] + "|" + split[1]))
    else:
        (cmdname, arturl, qrcode) = (split[1], split[2], split[0])

    # Determine the output image file names
    qrout = "out/{0}qr.png".format(index)
    artout = "out/{0}art.png".format(index)

    # Create a QR code from the command URI
    print(subprocess.check_output(["qrencode", "-s", "100", "-o", qrout, qrcode]))

    # Fetch the artwork and save to the output directory
    print(subprocess.check_output(["curl", arturl, "-o", artout]))

    return (cmdname, None, None)


def process_tunein(line, index):
    split = re.split("\\|", line)

    (cmdname, arturl, qrcode) = (split[1], split[2], split[0])

    # Determine the output image file names
    qrout = "out/{0}qr.png".format(index)
    artout = "out/{0}art.png".format(index)

    # Create a QR code from the command URI
    print(subprocess.check_output(["qrencode", "-s", "100", "-o", qrout, qrcode]))

    # Fetch the artwork and save to the output directory
    print(subprocess.check_output(["curl", arturl, "-o", artout]))

    return (cmdname, None, None)


def process_playlist_favorite(line, index):
    split = re.split("\\|", line)

    (cmdname, arturl, qrcode) = (split[1], split[2], split[0])

    # Try to get a fresh artwork URL from the Sonos API (overrides the static URL in the input file)
    sonos_art = get_sonos_artwork(cmdname)
    if sonos_art:
        arturl = sonos_art

    # Determine the output image file names
    qrout = "out/{0}qr.png".format(index)
    artout = "out/{0}art.png".format(index)

    # Create a QR code from the command URI
    print(subprocess.check_output(["qrencode", "-s", "100", "-o", qrout, qrcode]))

    # Fetch the artwork and save to the output directory
    print(subprocess.check_output(["curl", arturl, "-o", artout]))

    return (cmdname, None, None)


def process_track(line, index):
    split = re.split("\\|", line)

    service = re.split("\\:", line)[0]

    if ":album:" in line or ":playlist:" in line:
        album = split[1]
        song = None
        artist = split[2] or None  # empty string → None for playlists
        arturl = split[3]
    else:
        album = split[2]
        song = split[1]
        artist = split[3]
        arturl = split[4]

    # Determine the output image file names
    qrout = "out/{0}qr.png".format(index)
    artout = "out/{0}art.png".format(index)

    # Create a QR code from the track URI
    print(subprocess.check_output(["qrencode", "-s", "100", "-o", qrout, split[0]]))

    # Fetch the artwork and save to the output directory
    print(subprocess.check_output(["curl", arturl, "-o", artout]))

    return (song, album, artist, service)


# Return the HTML content for a single card.
def card_content_html(index, artist, album, song, service):
    qrimg = "{0}qr.png".format(index)
    artimg = "{0}art.png".format(index)
    serviceimg = "{0}.png".format(service)

    html = ""
    html += '  <img src="{0}" class="art"/>\n'.format(artimg)
    html += '  <img src="{0}" class="qrcode"/>\n'.format(qrimg)
    html += '  <div class="labels track-info">\n'
    html += '    <p class="song">{0}</p>\n'.format(song or album)
    if artist:
        html += '    <p class="artist">{0}</p>\n'.format(artist)
    if album and song is not None:
        html += '    <p class="album">{0}</p>\n'.format(album)
    html += "  </div>\n"

    return html


# Generate a PNG version of an individual card (with no dashed lines).
def generate_individual_card_image(index, artist, album, song, service):
    # First generate an HTML file containing the individual card
    html = """
<!DOCTYPE html>
<head>
  <meta charset="utf-8">
  <link rel="stylesheet" href="cards.css">
</head>
<body>
  <div class="card">
"""
    html += card_content_html(index, artist, album, song, service)
    html += """
</div>
</body>
</html>
"""

    html_filename = "out/{0}.html".format(index)
    with open(html_filename, "w") as f:
        f.write(html)

    # Then convert the HTML to a PNG image (beware the hardcoded values; these need to align
    # with the dimensions in `cards.css`)
    png_filename = "out/{0}".format(index)
    print(
        subprocess.check_output(
            [
                "webkit2png",
                html_filename,
                "--scale=1.0",
                "--clipped",
                "--clipwidth=720",
                "--clipheight=640",
                "--delay=2",
                "-o",
                png_filename,
            ]
        )
    )

    # Rename the file to remove the extra `-clipped` suffix that `webkit2png` includes by default
    os.rename(png_filename + "-clipped.png", png_filename + "card.png")


def generate_cards():
    service = ""
    duplex = args.print_dublex
    htmlarr = []

    def print_card_back():
        html = ""
        if duplex and len(htmlarr) > 0:
            html += '<br style="clear: both;"/>\n'
            html += '<div class="back">'
            for back in htmlarr:
                html += back

            html += "</div>"
            del htmlarr[:]
            html += '<br style="clear: both;"/>\n'

        return html

    # Create the output directory
    dirname = os.getcwd()
    outdir = os.path.join(dirname, "out")
    print(outdir)
    if os.path.exists(outdir):
        shutil.rmtree(outdir)
    os.mkdir(outdir)

    # Read the file containing the list of commands and songs to generate
    with open(args.input) as f:
        lines = f.readlines()

    # The index of the current item being processed
    index = 0

    # Copy the CSS file into the output directory.  (Note the use of 'page-break-inside: avoid'
    # in `cards.css`; this prevents the card divs from being spread across multiple pages
    # when printed.)
    shutil.copyfile("cards/cards.css", "out/cards.css")

    # Begin the HTML template
    html = """
<!DOCTYPE html>
<head>
  <meta charset="utf-8">
  <link rel="stylesheet" href="cards.css">
</head>
"""
    if duplex:
        html += '<body class="duplex">'
    else:
        html += "<body>"

    for line in lines:
        # Trim newline
        line = line.strip()

        # Remove any trailing comments and newline (and ignore any empty or comment-only lines)
        line = line.split("#")[0]
        line = line.strip()
        if not line:
            continue

        # Expand Apple Music playlist URLs first.
        expanded = expand_apple_music_url(line)
        if not expanded:
            # Then try the simple Artist | Title (| ID) shorthand.
            expanded = expand_simple_apple_music(line)
        if expanded:
            line = expanded

        if line.startswith("cmd:"):
            (song, album, artist) = process_command(line, index)
        elif (
            line.startswith("applemusic:")
            or line.startswith("amazonmusic:")
            or line.startswith("spotify:")
            or line.startswith("aldilife:")
            or line.startswith("napster:")
            or line.startswith("lib:")
        ):
            (song, album, artist, service) = process_track(line, index)
        elif line.startswith("tunein:"):
            (song, album, artist) = process_tunein(line, index)
        elif line.startswith("favorite:") or line.startswith("playlist:"):
            (song, album, artist) = process_playlist_favorite(line, index)
        else:
            print("Failed to handle URI: " + line)
            continue

        # Append the HTML for this card
        cardhtml = '<div class="card">\n'
        cardhtml += card_content_html(index, artist, album, song, service)
        cardhtml += "</div>\n"

        if args.generate_images:
            # Also generate an individual PNG for the card
            generate_individual_card_image(index, artist, album, song, service)

        if duplex:
            if index % 4 == 3:
                cardhtml += '<br style="clear: both;"/>\n'
        else:
            if index % 2 == 1:
                cardhtml += '<br style="clear: both;"/>\n'

        html += cardhtml

        if duplex:
            htmlarr.append(cardhtml)

            if index % 12 == 11:
                html += print_card_back()

        index += 1

    html += print_card_back()
    html += "</body>\n"
    html += "</html>\n"

    print(html)

    with open("out/index.html", "w") as f:
        f.write(html)


generate_cards()
