import time
import requests
import xml.etree.ElementTree as ET
import idna
import re

# Official MF redirect IP (per the WeWy spec) — 302 to the komunikat page.
# For ISP compliance the domain must resolve HERE, not to a blackhole.
REDIRECT_IP = '145.237.235.240'

def is_valid_domain(domain):
    # Regex to check for valid domain characters allowed in IDNs
    pattern = re.compile(r'^[a-z0-9-\.]*$', re.IGNORECASE)
    return pattern.match(domain) is not None

def fetch_register(url, attempts=5):
    # The MF server occasionally returns a transient 500 on the 8+ MB response —
    # a daily job must survive it with retries instead of failing (stale blocklist otherwise).
    headers = {'User-Agent': 'Mozilla/5.0 (hazard-rsc)', 'Accept': 'application/xml'}
    for i in range(1, attempts + 1):
        try:
            response = requests.get(url, headers=headers, timeout=60)
            response.raise_for_status()
            return response.content
        except requests.RequestException as e:
            if i == attempts:
                raise
            wait = i * 10
            print(f'attempt {i}/{attempts} failed ({e}); retrying in {wait}s')
            time.sleep(wait)

def download_and_parse_xml(url, txt_file, namespace):
    # Parse the XML content from the response
    root = ET.fromstring(fetch_register(url))

    # Define the namespace dictionary to handle namespaces in the XML tags
    ns = {'ns': namespace}

    written = 0
    # Open a text file to write output
    with open(txt_file, 'w') as file:
        # Full replace: drop the previous set first.
        # This clears domains removed from the register and avoids duplicates —
        # one import = the current state of the register.
        file.write('/ip dns static remove [find comment="hazard-list"]\n')

        # Iterate over each 'PozycjaRejestru' element
        for pozycja in root.findall('ns:PozycjaRejestru', ns):
            # Find the 'AdresDomeny' element
            adres_domeny = pozycja.find('ns:AdresDomeny', ns)
            if adres_domeny is None or not adres_domeny.text:
                continue

            domain = adres_domeny.text.strip()
            # Skip invalid ones — no placeholder entries
            if not is_valid_domain(domain):
                continue
            try:
                domain = idna.encode(domain).decode('ascii')
            except Exception:
                pass  # already ascii/punycode — keep as is

            # type=A + REDIRECT_IP (MF komunikat) + match-subdomain (catches www. and subdomains)
            output_line = (
                f'/ip dns static add type=A address={REDIRECT_IP} '
                f'name="{domain}" match-subdomain=yes comment="hazard-list"\n'
            )
            file.write(output_line)
            written += 1

    return written

# URL to the XML data
url = 'https://hazard.mf.gov.pl/api/Register'
# Output text file path
output_txt = 'hazard_dns.rsc'
# Namespace URL
namespace = 'http://www.hazard.mf.gov.pl/2017/03/21/'

# Generate the .rsc; GitHub Actions commits the file, the router fetches it over HTTPS
count = download_and_parse_xml(url, output_txt, namespace)
print(f'hazard_dns.rsc: {count} domains from the register')
