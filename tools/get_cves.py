#!/usr/bin/env python3
"""
Tool to retrieve CVEs from GitHub CVEProject/cvelistV5 repository

USAGE:
    python get_cves.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD [--limit N] [--output FILE]

EXAMPLES:
    # Get latest 10 CVEs from 2025
    python get_cves.py --start-date 2025-01-01 --end-date 2025-12-31 --limit 10

    # Get recent CVEs and save to file
    python get_cves.py --start-date 2024-11-01 --end-date 2025-12-31 --limit 20 --output recent_cves.json

    # Get all CVEs from last month
    python get_cves.py --start-date 2024-10-01 --end-date 2024-10-31

REQUIREMENTS:
    - Set GITHUB_API_TOKEN environment variable with a valid GitHub Personal Access Token
    - Install required packages: requests

NOTES:
    - Script traverses from newest to oldest CVEs for efficiency
    - Rate limited by GitHub API (5000 requests/hour for core API)
    - Returns CVEs sorted by publication date (newest first)
"""

import os
import requests
import json
from datetime import datetime, timedelta
import argparse


def get_cves(start_date, end_date, limit=100):
    """
    Retrieve recent CVEs efficiently by traversing from newest to oldest
    
    Args:
        start_date (str): Start date in YYYY-MM-DD format
        end_date (str): End date in YYYY-MM-DD format  
        limit (int): Maximum number of CVEs to retrieve
    
    Returns:
        list: List of CVE data
    """
    token = os.getenv('GITHUB_API_TOKEN')
    if not token:
        raise ValueError("GITHUB_API_TOKEN environment variable not set")
    
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    
    cves = []
    
    # Get years in reverse order (newest first)
    years_url = "https://api.github.com/repos/CVEProject/cvelistV5/contents/cves"
    years_response = requests.get(years_url, headers=headers)
    years_response.raise_for_status()
    
    years = [int(item['name']) for item in years_response.json() 
             if item['type'] == 'dir' and item['name'].isdigit()]
    years.sort(reverse=True)
    
    for year in years:
        if len(cves) >= limit:
            break
            
        if year < start_dt.year or year > end_dt.year:
            continue
            
        # Get CVE ranges for this year (only check most recent range for efficiency)
        year_url = f"https://api.github.com/repos/CVEProject/cvelistV5/contents/cves/{year}"
        year_response = requests.get(year_url, headers=headers)
        year_response.raise_for_status()
        
        # Sort ranges in reverse order (9xxx, 8xxx, etc.) and limit to recent ones
        ranges = [item for item in year_response.json() if item['type'] == 'dir']
        ranges.sort(key=lambda x: x['name'], reverse=True)
        
        # Only check the most recent 2 ranges for efficiency
        for range_dir in ranges[:2]:
            if len(cves) >= limit:
                break
                
            # Get CVE files in this range
            range_url = f"https://api.github.com/repos/CVEProject/cvelistV5/contents/cves/{year}/{range_dir['name']}"
            range_response = requests.get(range_url, headers=headers)
            range_response.raise_for_status()
            
            # Sort files in reverse order (newest CVE numbers first) and limit
            files = [item for item in range_response.json() 
                    if item['type'] == 'file' and item['name'].endswith('.json')]
            files.sort(key=lambda x: x['name'], reverse=True)
            
            # Only check the most recent 20 files per range for efficiency
            for file_item in files[:20]:
                if len(cves) >= limit:
                    break
                    
                try:
                    # Get file content
                    file_response = requests.get(file_item['download_url'])
                    file_response.raise_for_status()
                    
                    cve_data = file_response.json()
                    
                    # Extract and check date
                    date_published = cve_data.get('cveMetadata', {}).get('datePublished', '')
                    if date_published:
                        try:
                            if 'T' in date_published:
                                pub_date = datetime.fromisoformat(date_published.replace('Z', '+00:00')).replace(tzinfo=None)
                            else:
                                pub_date = datetime.strptime(date_published, '%Y-%m-%d')
                        except ValueError:
                            continue
                            
                        if start_dt <= pub_date <= end_dt:
                            cves.append(cve_data)
                            
                except (json.JSONDecodeError, KeyError, requests.RequestException):
                    continue
    
    # Sort by date published (newest first)
    cves.sort(key=lambda x: x.get('cveMetadata', {}).get('datePublished', ''), reverse=True)
    return cves[:limit]


def main():
    parser = argparse.ArgumentParser(description='Retrieve CVEs from GitHub CVEProject repository')
    parser.add_argument('--start-date', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--limit', type=int, default=100, help='Maximum number of CVEs to retrieve')
    parser.add_argument('--output', help='Output file path (JSON format)')
    
    args = parser.parse_args()
    
    try:
        cves = get_cves(args.start_date, args.end_date, args.limit)
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(cves, f, indent=2)
            print(f"Retrieved {len(cves)} CVEs and saved to {args.output}")
        else:
            print(json.dumps(cves, indent=2))
            
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
