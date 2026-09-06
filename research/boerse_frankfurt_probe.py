"""Probe: Börse Frankfurt bond quotes via the api.boerse-frankfurt.de endpoints the website uses.
Headers: Client-Date (UTC ISO ms), X-Client-TraceId = md5(ClientDate + url + salt), X-Security = md5(yyyyMMddHHmm).
The salt is read from the site bundle (main.*.js on live.deutsche-boerse.com) and rotates with deploys.
Verified 6 Sep 2026 with Barclays PLC 6.125% AT1 XS3176355751: last 99.15, 9-day history, master data with subordinated=true.
Terms: free only for non-commercial, non-redistributed use.
"""
import hashlib, json, urllib.parse, requests
from datetime import datetime, timezone
SALT="af5a8d16eb5dc49f8a72b26fd9185475c7a"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
B="https://api.boerse-frankfurt.de/"
def hdrs(url):
    now=datetime.now(timezone.utc); cd=now.strftime("%Y-%m-%dT%H:%M:%S.")+f"{now.microsecond//1000:03d}Z"
    return {"Client-Date":cd,"X-Client-TraceId":hashlib.md5((cd+url+SALT).encode()).hexdigest(),"X-Security":hashlib.md5(datetime.now().strftime("%Y%m%d%H%M").encode()).hexdigest(),"User-Agent":UA,"Accept":"application/json, text/plain, */*","Origin":"https://live.deutsche-boerse.com","Referer":"https://live.deutsche-boerse.com/"}
def get(fn,params):
    url=B+"v1/data/"+fn+"?"+urllib.parse.urlencode(params); r=requests.get(url,headers=hdrs(url),timeout=30); return r.status_code,r.text[:900]
def post(fn,body):
    url=B+"v1/search/"+fn; h=hdrs(url); h["Content-Type"]="application/json; charset=UTF-8"; r=requests.post(url,headers=h,json=body,timeout=30); return r.status_code,r.text[:1200]
I="XS3176355751"
for fn,p in [("quote_box/single",{"isin":I,"mic":"XFRA"}),("price_information/single",{"isin":I,"mic":"XFRA"}),("bid_ask_overview/single",{"isin":I,"mic":"XFRA"}),("master_data_bond",{"isin":I}),("instrument_information",{"slug":"xs3176355751-barclays-25-und-flr"}),("price_history",{"isin":I,"mic":"XFRA","minDate":"2026-08-25","maxDate":"2026-09-05","limit":3,"offset":0,"cleanSplit":"false","cleanPayout":"false","cleanSubscriptionRights":"false"}),("data_sheet_header",{"isin":I,"mic":"XFRA"}),("bond_data",{"isin":I,"mic":"XFRA"})]:
    print("##",fn,get(fn,p)); print()
print("## bond_search issuerName:",post("bond_search",{"issuerName":"Barclays","lang":"en","offset":0,"limit":3}))
print("## bond_search searchTerm:",post("bond_search",{"searchTerm":"Barclays","lang":"en","offset":0,"limit":3}))
print("## search_instruments:",post("search_instruments",{"searchTerm":"Barclays 6,125","lang":"en","offset":0,"limit":3}))
