# hazard-rsc

Turns the Polish Ministry of Finance gambling-domain register
([hazard.mf.gov.pl](https://hazard.mf.gov.pl)) into a MikroTik RouterOS script
(`.rsc`) that redirects every listed domain to the official MF komunikat page —
satisfying the ISP DNS-blocking + redirect obligation under art. 15f of the
*ustawa o grach hazardowych*.

## How it works

```
MF register (XML)  ->  GitHub Actions (daily)  ->  hazard_dns.rsc  ->  MikroTik
```

1. A scheduled workflow runs `parse_hazard_dns.py` once a day on GitHub's runners.
2. The script pulls the full register, converts each domain into a static DNS
   entry pointing to the official redirect IP and commits `hazard_dns.rsc`.
3. The router fetches the committed file over HTTPS and imports it.

No server to maintain, no credentials in the repo — the register is public data.

## Generated entries

Each line redirects the domain **and all its subdomains** to `145.237.235.240`
(the MF redirect IP from the WeWy spec — HTTP 302 to the komunikat page):

```
/ip dns static remove [find comment="hazard-list"]
/ip dns static add type=A address=145.237.235.240 name="example-casino.com" match-subdomain=yes comment="hazard-list"
...
```

The leading `remove` line makes every import a full replace: domains delisted
from the register are dropped, and no duplicates accumulate.

## Setup

1. Push `parse_hazard_dns.py` and `.github/workflows/hazard.yml` to a **public**
   repository.
2. Run the workflow once (Actions → *hazard-rsc* → Run workflow). It produces
   `hazard_dns.rsc`, served at:
   ```
   https://raw.githubusercontent.com/hreskiv/hazard-rsc/main/hazard_dns.rsc
   ```
3. On the router (CCR-class recommended for ~55k entries):
   ```
   /ip dns set cache-size=10240KiB cache-max-ttl=1d

   # Update script: import only if the download actually finished.
   # The file is ~6 MB, so a fixed delay is unreliable — gate on fetch status instead.
   /system script add name=hazard-update source={
     :local r [/tool fetch url="https://raw.githubusercontent.com/hreskiv/hazard-rsc/main/hazard_dns.rsc" mode=https dst-path=hazard_dns.rsc as-value];
     :if (($r->"status")="finished") do={ /import file-name=hazard_dns.rsc } else={ :log error "hazard: fetch failed" }
   }

   /system scheduler add name=hazard interval=1d start-time=04:30:00 on-event="/system script run hazard-update"
   ```

## Notes

- **Certificate check on fetch.** Prefer keeping HTTPS verification on
  (`check-certificate=yes-without-crl`, or import the GitHub CA chain) rather than
  `check-certificate=no`, so the blocklist can't be tampered with in transit.
- **Liveness monitoring.** Enable email-on-failure for the workflow — a dead job
  means a stale blocklist, which is a compliance gap (the register must be applied
  within 48h of a change).
- **Register API.** `GET https://hazard.mf.gov.pl/api/Register` returns XML of all
  currently blocked domains. The on-demand endpoint does **not** include removals,
  which is why the script rebuilds the full list each run instead of diffing.

## Source

- Register: https://hazard.mf.gov.pl
- I/O specification (WeWy): published on hazard.mf.gov.pl
