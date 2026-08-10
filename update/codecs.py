#!/usr/bin/env python3

import os
import requests
import subprocess
import json
import re


OUTPATH = os.getenv('OUTPATH') or 'json'
CODECS_JSON = 'https://browser-resources.s3.yandex.net/linux/codecs.json'
CODECS_SNAP_JSON = "https://browser-resources.s3.yandex.net/linux/codecs_snap.json"

STRINGS_CMD = os.getenv('STRINGS') or 'strings'

BROWSERS = {
    'yandex-browser-stable': (os.getenv('STABLE'), 'browser'),
    'yandex-browser-beta': (os.getenv('BETA'), 'browser-beta'),
}


def extract_chromium_version(name):
    """Return the Chromium version string embedded in the Yandex binary.

    Yandex used to share the last patch digit with Chromium (so filtering by
    patch worked), but modern builds decouple them — the binary now contains
    e.g. `148.0.7778.265` (Chromium) alongside `26.6.1.1084` (Yandex). Pick
    any four-part version with a Chromium-scale major (>=100) that isn't the
    Yandex version itself.
    """
    nix_path, folder_name = BROWSERS[name]
    browser_cmd = f'{nix_path}/opt/yandex/{folder_name}/yandex_browser'
    filename = "/".join([OUTPATH, f'{name}.json'])
    with open(filename, "r") as h:
        yandex_version = json.load(h)['version'].split('-')[0]
    result = subprocess.run(
        [STRINGS_CMD, browser_cmd],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f'Failed to read strings from {browser_cmd}')
    # Chromium version shape today: MAJOR (100-999), MINOR (0), BUILD (4-5 digits),
    # PATCH (0-4 digits). Constraining the shape rejects IPs, mDNS addresses,
    # and placeholders like 9999.9999.9999.9999.
    def looks_like_chromium(s):
        parts = s.split('.')
        try:
            major, minor, build, patch = (int(p) for p in parts)
        except ValueError:
            return False
        return (
            100 <= major <= 999
            and minor == 0
            and 1000 <= build <= 99999
            and 0 <= patch <= 9999
        )
    candidates = sorted({
        s for s in result.stdout.split('\n')
        if re.fullmatch(r'\d+\.\d+\.\d+\.\d+', s)
        and s != yandex_version
        and looks_like_chromium(s)
    })
    if not candidates:
        raise RuntimeError(
            f'No Chromium-shaped version string found in {browser_cmd}'
        )
    return candidates[-1]


def get_codec_sources(url):
    response = requests.get(url)
    if response.ok:
        content = response.text
        return json.loads(content)
    else:
        print('Failed to fetch codec links')


def get_links(name):
    chrver = extract_chromium_version(name)
    chrver_no_patch = '.'.join(chrver.split('.')[0:-1])
    all_codec_sources = get_codec_sources(CODECS_JSON)
    if chrver_no_patch in all_codec_sources:
        return all_codec_sources[chrver_no_patch]
    return []


def prefetch_url(url):
    result = subprocess.run(
        ['nix-prefetch-url', url],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        return result.stdout.strip()
    else:
        return None


def process_links(url_list):
    if len(url_list) == 0:
        return None
    url_count = len(url_list)
    failed = 0
    for url in url_list:
        print(f'Failed urls: {failed} out of {url_count}')
        result = prefetch_url(url)
        if not result:
            failed += 1
            continue
        else:
            version = url.split('/')[-1]\
                         .split('_')[1]\
                         .split('-')[0]
            return {
                'url': url,
                'version': version,
                'sha256': result
            }



def get_snap_info(name):
    chrver = extract_chromium_version(name)
    chrver_major = chrver.split('.')[0]
    all_codec_sources = get_codec_sources(CODECS_SNAP_JSON)
    if chrver_major in all_codec_sources:
        data = all_codec_sources[chrver_major]
        return {
            'version': chrver,
            'url': data['url'],
            'path': data['path']
        }
    return None


def process_snap(data):
    if data:
        prefetch = prefetch_url(data['url'])
        if prefetch:
            return {
                'version': data['version'],
                'url': data['url'],
                'path': data['path'],
                'sha256': prefetch
            }



if __name__ == '__main__':
    for browser in BROWSERS.keys():
        print(f'Processing {browser}')
        links = get_links(browser)
        json_data = process_links(links)
        if json_data is not None:
            with open(f'{OUTPATH}/{browser}-codecs.json', "w") as h:
                json_string = json.dumps(json_data)
                h.write(json_string)
        snap = get_snap_info(browser)
        json_data = process_snap(snap)
        if json_data is not None:
            with open(f'{OUTPATH}/{browser}-codecs.json', "w") as h:
                json_string = json.dumps(json_data)
                h.write(json_string)
        else:
            print("Error fetching codecs")
