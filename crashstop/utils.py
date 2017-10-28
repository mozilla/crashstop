# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from bisect import bisect_left
from collections import defaultdict
from datetime import datetime
from dateutil.relativedelta import relativedelta
from libmozdata import utils
import pytz
import re
import six
from . import config


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


def analyze_hg_urls(urls):
    res = defaultdict(lambda: list())
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
    if isinstance(p, list) and len(p) >= 1:
        p = p[0]
    if isinstance(p, six.string_types):
        p = p.lower()
        prods = {'firefox': 'Firefox',
                 'fennecandroid': 'FennecAndroid'}
        return prods.get(p, 'Firefox')
    return 'Firefox'


def get_correct_channel(c):
    if isinstance(c, list) and len(c) >= 1:
        c = c[0]
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
    # 20160407164938 == 2016 04 07 16 49 38
    N = 5
    r = [0] * N
    for i in range(N):
        r[i] = bid % 100
        bid //= 100
    Y = bid
    S, M, H, d, m = r
    d = datetime(Y, m, d, H, M, S)
    d = pytz.utc.localize(d)

    return d


def get_buildid(date):
    return date.strftime('%Y%m%d%H%M%S')


def set_position(info, dates):
    pushdate = info['pushdate']
    pos = bisect_left(dates, pushdate)
    if pos != 0:
        pos -= 1
    info['position'] = pos
