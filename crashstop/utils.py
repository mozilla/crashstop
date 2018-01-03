# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bisect import bisect_left
from collections import defaultdict
import copy
from datetime import datetime
from dateutil.relativedelta import relativedelta
from libmozdata import utils
import pytz
import re
import six
from . import config
from .const import RAW, INSTALLS


HG_PAT = re.compile(r'^http[s]?://hg\.mozilla\.org/(?:releases/)?mozilla-([^/]*)/rev/([0-9a-f]+)$') # NOQA


try:
    UNICODE_EXISTS = bool(type(unicode))
except NameError:
    UNICODE_EXISTS = False


def get_str(s):
    if UNICODE_EXISTS and type(s) == unicode: # NOQA
        return s.encode('raw_unicode_escape')
    return s


def get_products():
    return config.get_products()


def get_channels():
    return config.get_channels()


def get_major(v):
    v = v.split('.')
    if len(v) >= 2:
        return int(v[0])
    return -1


def get_raw_installs(numbers):
    N = len(numbers)
    raw = [0] * N
    installs = copy.copy(raw)
    for i in range(N):
        n = numbers[i]
        raw[i] = n[RAW]
        installs[i] = n[INSTALLS]
    return raw, installs


def analyze_hg_url(url):
    channel = rev = ''
    m = HG_PAT.match(url)
    if m:
        channel = m.group(1)
        rev = m.group(2)
        if channel == 'central':
            channel = 'nightly'
        elif channel not in get_channels():
            channel = rev = ''

    return channel, rev


def analyze_hg_urls(urls, sumup=False):
    res = defaultdict(lambda: list())
    if sumup:
        for url in urls:
            url = url.split('|')
            res[url[0]].append(url[1])
    else:
        for url in urls:
            url = url.strip()
            chan, rev = analyze_hg_url(url)
            if chan:
                res[chan].append(rev)
    return res


def get_signatures(signatures):
    res = set()
    for s in signatures:
        if '[@' in s:
            sgns = map(lambda x: x.strip(), s.split('[@'))
            sgns = filter(None, sgns)
            sgns = map(lambda x: x[:-1].strip(), sgns)
        else:
            sgns = map(lambda x: x.strip(), s.split('\n'))
            sgns = filter(None, sgns)
        res |= set(sgns)

    return res


def get_params_for_link(query={}):
    today = utils.get_date_ymd('today')
    last = today - relativedelta(days=config.get_limit())
    last = utils.get_date_str(last)
    search_date = ['>=' + last]
    params = {'product': '',
              'date': search_date,
              'release_channel': '',
              'version': '',
              'signature': '',
              '_facets': ['url',
                          'user_comments',
                          'install_time',
                          'version',
                          'address',
                          'moz_crash_reason',
                          'reason',
                          'build_id',
                          'platform_pretty_version',
                          'signature',
                          'useragent_locale']}
    params.update(query)
    return params


def get_correct_product(p):
    if isinstance(p, six.string_types):
        p = p.lower()
        for prod in get_products():
            if p == prod.lower():
                return prod
    return 'Firefox'


def get_correct_products(p):
    return set(map(get_correct_product, p))


def get_correct_channel(c):
    if isinstance(c, six.string_types):
        c = c.lower()
        return c if c in get_channels() else 'nightly'
    return 'nightly'


def get_correct_sgn(sgn):
    if isinstance(sgn, six.string_types):
        return sgn
    elif isinstance(sgn, list) and len(sgn) >= 1:
        return sgn[0]
    return ''


def get_correct_filter(f):
    f = f.lower()
    if f in {'all', 'successful', 'unsuccessful'}:
        return f
    return 'all'


def get_esearch_sgn(sgn):
    if sgn.startswith('\"'):
        return '@' + sgn
    return '=' + sgn


def get_bug_number(bug):
    if bug is None:
        return 0
    try:
        return int(bug)
    except ValueError:
        return 0


def get_build_date(bid):
    if isinstance(bid, six.string_types):
        Y = int(bid[0:4])
        m = int(bid[4:6])
        d = int(bid[6:8])
        H = int(bid[8:10])
        M = int(bid[10:12])
        S = int(bid[12:])
    else:
        # 20160407164938 == 2016 04 07 16 49 38
        N = 5
        r = [0] * N
        for i in range(N):
            r[i] = bid % 100
            bid //= 100
        Y = bid
        S, M, H, d, m = r
    d = datetime(Y, m, d, H, M, S)
    dutc = pytz.utc.localize(d)

    return dutc


def get_buildid(date):
    return date.strftime('%Y%m%d%H%M%S')


def set_position(info, dates):
    pushdate = info['pushdate']
    if pushdate:
        pos = bisect_left(dates, pushdate)
        info['position'] = pos - 1
    else:
        info['position'] = -2


def get_dates(bids):
    start_date = utils.get_date_ymd('tomorrow')
    end_date = utils.get_guttenberg_death()
    date_ranges = {}

    for i in bids.values():
        for chan, j in i.items():
            # TODO: handle the case where j is empty...
            md, Md = j[0][0], j[-1][0]
            if md < start_date:
                start_date = md
            if Md > end_date:
                end_date = Md
            if chan not in date_ranges:
                date_ranges[chan] = [md, Md]
            else:
                r = date_ranges[chan]
                if md < r[0]:
                    r[0] = md
                if Md > r[1]:
                    r[1] = Md

    return start_date, end_date, date_ranges


def get_base_list(bids):
    base = {}
    nbase = [0] * 2
    for p, i in bids.items():
        base[p] = d = {}
        bids_prod = bids[p]
        for c in i.keys():
            d[c] = [copy.copy(nbase) for _ in range(len(bids_prod[c]))]
    return base


def equals_bids(b1, b2):
    if not b1 or not b2:
        return False

    for p, i in b1.items():
        for c, j in b2.items():
            if j != b2[p][c]:
                return False
    return True
