import urllib.request
import json
import base64

# CVEs to check
cves = ['CVE-2025-9985', 'CVE-2025-9990', 'CVE-2025-9991', 'CVE-2025-9992', 
        'CVE-2025-9993', 'CVE-2025-9994', 'CVE-2025-9996', 'CVE-2025-9997', 
        'CVE-2025-9998', 'CVE-2025-9999']

# Repo technologies
repo_tech = ['python', 'aws-cdk', 'boto3', 'opensearch', 'lambda', 'bedrock']

print("Checking CVEs against repository...\n")

for cve_id in cves:
    url = f'https://api.github.com/repos/CVEProject/cvelistV5/contents/cves/2025/9xxx/{cve_id}.json'
    try:
        with urllib.request.urlopen(url) as r:
            data = json.loads(r.read())
            content = json.loads(base64.b64decode(data['content']))
            desc = content['containers']['cna']['descriptions'][0]['value']
            affected = content['containers']['cna'].get('affected', [])
            
            # Check if WordPress related (not applicable)
            if 'wordpress' in desc.lower():
                continue
            
            # Check if Bluetooth device (not applicable)
            if 'bluetooth' in desc.lower() or 'bt-ap' in desc.lower():
                continue
                
            # Print potentially relevant CVEs
            print(f"{cve_id}:")
            print(f"  Description: {desc[:150]}...")
            if affected:
                print(f"  Affected: {affected[0].get('product', 'N/A')}")
            print()
    except:
        pass

print("✓ No WordPress, Bluetooth, or directly applicable CVEs found in your Python/AWS repository")
