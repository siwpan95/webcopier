import requests
from bs4 import BeautifulSoup
url = 'https://www.studycpp.cn/basic/chapter1/program-structure/'
headers = {'User-Agent': 'Mozilla/5.0'}
resp = requests.get(url, headers=headers, timeout=30)
resp.encoding = 'utf-8'
soup = BeautifulSoup(resp.text, 'html.parser')
card = soup.select_one('.col-md-8.card')

# Check if pre tags are direct children
direct_pres = card.find_all('pre', recursive=False)
all_pres = card.find_all('pre')
print(f"Direct pre children: {len(direct_pres)}")
print(f"All pre (recursive): {len(all_pres)}")

# Check parent of first pre
for pre in all_pres[:3]:
    parent = pre.parent
    print(f"  pre parent: <{parent.name}> class={parent.get('class', [])}")
    # Check how nested it is
    depth = 0
    p = pre
    while p and p != card:
        p = p.parent
        depth += 1
    print(f"    depth from card: {depth}")
