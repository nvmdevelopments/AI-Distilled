import re
import requests

def get_pub_date(vid):
    html = requests.get(f"https://www.youtube.com/watch?v={vid}").text
    match = re.search(r'"publishDate":"([^"]+)"', html)
    if match:
        print(f"publishDate for {vid}: {match.group(1)}")
    else:
        print(f"publishDate not found for {vid}")

get_pub_date("WBN1CyBy8bE")
