import urllib.request
import json
import base64

# Get 2025 directory
with urllib.request.urlopen('https://api.github.com/repos/CVEProject/cvelistV5/contents/cves/2025') as r:
    years = json.loads(r.read())

# Get last year folder
last_year = sorted([d['name'] for d in years if d['type'] == 'dir'])[-1]
with urllib.request.urlopen(f'https://api.github.com/repos/CVEProject/cvelistV5/contents/cves/2025/{last_year}') as r:
    cves = sorted([c['name'].replace('.json', '') for c in json.loads(r.read()) if c['name'].endswith('.json')])[-10:]

# Fetch CVE details
for cve_id in cves:
    url = f'https://api.github.com/repos/CVEProject/cvelistV5/contents/cves/2025/{last_year}/{cve_id}.json'
    with urllib.request.urlopen(url) as r:
        data = json.loads(r.read())
        content = json.loads(base64.b64decode(data['content']))
        desc = content['containers']['cna']['descriptions'][0]['value']
        print(f"{cve_id}: {desc[:100]}...")
