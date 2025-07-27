import re, os, json, time
def collect_akamai_headers():
    if not os.path.exists('curls.txt'):
        open('curls.txt', 'w', encoding='utf-8').close()
        return

    with open('curls.txt', 'r', encoding='utf-8') as f:
        curls = f.read().split("curl 'https://identity.att.com")

    # open('curls.txt', 'w', encoding='utf-8').close()

    v = 0
    for curl in curls:
        pattern = r"-H (?:'|\$')x-iozyazcd-([a-z0-9]+): ([^']+)'"
        matches = re.findall(pattern, curl, re.IGNORECASE)

        if len(matches) > 2:
            try:
                user_agent = re.findall(r"-H (?:'|\$')user-agent: ([^']+)'", curl, re.IGNORECASE)[0]
                sec_ch_ua_raw = re.findall(r"-H (?:'|\$')sec-ch-ua: ([^']+)'", curl, re.IGNORECASE)[0]
                sec_ch_ua_platform_raw = re.findall(r"-H (?:'|\$')sec-ch-ua-platform: ([^']+)'", curl, re.IGNORECASE)[0]
                att_convid = re.findall(r"-H (?:'|\$')x-att-conversationid: ([^']+)'", curl, re.IGNORECASE)[0]

                sec_ch_ua = sec_ch_ua_raw.replace('\\"', '"')
                sec_ch_ua_platform = sec_ch_ua_platform_raw.replace('\\"', '"')

                headers = {key.lower(): value for key, value in matches}

                print([
                headers,
                    user_agent,
                    sec_ch_ua,
                    sec_ch_ua_platform,
                    att_convid,
                    int(time.time())
                ])
                v += 1
            except IndexError:
                continue

    if v > 0:
        print(f'[+] Collected {v} akamai headers')

collect_akamai_headers()