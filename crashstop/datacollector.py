# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import copy
from collections import defaultdict
from datetime import datetime
from dateutil.relativedelta import relativedelta
import functools
from libmozdata import socorro, utils as lmdutils
from libmozdata.patchanalysis import get_patch_info
from libmozdata.hgmozilla import Revision
import time
from . import config
from . import utils


def remove_dup_versions(data):
    res = {}
    if 'nightly' in data:
        res['nightly'] = [(b, v) for b, v, _ in data['nightly']]

    for chan in ['beta', 'release']:
        if chan in data:
            versions = {}
            for b, v, c in data[chan]:
                if v in versions:
                    if c > versions[v][1]:
                        versions[v] = (b, c)
                else:
                    versions[v] = (b, c)
            res[chan] = []
            for v, i in versions.items():
                bid, _ = i
                res[chan].append((bid, v))
    return res


def get_buildids(search_date, channels, product):
    data = {chan: list() for chan in channels}

    def handler(chan, threshold, json, data):
        if json['errors'] or not json['facets']['build_id']:
            return
        for facets in json['facets']['build_id']:
            count = facets['count']
            if count >= threshold:
                version = facets['facets']['version'][0]['term']
                if chan != 'beta' or not version.endswith('a2'):
                    buildid = facets['term']
                    data.append((buildid, version, count))

    params = {'product': product,
              'release_channel': '',
              'date': search_date,
              '_aggs.build_id': 'version',
              '_results_number': 0,
              '_facets_size': 1000}

    searches = []
    for chan in channels:
        params = copy.deepcopy(params)
        if chan == 'beta' and product == 'Firefox':
            params['release_channel'] = ['beta', 'aurora']
        else:
            params['release_channel'] = chan
        threshold = config.get_min_total(product, chan)
        hdler = functools.partial(handler, chan, threshold)
        searches.append(socorro.SuperSearch(params=params,
                                            handler=hdler,
                                            handlerdata=data[chan]))

    for s in searches:
        s.wait()

    data = remove_dup_versions(data)

    res = {}
    for chan, bids in data.items():
        bids = sorted(bids, reverse=True)
        min_v = config.get_versions(product, chan)
        if len(bids) > min_v:
            bids = bids[:min_v]
        bids = [(utils.get_build_date(bid), v) for bid, v in bids]
        res[chan] = bids

    return res


def get_sgns_by_buildid(channels, product='Firefox',
                        date='today', query={}):
    today = lmdutils.get_date_ymd(date)
    few_days_ago = today - relativedelta(days=config.get_limit())
    search_date = socorro.SuperSearch.get_search_date(few_days_ago)
    bids = get_buildids(search_date, channels, product)
    nbase = {'raw': 0,
             'installs': 0}
    base = {c: {b: nbase.copy() for b, _ in bids[c]} for c in channels}
    data = {}
    limit = config.get_limit_facets()

    def handler(base, chan, bid, json, data):
        if json['errors'] or not json['facets']['signature']:
            return
        for facets in json['facets']['signature']:
            sgn = facets['term']
            if sgn not in data:
                data[sgn] = copy.deepcopy(base)
            data[sgn][bid]['raw'] = facets['count']
            facets = facets['facets']
            n = len(facets['install_time'])
            if n == limit:
                n = facets['cardinality_install_time']['value']
            data[sgn][bid]['installs'] = n

    base_params = {'product': product,
                   'release_channel': '',
                   'build_id': '',
                   'date': search_date,
                   '_aggs.signature': ['install_time',
                                       '_cardinality.install_time'],
                   '_results_number': 0,
                   '_facets': 'release_channel',
                   '_facets_size': limit}
    base_params.update(query)

    searches = []
    for chan in channels:
        params = copy.deepcopy(base_params)
        params['release_channel'] = chan
        data[chan] = {}
        for bid, _ in bids[chan]:
            params = copy.deepcopy(params)
            params['build_id'] = utils.get_buildid(bid)
            hdler = functools.partial(handler, base[chan], chan, bid)
            searches.append(socorro.SuperSearch(params=params,
                                                handler=hdler,
                                                handlerdata=data[chan],
                                                timeout=120))
            time.sleep(1)

    for s in searches:
        s.wait()

    res = defaultdict(lambda: dict())
    for chan, i in data.items():
        threshold = config.get_min(product, chan)
        for sgn, j in i.items():
            numbers = [v['raw'] for v in j.values()]
            if max(numbers) >= threshold:
                res[chan][sgn] = j

    return res, bids


def get_sgns_data(channels, bids, signatures, products, date='today'):
    today = lmdutils.get_date_ymd(date)
    few_days_ago = today - relativedelta(days=config.get_limit())
    search_date = socorro.SuperSearch.get_search_date(few_days_ago)

    nbase = {'raw': 0,
             'installs': 0}
    data = {}

    for product in products:
        data[product] = d1 = {}
        b1 = bids[product]
        for chan in channels:
            d1[chan] = d2 = {}
            b2 = b1[chan]
            for signature in signatures:
                d2[signature] = {bid: nbase.copy() for bid in b2}

    limit = config.get_limit_facets()
    signatures = ['=' + s for s in signatures]

    def handler(bid, json, data):
        if json['errors'] or not json['facets']['signature']:
            return
        for facets in json['facets']['signature']:
            sgn = facets['term']
            data[sgn][bid]['raw'] = facets['count']
            facets = facets['facets']
            n = len(facets['install_time'])
            if n == limit:
                n = facets['cardinality_install_time']['value']
            data[sgn][bid]['installs'] = n

    base_params = {'product': '',
                   'release_channel': '',
                   'build_id': '',
                   'signature': signatures,
                   'date': search_date,
                   '_aggs.signature': ['install_time',
                                       '_cardinality.install_time'],
                   '_results_number': 0,
                   '_facets': 'release_channel',
                   '_facets_size': limit}

    searches = []
    for product in products:
        pparams = copy.deepcopy(base_params)
        pparams['product'] = product
        d1 = data[product]
        b1 = bids[product]
        for chan in channels:
            params = copy.deepcopy(pparams)
            params['release_channel'] = chan
            d2 = d1[chan]
            for bid in b1[chan]:
                params = copy.deepcopy(params)
                params['build_id'] = utils.get_buildid(bid)
                hdler = functools.partial(handler, bid)
                searches.append(socorro.SuperSearch(params=params,
                                                    handler=hdler,
                                                    handlerdata=d2,
                                                    timeout=120))

    for s in searches:
        s.wait()

    return data


def compare_lands(l1, l2):
    chans = utils.get_channels()
    for chan in chans:
        if chan in l1 and chan in l2:
            if l1[chan] <= l2[chan]:
                return l2
    return None


def get_patches(signatures):
    bugs_by_signature = socorro.Bugs.get_bugs(list(signatures))
    bugs = set()
    for b in bugs_by_signature.values():
        bugs = bugs.union(set(b))

    patches = get_patch_info(bugs, channels=utils.get_channels())
    pushdates = {}

    for sgn, bugs in bugs_by_signature.items():
        for bug in map(str, bugs):
            land = patches.get(bug, {}).get('land', {})
            if land:
                if sgn in pushdates:
                    land = compare_lands(pushdates[sgn]['land'], land)
                    if land:
                        pushdates[sgn]['land'] = land
                        pushdates[sgn]['bugid'] = bug
                else:
                    pushdates[sgn] = {'land': land,
                                      'bugid': bug}
    return pushdates


def get_pushdates(chan_rev):

    def handler(json, data):
        pushdate = json['pushdate'][0]
        pushdate = lmdutils.as_utc(datetime.utcfromtimestamp(pushdate))
        data.append(pushdate)

    res = []
    data = {}
    for chan, revs in chan_rev.items():
        data[chan] = pd = []
        for rev in revs:
            res.append(Revision(channel=chan,
                                params={'node': rev},
                                handler=handler,
                                handlerdata=pd))

    return res, data
