import requests
from bs4 import BeautifulSoup
url = 'https://www.studycpp.cn/basic/chapter1/program-structure/'
headers = {'User-Agent': 'Mozilla/5.0'}
resp = requests.get(url, headers=headers, timeout=30)
resp.encoding = 'utf-8'
soup = BeautifulSoup(resp.text, 'html.parser')
card = soup.select_one('.col-md-8.card')
pre_tags = card.find_all('pre')
print(f"Total pre tags: {len(pre_tags)}")
for pre in pre_tags:
    code = pre.find('code')
    if code:
        cls = code.get('class', [])
        text = code.get_text()[:150]
        print(f"CODE class={cls}: {text}")
    else:
        print(f"PRE only: {pre.get_text()[:100]}")
